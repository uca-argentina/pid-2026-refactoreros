from django.db import models


class Sala(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    capacidad = models.PositiveIntegerField()

    class Meta:
        verbose_name = "Sala"
        verbose_name_plural = "Salas"
        ordering = ["nombre"]

    def __str__(self):
        return f"{self.nombre} (cap. {self.capacidad})"