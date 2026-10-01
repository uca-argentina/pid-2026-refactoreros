from datetime import timedelta
from decimal import Decimal, InvalidOperation

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
    precios_por_tipo = models.JSONField(default=dict, blank=True)
    sala_configuracion_snapshot = models.JSONField(default=list, blank=True)
    capacidad_snapshot = models.PositiveIntegerField(default=0)

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
    def capacidad_disponible(self):
        return self.capacidad_snapshot or self.sala.capacidad

    @property
    def precio_desde(self):
        prices = [Decimal(str(price)) for price in (self.precios_por_tipo or {}).values()]
        if prices:
            return min(prices)
        return self.precio_entrada

    def precio_para_tipo(self, type_id):
        price = (self.precios_por_tipo or {}).get(str(type_id))
        if price is not None:
            return Decimal(str(price))
        return self.precio_entrada

    def capturar_configuracion_sala(self):
        seats = (
            self.sala.seats.select_related("tipo")
            .order_by("fila", "columna")
        )
        price_config = self.precios_por_tipo or self.sala.precio_configuracion or {}
        seat_snapshot = []
        for seat in seats:
            seat_price = price_config.get(str(seat.tipo_id), str(seat.tipo.precio_base))
            seat_snapshot.append({
                "row": seat.fila,
                "column": seat.columna,
                "type": seat.tipo.nombre,
                "type_id": seat.tipo_id,
                "price": str(seat_price),
                "color": seat.tipo.color,
            })
        layout = self.sala.layout_configuracion or {}
        rows = layout.get("rows") or max((seat["row"] for seat in seat_snapshot), default=-1) + 1
        columns = layout.get("columns") or max((seat["column"] for seat in seat_snapshot), default=-1) + 1
        snapshot = {
            "rows": rows,
            "columns": columns,
            "seats": seat_snapshot,
        }
        self.sala_configuracion_snapshot = snapshot
        self.capacidad_snapshot = len(seat_snapshot) if seat_snapshot else self.sala.capacidad
        if price_config:
            self.precios_por_tipo = {
                str(type_id): str(price)
                for type_id, price in price_config.items()
            }
            self.precio_entrada = min(Decimal(str(price)) for price in self.precios_por_tipo.values())

    def save(self, *args, **kwargs):
        if self.sala_id and not self.capacidad_snapshot:
            self.capturar_configuracion_sala()
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        errors = {}

        if self.precios_por_tipo:
            for price in self.precios_por_tipo.values():
                try:
                    normalized_price = Decimal(str(price))
                except (InvalidOperation, TypeError, ValueError):
                    errors["precios_por_tipo"] = "Todos los precios por tipo de asiento deben ser numericos."
                    break
                if normalized_price <= 0:
                    errors["precios_por_tipo"] = "Todos los precios por tipo de asiento deben ser mayores a cero."
                    break
        elif self.precio_entrada is not None and self.precio_entrada <= 0:
            errors["precio_entrada"] = "El precio debe ser mayor a cero."

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
