from django.db import models


class Sala(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    layout_configuracion = models.JSONField(default=dict, blank=True)
    
    class Meta:
        verbose_name = "Sala"
        verbose_name_plural = "Salas"
        ordering = ["nombre"]

    @property
    def capacidad(self):
        if hasattr(self, "_capacidad"):
            return self._capacidad
        return self.seats.count() if self.pk else 0

    def __str__(self):
        return f"{self.nombre} (cap. {self.capacidad})"
