from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

from domain.movies.models import Movie
from domain.rooms.models import Room


class Screening(models.Model):
    class Status(models.TextChoices):
        DRAFT = "borrador", "Borrador"
        SCHEDULED = "programada", "Programada"
        PUBLISHED = "publicada", "Publicada"
        IN_PROGRESS = "en_proyeccion", "En proyección"
        CANCELED = "cancelada", "Cancelada"
        FINISHED = "finalizada", "Finalizada"

    TRANSITIONS = {
        Status.DRAFT: (Status.SCHEDULED, Status.PUBLISHED),
        Status.SCHEDULED: (Status.DRAFT, Status.PUBLISHED, Status.CANCELED),
        Status.PUBLISHED: (Status.SCHEDULED, Status.CANCELED),
        Status.IN_PROGRESS: (),
        Status.CANCELED: (),
        Status.FINISHED: (),
    }

    movie = models.ForeignKey(
        Movie,
        on_delete=models.CASCADE,
        related_name="screenings",
        verbose_name="Pelicula",
        db_column="pelicula_id",
    )
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="screenings", db_column="sala_id")
    starts_at = models.DateTimeField(db_column="fecha_horario")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_column="estado")
    ticket_price = models.DecimalField(max_digits=8, decimal_places=2, db_column="precio_entrada")
    prices_by_type = models.JSONField(default=dict, blank=True, db_column="precios_por_tipo")
    room_layout_snapshot = models.JSONField(default=list, blank=True, db_column="sala_configuracion_snapshot")
    capacity_snapshot = models.PositiveIntegerField(default=0, db_column="capacidad_snapshot")

    class Meta:
        verbose_name = "función"
        verbose_name_plural = "funciones"
        db_table = "screenings_funcion"
        ordering = ["starts_at"]

    def __str__(self):
        return f"{self.movie.title} - {self.room.name} - {self.starts_at:%d/%m/%Y %H:%M}"

    @property
    def ends_at(self):
        return self.starts_at + timedelta(minutes=self.movie.duration_minutes)

    @property
    def available_capacity(self):
        return self.capacity_snapshot or self.room.capacity

    @property
    def price_from(self):
        prices = [Decimal(str(price)) for price in (self.prices_by_type or {}).values()]
        if prices:
            return min(prices)
        return self.ticket_price

    def price_for_type(self, type_id):
        price = (self.prices_by_type or {}).get(str(type_id))
        if price is not None:
            return Decimal(str(price))
        return self.ticket_price

    def capture_room_configuration(self):
        seats = self.room.seats.select_related("seat_type").order_by("row", "column")
        price_config = {}
        seat_snapshot = []
        for seat in seats:
            seat_price = str(seat.seat_type.base_price)
            price_config[str(seat.seat_type_id)] = seat_price
            seat_snapshot.append(
                {
                    "row": seat.row,
                    "column": seat.column,
                    "type": seat.seat_type.name,
                    "type_id": seat.seat_type_id,
                    "price": str(seat_price),
                    "color": seat.seat_type.color,
                    "icon_url": seat.seat_type.icon.url if seat.seat_type.icon else "",
                }
            )
        layout = self.room.layout_configuration or {}
        rows = layout.get("rows") or max((seat["row"] for seat in seat_snapshot), default=-1) + 1
        columns = layout.get("columns") or max((seat["column"] for seat in seat_snapshot), default=-1) + 1
        self.room_layout_snapshot = {
            "rows": rows,
            "columns": columns,
            "seats": seat_snapshot,
        }
        self.capacity_snapshot = len(seat_snapshot) if seat_snapshot else self.room.capacity
        if price_config:
            self.prices_by_type = {
                str(type_id): str(price)
                for type_id, price in price_config.items()
            }
            self.ticket_price = min(
                Decimal(str(price)) for price in self.prices_by_type.values()
            )

    def save(self, *args, **kwargs):
        with transaction.atomic():
            previous = None
            if self.pk:
                previous = type(self).objects.select_for_update().get(pk=self.pk)
            if self.room_id and not self.capacity_snapshot:
                self.capture_room_configuration()
            super().save(*args, **kwargs)
            status_written = kwargs.get("update_fields") is None or "status" in kwargs["update_fields"]
            if status_written and self.status == self.Status.CANCELED and (
                previous is None or previous.status != self.Status.CANCELED
            ):
                from domain.tickets.services import (
                    enqueue_refund_notifications,
                    refund_canceled_screening,
                )

                refund_ids = refund_canceled_screening(self)
                transaction.on_commit(
                    lambda refund_ids=refund_ids: enqueue_refund_notifications(refund_ids)
                )

    @property
    def has_sales(self):
        sold = getattr(self, "tickets_sold", None)
        if sold is not None:
            return sold > 0
        return self.ticket_purchases.exists()

    @property
    def is_editable(self):
        if self.status in (self.Status.DRAFT, self.Status.SCHEDULED):
            return True
        return (
            self.status == self.Status.PUBLISHED
            and self.starts_at > timezone.now()
            and not self.has_sales
        )

    @property
    def is_deletable(self):
        return self.status in (self.Status.DRAFT, self.Status.SCHEDULED)

    def can_transition_to(self, new_status):
        if new_status not in self.TRANSITIONS[self.status]:
            return False
        if new_status == self.Status.CANCELED and self.starts_at <= timezone.now():
            return False
        if (
            self.status == self.Status.PUBLISHED
            and new_status == self.Status.SCHEDULED
        ):
            return not self.has_sales
        return True

    @property
    def available_transitions(self):
        return [
            status
            for status in self.TRANSITIONS[self.status]
            if self.can_transition_to(status)
        ]

    def change_status(self, new_status):
        with transaction.atomic():
            current = type(self).objects.select_for_update().get(pk=self.pk)
            current._change_status(new_status)
            self.refresh_from_db()

    def _change_status(self, new_status):
        if not self.can_transition_to(new_status):
            raise ValidationError(
                f"No se puede pasar una función {self.get_status_display().lower()} "
                f"a {self.Status(new_status).label.lower()}."
            )
        if (
            new_status in (self.Status.SCHEDULED, self.Status.PUBLISHED)
            and self.starts_at <= timezone.now()
        ):
            raise ValidationError(
                "No se puede programar ni publicar una función con fecha pasada."
            )
        self.status = new_status
        update_fields = ["status"]
        if new_status == self.Status.PUBLISHED:
            self.capture_room_configuration()
            update_fields.extend(
                [
                    "room_layout_snapshot",
                    "capacity_snapshot",
                    "prices_by_type",
                    "ticket_price",
                ]
            )
        self.save(update_fields=update_fields)

    def clean(self):
        super().clean()
        errors = {}

        if self.prices_by_type:
            for price in self.prices_by_type.values():
                try:
                    normalized_price = Decimal(str(price))
                except (InvalidOperation, TypeError, ValueError):
                    errors["prices_by_type"] = "Todos los precios por tipo de asiento deben ser numericos."
                    break
                if normalized_price <= 0:
                    errors["prices_by_type"] = "Todos los precios por tipo de asiento deben ser mayores a cero."
                    break
        elif self.ticket_price is not None and self.ticket_price <= 0:
            errors["ticket_price"] = "El precio debe ser mayor a cero."

        if self.starts_at and self.starts_at <= timezone.now():
            errors["starts_at"] = "La fecha y horario deben ser futuros."

        if errors:
            raise ValidationError(errors)

        if not self.movie_id or not self.room_id or not self.starts_at:
            return

        start = self.starts_at
        end = self.ends_at
        same_room_screenings = (
            Screening.objects.filter(room=self.room)
            .exclude(status=self.Status.CANCELED)
            .select_related("movie")
            .exclude(pk=self.pk)
        )

        for screening in same_room_screenings:
            if screening.starts_at < end and screening.ends_at > start:
                raise ValidationError(
                    "La sala ya tiene una función programada en ese horario."
                )

    @classmethod
    def finalize_expired(cls):
        now = timezone.now()
        candidates = cls.objects.filter(
            status__in=(cls.Status.SCHEDULED, cls.Status.PUBLISHED, cls.Status.IN_PROGRESS),
            starts_at__lte=now,
        ).select_related("movie")
        finished = []
        in_progress = []
        for screening in candidates:
            if screening.ends_at <= now:
                finished.append(screening.pk)
            elif screening.status in (cls.Status.SCHEDULED, cls.Status.PUBLISHED):
                in_progress.append(screening.pk)
        if in_progress:
            cls.objects.filter(pk__in=in_progress).update(status=cls.Status.IN_PROGRESS)
        if finished:
            cls.objects.filter(pk__in=finished).update(status=cls.Status.FINISHED)

    @classmethod
    def published(cls):
        return cls.objects.filter(status=cls.Status.PUBLISHED).select_related(
            "movie", "room"
        )
