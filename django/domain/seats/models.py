from django.db import models
from domain.rooms.models import Sala
from domain.seat_types.models import SeatType

class Seat(models.Model):

    sala        = models.ForeignKey(Sala, on_delete=models.CASCADE, related_name="seats")
    fila        = models.PositiveIntegerField()
    columna     = models.PositiveIntegerField()
    tipo        = models.ForeignKey(SeatType, on_delete=models.CASCADE, related_name="seats")
    
    class Meta:
        verbose_name = "Asiento"
        verbose_name_plural = "Asientos"
        ordering = ["sala"]