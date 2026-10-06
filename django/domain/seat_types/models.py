from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal


class SeatType(models.Model):
    nombre      = models.CharField(max_length=100, unique=True)
    precio_base = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    color       = models.CharField(max_length=7)
    icono       = models.ImageField(upload_to="seat_icons/",blank=True)
    
    class Meta:
        verbose_name = "Tipo de Asiento"
        verbose_name_plural = "Tipos de Asientos"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre
