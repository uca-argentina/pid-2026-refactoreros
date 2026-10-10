from django.db import models

from domain.rooms.models import Room
from domain.seat_types.models import SeatType


class Seat(models.Model):
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="seats", db_column="sala_id")
    row = models.PositiveIntegerField(db_column="fila")
    column = models.PositiveIntegerField(db_column="columna")
    seat_type = models.ForeignKey(SeatType, on_delete=models.PROTECT, related_name="seats", db_column="tipo_id")

    class Meta:
        verbose_name = "Asiento"
        verbose_name_plural = "Asientos"
        ordering = ["room"]
