from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from domain.movies.models import Pelicula
from domain.rooms.models import Sala


class Funcion(models.Model):
    class Estado(models.TextChoices):
        BORRADOR = "borrador", "Borrador"
        PROGRAMADA = "programada", "Programada"
        PUBLICADA = "publicada", "Publicada"
        CANCELADA = "cancelada", "Cancelada"
        FINALIZADA = "finalizada", "Finalizada"

    TRANSICIONES = {
        Estado.BORRADOR: (Estado.PROGRAMADA,),
        Estado.PROGRAMADA: (Estado.BORRADOR, Estado.PUBLICADA, Estado.CANCELADA),
        Estado.PUBLICADA: (Estado.PROGRAMADA, Estado.CANCELADA),
        Estado.CANCELADA: (),
        Estado.FINALIZADA: (),
    }

    pelicula = models.ForeignKey(
        Pelicula, on_delete=models.CASCADE, related_name="funciones"
    )
    sala = models.ForeignKey(Sala, on_delete=models.CASCADE, related_name="funciones")
    fecha_horario = models.DateTimeField()
    estado = models.CharField(
        max_length=20, choices=Estado.choices, default=Estado.BORRADOR
    )
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

    @property
    def tiene_ventas(self):
        vendidas = getattr(self, "entradas_vendidas", None)
        if vendidas is not None:
            return vendidas > 0
        return self.compras_entradas.exists()

    @property
    def es_editable(self):
        if self.estado in (self.Estado.BORRADOR, self.Estado.PROGRAMADA):
            return True
        return self.estado == self.Estado.PUBLICADA and not self.tiene_ventas

    @property
    def es_eliminable(self):
        return self.estado in (self.Estado.BORRADOR, self.Estado.PROGRAMADA)

    def puede_pasar_a(self, nuevo_estado):
        if nuevo_estado not in self.TRANSICIONES[self.estado]:
            return False
        if (
            self.estado == self.Estado.PUBLICADA
            and nuevo_estado == self.Estado.PROGRAMADA
        ):
            return not self.tiene_ventas
        return True

    @property
    def transiciones_disponibles(self):
        return [
            estado
            for estado in self.TRANSICIONES[self.estado]
            if self.puede_pasar_a(estado)
        ]

    def cambiar_estado(self, nuevo_estado):
        if not self.puede_pasar_a(nuevo_estado):
            raise ValidationError(
                f"No se puede pasar una función {self.get_estado_display().lower()} "
                f"a {self.Estado(nuevo_estado).label.lower()}."
            )
        if (
            nuevo_estado in (self.Estado.PROGRAMADA, self.Estado.PUBLICADA)
            and self.fecha_horario <= timezone.now()
        ):
            raise ValidationError(
                "No se puede programar ni publicar una función con fecha pasada."
            )
        self.estado = nuevo_estado
        self.save(update_fields=["estado"])

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
            .exclude(estado=self.Estado.CANCELADA)
            .select_related("pelicula")
            .exclude(pk=self.pk)
        )

        for funcion in funciones_misma_sala:
            if funcion.fecha_horario < fin and funcion.fecha_fin > inicio:
                raise ValidationError(
                    "La sala ya tiene una funcion programada en ese horario."
                )

    @classmethod
    def finalizar_vencidas(cls):
        ahora = timezone.now()
        candidatas = cls.objects.filter(
            estado__in=(cls.Estado.PROGRAMADA, cls.Estado.PUBLICADA),
            fecha_horario__lte=ahora,
        ).select_related("pelicula")
        vencidas = [funcion.pk for funcion in candidatas if funcion.fecha_fin <= ahora]
        if vencidas:
            cls.objects.filter(pk__in=vencidas).update(estado=cls.Estado.FINALIZADA)

    @classmethod
    def funciones_publicadas(cls):
        return cls.objects.filter(estado=cls.Estado.PUBLICADA).select_related(
            "pelicula", "sala"
        )
