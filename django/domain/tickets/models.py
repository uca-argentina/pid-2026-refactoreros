from datetime import timedelta
import hashlib
import secrets
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction
from django.utils import timezone

from domain.cinema.models import CinemaSettings
from domain.promotions.pricing import PromotionPriceCalculator
from domain.screenings.models import Screening

TICKET_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generate_ticket_code():
    """Legacy migration default for the former plaintext code column."""
    return "".join(secrets.choice(TICKET_CODE_ALPHABET) for _ in range(6))


def generate_ticket_token():
    """Persistent random source for the reservation code, independent from IDs."""
    return secrets.token_urlsafe(24)


def reservation_code_for_token(token):
    """Return a stable, human-readable code for a persisted purchase token.

    The token is already random and unique.  Deriving the short display code
    from it (rather than from ``SECRET_KEY``) keeps existing tickets usable
    after a routine Django secret-key rotation.
    """
    digest = hashlib.sha256(f"ticket-reservation-code:{token}".encode()).digest()
    return "".join(TICKET_CODE_ALPHABET[byte % len(TICKET_CODE_ALPHABET)] for byte in digest[:6])


def reservation_code_digest(code):
    """Indexed server-side representation of a short reservation code."""
    return hashlib.sha256(
        f"ticket-reservation-lookup:{code.upper()}".encode()
    ).hexdigest()


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
    validation_code_digest = models.CharField(max_length=64, unique=True, editable=False)
    validation_token = models.CharField(max_length=32, unique=True, default=generate_ticket_token, editable=False)

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

    @property
    def validation_code(self):
        return reservation_code_for_token(self.validation_token)

    @property
    def qr_payload(self):
        return f"BC2:{self.validation_code}"

    @property
    def used_quantity(self):
        return self.tickets.filter(used_at__isnull=False).count()

    @property
    def remaining_quantity(self):
        return self.quantity - self.used_quantity

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
    def seat_price_quotes(cls, screening, price_calculator=None):
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

        calculator = price_calculator or PromotionPriceCalculator.current()
        quotes = {}
        for seat in seats:
            column_label = column_labels.get(seat["column"], "")
            if not column_label:
                continue
            label = f"{seat['row'] + 1}{column_label}"
            quotes[label] = calculator.quote(
                base_price=screening.price_for_type(seat.get("type_id")),
                seat_type_id=seat.get("type_id"),
                screening_starts_at=screening.starts_at,
            )
        return quotes

    @classmethod
    def seat_prices(cls, screening):
        return {
            label: quote.final_price
            for label, quote in cls.seat_price_quotes(screening).items()
        }

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
        seat_quotes = cls.seat_price_quotes(screening)
        labels = cls._labels_from_selected_seats(selected_seats)

        if not labels:
            return None, 0, []

        invalid_labels = [label for label in labels if label not in seat_quotes]
        if invalid_labels:
            raise ValidationError({"quantity": "La seleccion de asientos no es valida."})

        selected_payload = []
        for label in labels:
            quote = seat_quotes[label]
            selected_payload.append(
                {
                    "label": label,
                    "price": str(quote.final_price),
                    "base_price": str(quote.base_price),
                    "discount": str(quote.discount),
                    "promotion": quote.promotion.name if quote.promotion else "",
                }
            )
        return (
            sum(seat_quotes[label].final_price for label in labels),
            len(labels),
            selected_payload,
        )

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
        creating = self._state.adding
        for attempt in range(32 if creating else 1):
            if not self.validation_token or (creating and attempt):
                self.validation_token = generate_ticket_token()
            self.validation_code_digest = reservation_code_digest(self.validation_code)
            try:
                with transaction.atomic():
                    super().save(*args, **kwargs)
                    if creating:
                        labels = self._labels_from_selected_seats(self.selected_seats)
                        AdmissionTicket.objects.bulk_create([
                            AdmissionTicket(
                                purchase=self, number=index + 1,
                                seat_label=labels[index] if index < len(labels) else "",
                            )
                            for index in range(self.quantity)
                        ])
                return
            except IntegrityError:
                if not creating:
                    raise
                # A short code collision is unlikely but must not fail a sale.
                # The database constraint also covers concurrent purchases.
                collision = TicketPurchase.objects.filter(
                    models.Q(validation_token=self.validation_token)
                    | models.Q(validation_code_digest=self.validation_code_digest)
                ).exists()
                if not collision:
                    raise
                self.pk = None
                self._state.adding = True
        raise RuntimeError("No se pudo generar un código de reserva único.")

class AdmissionTicket(models.Model):
    purchase = models.ForeignKey(TicketPurchase, on_delete=models.CASCADE, related_name="tickets")
    number = models.PositiveIntegerField()
    seat_label = models.CharField(max_length=12, blank=True)
    code = models.CharField(max_length=32, unique=True, default=generate_ticket_token, editable=False)
    used_at = models.DateTimeField(null=True, blank=True, editable=False)
    used_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                on_delete=models.SET_NULL, related_name="validated_tickets", editable=False)

    class Meta:
        ordering = ["number"]
        verbose_name = "Entrada individual"
        verbose_name_plural = "Entradas individuales"
        constraints = [models.UniqueConstraint(fields=["purchase", "number"], name="unique_ticket_number_per_purchase")]

    @property
    def qr_payload(self):
        return f"BC1:{self.code}"

    def __str__(self):
        return f"Compra #{self.purchase_id} · Entrada {self.number}"


class AdmissionValidation(models.Model):
    """An operator's reversible, auditable admission action."""

    purchase = models.ForeignKey(TicketPurchase, on_delete=models.CASCADE, related_name="admission_validations")
    operator = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
                                 related_name="admission_validations")
    tickets = models.ManyToManyField(AdmissionTicket, related_name="validation_events")
    created_at = models.DateTimeField(auto_now_add=True)
    reverted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["operator", "-created_at"], name="admission_operator_recent_idx"),
        ]
        verbose_name = "Validación de ingreso"
        verbose_name_plural = "Validaciones de ingreso"

    @property
    def can_undo(self):
        return (
            self.reverted_at is None
            and self.created_at >= timezone.now() - timedelta(seconds=CinemaSettings.current().admission_undo_seconds)
        )


class PurchaseRefund(models.Model):
    purchase = models.OneToOneField(TicketPurchase, on_delete=models.CASCADE, related_name="refund")
    reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    notice = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    email_sent_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Devolución"
        verbose_name_plural = "Devoluciones"

    def __str__(self):
        return f"Devolución · Compra #{self.purchase_id}"


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
