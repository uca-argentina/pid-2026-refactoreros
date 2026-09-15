from django.db import models

from movies.models import Pelicula
from rooms.models import Sala


class Funcion(models.Model):
    pelicula = models.ForeignKey(
        Pelicula, on_delete=models.CASCADE, related_name="funciones"
    )
    sala = models.ForeignKey(Sala, on_delete=models.CASCADE, related_name="funciones")
    fecha_horario = models.DateTimeField()
    publicada = models.BooleanField(default=False)
    precio_entrada = models.DecimalField(max_digits=8, decimal_places=2)

    class Meta:
        verbose_name = "Función"
        verbose_name_plural = "Funciones"
        ordering = ["fecha_horario"]

    def __str__(self):
        return f"{self.pelicula.titulo} - {self.sala.nombre} - {self.fecha_horario:%d/%m/%Y %H:%M}"