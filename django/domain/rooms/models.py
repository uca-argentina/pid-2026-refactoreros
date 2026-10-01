from django.db import models


class Sala(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    capacidad = models.PositiveIntegerField(default=0)
    layout_configuracion = models.JSONField(default=dict, blank=True)
    precio_configuracion = models.JSONField(default=dict, blank=True)
    
    class Meta:
        verbose_name = "Sala"
        verbose_name_plural = "Salas"
        ordering = ["nombre"]

    def __str__(self):
        return f"{self.nombre} (cap. {self.capacidad})"
