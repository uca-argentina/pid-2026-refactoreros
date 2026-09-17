from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from domain.movies.models import Pelicula
from domain.rooms.models import Sala


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

    @property
    def fecha_fin(self):
        return self.fecha_horario + timedelta(minutes=self.pelicula.duracion_minutos)

    def clean(self):
        super().clean()
        errors = {}

        if self.precio_entrada is not None and self.precio_entrada <= 0:
            errors["precio_entrada"] = "El precio de entrada debe ser mayor a cero."

        if self.fecha_horario and self.fecha_horario <= timezone.now():
            errors["fecha_horario"] = "La fecha y horario deben ser futuros."

        if errors:
            raise ValidationError(errors)

        if not self.pelicula_id or not self.sala_id or not self.fecha_horario:
            return

        inicio = self.fecha_horario
        fin = self.fecha_fin
        funciones_misma_sala = (
            Funcion.objects.filter(sala=self.sala)
            .select_related("pelicula")
            .exclude(pk=self.pk)
        )

        for funcion in funciones_misma_sala:
            if funcion.fecha_horario < fin and funcion.fecha_fin > inicio:
                raise ValidationError(
                    "La sala ya tiene una funcion programada en ese horario."
                )

    @classmethod
    def funciones_publicadas(cls):
        return cls.objects.filter(publicada=True).select_related("pelicula", "sala")
