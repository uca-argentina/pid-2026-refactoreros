from django.db import models


class Room(models.Model):
    name = models.CharField(max_length=100, unique=True, db_column="nombre")
    layout_configuration = models.JSONField(default=dict, blank=True, db_column="layout_configuracion")

    class Meta:
        verbose_name = "Sala"
        verbose_name_plural = "Salas"
        db_table = "rooms_sala"
        ordering = ["name"]

    @property
    def capacity(self):
        if hasattr(self, "_capacity"):
            return self._capacity
        return self.seats.count() if self.pk else 0

    def __str__(self):
        return f"{self.name} (cap. {self.capacity})"
