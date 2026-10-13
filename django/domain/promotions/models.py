from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class Promotion(models.Model):
    class DiscountType(models.TextChoices):
        PERCENTAGE = "percentage", "Porcentaje"
        FIXED = "fixed", "Monto fijo"

    class Weekday(models.IntegerChoices):
        MONDAY = 0, "Lunes"
        TUESDAY = 1, "Martes"
        WEDNESDAY = 2, "Miércoles"
        THURSDAY = 3, "Jueves"
        FRIDAY = 4, "Viernes"
        SATURDAY = 5, "Sábado"
        SUNDAY = 6, "Domingo"

    name = models.CharField(max_length=100, unique=True, db_column="nombre")
    is_active = models.BooleanField(default=True, db_column="activa")
    discount_type = models.CharField(
        max_length=12,
        choices=DiscountType.choices,
        default=DiscountType.PERCENTAGE,
        db_column="tipo_descuento",
    )
    discount_value = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        db_column="valor_descuento",
    )
    weekdays = models.JSONField(default=list, blank=True, db_column="dias_semana")
    starts_at = models.TimeField(null=True, blank=True, db_column="horario_desde")
    ends_at = models.TimeField(null=True, blank=True, db_column="horario_hasta")
    seat_types = models.ManyToManyField(
        "seat_types.SeatType",
        blank=True,
        related_name="promotions",
        verbose_name="tipos de butaca",
    )

    class Meta:
        verbose_name = "promoción"
        verbose_name_plural = "promociones"
        db_table = "promotions_promocion"
        ordering = ("-is_active", "name")

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        errors = {}
        if self.discount_type == self.DiscountType.PERCENTAGE and self.discount_value > 100:
            errors["discount_value"] = "El descuento porcentual no puede superar el 100%."
        if bool(self.starts_at) != bool(self.ends_at):
            errors["starts_at"] = "Indicá ambos horarios o dejá los dos vacíos."
        valid_weekdays = {choice.value for choice in self.Weekday}
        if any(day not in valid_weekdays for day in self.weekdays or []):
            errors["weekdays"] = "Elegí días de la semana válidos."
        if errors:
            raise ValidationError(errors)

    @property
    def discount_label(self):
        if self.discount_type == self.DiscountType.PERCENTAGE:
            value = format(self.discount_value.normalize(), "f").rstrip("0").rstrip(".")
            return f"{value}%"
        return f"${self.discount_value:.2f}"

    @property
    def weekdays_label(self):
        if not self.weekdays:
            return "Todos los días"
        labels = dict(self.Weekday.choices)
        return ", ".join(labels[int(day)] for day in self.weekdays)

    @property
    def schedule_label(self):
        if not self.starts_at:
            return "Todo el día"
        return f"{self.starts_at:%H:%M} a {self.ends_at:%H:%M}"

    @property
    def seat_types_label(self):
        seat_types = list(self.seat_types.all())
        return ", ".join(seat_type.name for seat_type in seat_types) or "Todos los tipos"

    def applies_to(self, seat_type_id, screening_starts_at):
        """Return whether this rule applies to a seat in the scheduled screening."""
        if not self.is_active:
            return False

        local_start = timezone.localtime(screening_starts_at)
        weekdays = {int(day) for day in self.weekdays or []}
        if weekdays and local_start.weekday() not in weekdays:
            return False

        if self.starts_at and self.ends_at:
            screening_time = local_start.timetz().replace(tzinfo=None)
            if self.starts_at <= self.ends_at:
                if not self.starts_at <= screening_time <= self.ends_at:
                    return False
            elif not (screening_time >= self.starts_at or screening_time <= self.ends_at):
                return False

        selected_types = {seat_type.pk for seat_type in self.seat_types.all()}
        return not selected_types or seat_type_id in selected_types

    def discounted_price(self, base_price):
        base_price = Decimal(str(base_price))
        if self.discount_type == self.DiscountType.PERCENTAGE:
            discounted = base_price * (Decimal("100") - self.discount_value) / Decimal("100")
        else:
            discounted = base_price - self.discount_value
        return max(discounted, Decimal("0")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
