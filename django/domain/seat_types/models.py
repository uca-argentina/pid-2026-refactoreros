from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models


class SeatType(models.Model):
    name = models.CharField(max_length=100, unique=True, db_column="nombre")
    base_price = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        db_column="precio_base",
    )
    color = models.CharField(max_length=7)
    icon = models.ImageField(upload_to="seat_icons/", blank=True, db_column="icono")

    class Meta:
        verbose_name = "Tipo de Asiento"
        verbose_name_plural = "Tipos de Asientos"
        ordering = ["name"]

    def __str__(self):
        return self.name
