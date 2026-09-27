from django.db import models
from domain.rooms.models import Sala


class Seat(models.Model):

    sala        = models.ForeignKey(Sala, on_delete=models.CASCADE, related_name="asientos")
    fila        = models.PositiveIntegerField()
    columna     = models.PositiveIntegerField()
    precio_base = models.DecimalField(max_digits=8, decimal_places=2)
    
    class Meta:
        verbose_name = "Asiento"
        verbose_name_plural = "Asientos"
        ordering = ["sala"]