from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction
from django.utils import timezone

from domain.cinema.models import CinemaSettings
from domain.screenings.models import Screening


def index_to_letters(index):
    label = ""
    value = index + 1
    while value > 0:
        value, remainder = divmod(value - 1, 26)
        label = chr(65 + remainder) + label
    return label


class TicketPurchase(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ticket_purchases",
        db_column="usuario_id",
    )
    screening = models.ForeignKey(
        Screening,
        on_delete=models.CASCADE,
        related_name="ticket_purchases",
        db_column="funcion_id",
    )
    quantity = models.PositiveIntegerField(db_column="cantidad")
    total = models.DecimalField(max_digits=10, decimal_places=2)
    selected_seats = models.JSONField(default=list, blank=True, db_column="asientos_seleccionados")
    created_at = models.DateTimeField(auto_now_add=True, db_column="creada_en")

    class Meta:
        verbose_name = "Compra de entrada"
        verbose_name_plural = "Compras de entradas"
        db_table = "tickets_compraentrada"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} - {self.screening} x{self.quantity}"

    @property
    def seat_labels(self):
        labels = self._labels_from_selected_seats(self.selected_seats)
        return ", ".join(labels)

    @classmethod
    def sold_quantity(cls, screening):
        cls.sync_sold_seats(screening)
        sold_seats = SeatPurchase.objects.filter(screening=screening).count()
        legacy_total = 0
        legacy_purchases = cls.objects.filter(screening=screening, selected_seats=[]).prefetch_related(
            "sold_seats"
        )
        for purchase in legacy_purchases:
            legacy_total += max(purchase.quantity - purchase.sold_seats.count(), 0)
        return sold_seats + legacy_total

    @classmethod
    def available_for(cls, screening):
        return max(screening.available_capacity - cls.sold_quantity(screening), 0)

    @classmethod
    def seat_prices(cls, screening):
        snapshot = screening.room_layout_snapshot or {}
        if isinstance(snapshot, dict):
            seats = snapshot.get("seats", [])
            columns_count = snapshot.get("columns") or max(
                (seat["column"] for seat in seats), default=-1
            ) + 1
        else:
            seats = snapshot
            columns_count = max((seat["column"] for seat in seats), default=-1) + 1

        occupied_columns = {seat["column"] for seat in seats}
        column_labels = {}
        next_column_label = 0
        for column_index in range(columns_count):
            if column_index in occupied_columns:
                column_labels[column_index] = index_to_letters(next_column_label)
                next_column_label += 1

        prices = {}
        for seat in seats:
            column_label = column_labels.get(seat["column"], "")
            if not column_label:
                continue
            label = f"{seat['row'] + 1}{column_label}"
            prices[label] = screening.price_for_type(seat.get("type_id"))
        return prices

    @classmethod
    def _labels_from_selected_seats(cls, selected_seats):
        labels = []
        for seat in selected_seats or []:
            label = seat.get("label") if isinstance(seat, dict) else str(seat)
            if label and label not in labels:
                labels.append(label)
        return labels

    @classmethod
    def occupied_seats(cls, screening):
        cls.sync_sold_seats(screening)
        return set(SeatPurchase.objects.filter(screening=screening).values_list("label", flat=True))

    @classmethod
    def blocked_seats(cls, screening, user=None):
        occupied = cls.occupied_seats(screening)
        reserved = SeatReservation.active_for(screening)
        if user is not None and getattr(user, "is_authenticated", False):
            reserved = reserved.exclude(user=user)
        return occupied | set(reserved.values_list("label", flat=True))

    @classmethod
    def sync_sold_seats(cls, screening):
        purchases = cls.objects.filter(screening=screening)
        legacy_purchases = []
        legacy_sold_count = 0
        for purchase in purchases:
            labels = cls._labels_from_selected_seats(purchase.selected_seats)
            if labels:
                for label in labels:
                    SeatPurchase.objects.get_or_create(
                        purchase=purchase,
                        screening=screening,
                        label=label,
                    )
            else:
                assigned_count = SeatPurchase.objects.filter(purchase=purchase).count()
                remaining = max(purchase.quantity - assigned_count, 0)
                if remaining:
                    legacy_purchases.append({"purchase": purchase, "remaining": remaining})
                    legacy_sold_count += remaining

        if legacy_sold_count:
            occupied_labels = set(
                SeatPurchase.objects.filter(screening=screening).values_list("label", flat=True)
            )
            legacy_index = 0
            legacy_remaining = legacy_purchases[legacy_index]["remaining"] if legacy_purchases else 0
            for label in cls.seat_prices(screening):
                if label in occupied_labels:
                    continue
                while legacy_purchases and legacy_remaining <= 0:
                    legacy_index += 1
                    if legacy_index >= len(legacy_purchases):
                        break
                    legacy_remaining = legacy_purchases[legacy_index]["remaining"]
                if legacy_index >= len(legacy_purchases):
                    break
                SeatPurchase.objects.get_or_create(
                    purchase=legacy_purchases[legacy_index]["purchase"],
                    screening=screening,
                    label=label,
                )
                occupied_labels.add(label)
                legacy_remaining -= 1
                legacy_sold_count -= 1
                if legacy_sold_count <= 0:
                    break

    @classmethod
    def total_for_seats(cls, screening, selected_seats):
        seat_prices = cls.seat_prices(screening)
        labels = cls._labels_from_selected_seats(selected_seats)

        if not labels:
            return None, 0, []

        invalid_labels = [label for label in labels if label not in seat_prices]
        if invalid_labels:
            raise ValidationError({"quantity": "La seleccion de asientos no es valida."})

        selected_payload = [
            {"label": label, "price": str(seat_prices[label])}
            for label in labels
        ]
        return sum(seat_prices[label] for label in labels), len(labels), selected_payload

    @classmethod
    def buy(cls, user, screening, quantity, selected_seats=None, require_reservation=False):
        with transaction.atomic():
            quantity = int(quantity)
            screening = Screening.objects.select_for_update().select_related("room").get(
                pk=screening.pk
            )
            SeatReservation.clear_expired()
            list(cls.objects.select_for_update().filter(screening=screening))
            list(SeatPurchase.objects.select_for_update().filter(screening=screening))
            list(SeatReservation.objects.select_for_update().filter(screening=screening))
            total_seats, seat_quantity, selected_payload = cls.total_for_seats(
                screening, selected_seats
            )
            if selected_payload:
                occupied_labels = cls.occupied_seats(screening)
                already_taken = [
                    seat["label"]
                    for seat in selected_payload
                    if seat["label"] in occupied_labels
                ]
                if already_taken:
                    raise ValidationError(
                        {"quantity": "Algunos asientos seleccionados ya no estan disponibles."}
                    )
                if require_reservation:
                    reserved_by_user = set(
                        SeatReservation.active_for(screening)
                        .filter(user=user)
                        .values_list("label", flat=True)
                    )
                    missing_reservations = [
                        seat["label"]
                        for seat in selected_payload
                        if seat["label"] not in reserved_by_user
                    ]
                    if missing_reservations:
                        raise ValidationError(
                            {"quantity": "Algunas butacas ya no estan reservadas para tu compra."}
                        )
            if seat_quantity:
                quantity = seat_quantity
            total = total_seats if total_seats is not None else screening.price_from * quantity
            purchase = cls(
                user=user,
                screening=screening,
                quantity=quantity,
                total=total,
                selected_seats=selected_payload,
            )
            purchase.full_clean()
            purchase.save()
            sold_seats = [
                SeatPurchase(purchase=purchase, screening=screening, label=seat["label"])
                for seat in selected_payload
            ]
            try:
                SeatPurchase.objects.bulk_create(sold_seats)
            except IntegrityError:
                raise ValidationError(
                    {"quantity": "Algunos asientos seleccionados ya no estan disponibles."}
                )
            if selected_payload:
                SeatReservation.objects.filter(
                    screening=screening,
                    user=user,
                    label__in=[seat["label"] for seat in selected_payload],
                ).delete()
            return purchase

    def clean(self):
        super().clean()
        if self.quantity < 1:
            raise ValidationError({"quantity": "Elegi al menos una entrada."})

        if not self.pk and self.screening.status != Screening.Status.PUBLISHED:
            raise ValidationError("Esta funcion no tiene entradas a la venta.")

        available = self.available_for(self.screening)
        if self.pk:
            available += self.quantity
        if self.quantity > available:
            raise ValidationError(
                {
                    "quantity": (
                        f"Solo tenemos disponibles {available} entradas "
                        "para esta funcion."
                    )
                }
            )

    def save(self, *args, **kwargs):
        if self.screening_id and self.quantity and self.total in (None, ""):
            self.total = self.screening.price_from * self.quantity
        super().save(*args, **kwargs)


class SeatPurchase(models.Model):
    purchase = models.ForeignKey(
        TicketPurchase,
        on_delete=models.CASCADE,
        related_name="sold_seats",
        db_column="compra_id",
    )
    screening = models.ForeignKey(
        Screening,
        on_delete=models.CASCADE,
        related_name="sold_seats",
        db_column="funcion_id",
    )
    label = models.CharField(max_length=12)
    created_at = models.DateTimeField(auto_now_add=True, db_column="creada_en")
    used_at = models.DateTimeField(null=True, blank=True, db_column="utilizada_en")

    class Meta:
        verbose_name = "Asiento vendido"
        verbose_name_plural = "Asientos vendidos"
        db_table = "tickets_compraasiento"
        constraints = [
            models.UniqueConstraint(
                fields=["screening", "label"],
                name="unique_sold_seat_per_screening",
            )
        ]

    def __str__(self):
        return f"{self.screening} - {self.label}"


class SeatReservation(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="seat_reservations",
        db_column="usuario_id",
    )
    screening = models.ForeignKey(
        Screening,
        on_delete=models.CASCADE,
        related_name="seat_reservations",
        db_column="funcion_id",
    )
    label = models.CharField(max_length=12)
    expires_at = models.DateTimeField(db_column="expira_en")
    created_at = models.DateTimeField(auto_now_add=True, db_column="creada_en")
    updated_at = models.DateTimeField(auto_now=True, db_column="actualizada_en")

    class Meta:
        verbose_name = "Reserva temporal de asiento"
        verbose_name_plural = "Reservas temporales de asientos"
        db_table = "tickets_reservaasiento"
        constraints = [
            models.UniqueConstraint(
                fields=["screening", "label"],
                name="unique_reserved_seat_per_screening",
            )
        ]

    def __str__(self):
        return f"{self.user} - {self.screening} - {self.label}"

    @classmethod
    def duration(cls):
        minutes = CinemaSettings.current().seat_reservation_minutes or 5
        return timedelta(minutes=minutes)

    @classmethod
    def clear_expired(cls):
        return cls.objects.filter(expires_at__lte=timezone.now()).delete()

    @classmethod
    def active_for(cls, screening):
        cls.clear_expired()
        return cls.objects.filter(screening=screening, expires_at__gt=timezone.now())

    @classmethod
    def reserve(cls, user, screening, label):
        with transaction.atomic():
            screening = Screening.objects.select_for_update().get(pk=screening.pk)
            cls.clear_expired()
            TicketPurchase.sync_sold_seats(screening)
            if label not in TicketPurchase.seat_prices(screening):
                raise ValidationError("La butaca no es valida para esta funcion.")
            if SeatPurchase.objects.filter(screening=screening, label=label).exists():
                raise ValidationError("La butaca ya fue comprada.")

            reservation = cls.objects.select_for_update().filter(
                screening=screening,
                label=label,
            ).first()
            expiration = timezone.now() + cls.duration()
            if reservation and reservation.user_id != user.pk and reservation.expires_at > timezone.now():
                raise ValidationError("La butaca esta reservada temporalmente.")
            if reservation:
                reservation.user = user
                reservation.expires_at = expiration
                reservation.save(update_fields=["user", "expires_at", "updated_at"])
            else:
                reservation = cls.objects.create(
                    user=user,
                    screening=screening,
                    label=label,
                    expires_at=expiration,
                )
            return reservation

    @classmethod
    def release(cls, user, screening, label):
        cls.objects.filter(user=user, screening=screening, label=label).delete()
