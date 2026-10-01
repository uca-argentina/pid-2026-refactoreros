from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Sum

from domain.screenings.models import Funcion


def index_to_letters(index):
    label = ""
    value = index + 1
    while value > 0:
        value, remainder = divmod(value - 1, 26)
        label = chr(65 + remainder) + label
    return label


class CompraEntrada(models.Model):
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="compras_entradas",
    )
    funcion = models.ForeignKey(
        Funcion,
        on_delete=models.CASCADE,
        related_name="compras_entradas",
    )
    cantidad = models.PositiveIntegerField()
    total = models.DecimalField(max_digits=10, decimal_places=2)
    asientos_seleccionados = models.JSONField(default=list, blank=True)
    creada_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Compra de entrada"
        verbose_name_plural = "Compras de entradas"
        ordering = ["-creada_en"]

    def __str__(self):
        return f"{self.usuario} - {self.funcion} x{self.cantidad}"

    @property
    def asientos_label(self):
        labels = self._labels_from_selected_seats(self.asientos_seleccionados)
        return ", ".join(labels)

    @classmethod
    def cantidad_vendida(cls, funcion):
        return (
            cls.objects.filter(funcion=funcion).aggregate(total=Sum("cantidad"))["total"]
            or 0
        )

    @classmethod
    def disponibles_para(cls, funcion):
        return max(funcion.capacidad_disponible - cls.cantidad_vendida(funcion), 0)

    @classmethod
    def precios_por_asiento(cls, funcion):
        snapshot = funcion.sala_configuracion_snapshot or {}
        if isinstance(snapshot, dict):
            seats = snapshot.get("seats", [])
            columns_count = snapshot.get("columns") or max(
                (seat["column"] for seat in seats), default=-1
            ) + 1
        else:
            seats = snapshot
            columns_count = max((seat["column"] for seat in seats), default=-1) + 1

        occupied_columns = {seat["column"] for seat in seats}
        column_labels = {}
        next_column_label = 0
        for column_index in range(columns_count):
            if column_index in occupied_columns:
                column_labels[column_index] = index_to_letters(next_column_label)
                next_column_label += 1

        prices = {}
        for seat in seats:
            column_label = column_labels.get(seat["column"], "")
            if not column_label:
                continue
            label = f"{seat['row'] + 1}{column_label}"
            prices[label] = funcion.precio_para_tipo(seat.get("type_id"))
        return prices

    @classmethod
    def _labels_from_selected_seats(cls, selected_seats):
        labels = []
        for seat in selected_seats or []:
            label = seat.get("label") if isinstance(seat, dict) else str(seat)
            if label and label not in labels:
                labels.append(label)
        return labels

    @classmethod
    def asientos_ocupados(cls, funcion):
        compras = cls.objects.filter(funcion=funcion)
        occupied_labels = []
        legacy_sold_count = 0
        for compra in compras:
            labels = cls._labels_from_selected_seats(compra.asientos_seleccionados)
            if labels:
                for label in labels:
                    if label not in occupied_labels:
                        occupied_labels.append(label)
            else:
                legacy_sold_count += compra.cantidad

        if legacy_sold_count:
            for label in cls.precios_por_asiento(funcion):
                if label in occupied_labels:
                    continue
                occupied_labels.append(label)
                legacy_sold_count -= 1
                if legacy_sold_count <= 0:
                    break

        return set(occupied_labels)

    @classmethod
    def total_para_asientos(cls, funcion, selected_seats):
        seat_prices = cls.precios_por_asiento(funcion)
        labels = cls._labels_from_selected_seats(selected_seats)

        if not labels:
            return None, 0, []

        invalid_labels = [label for label in labels if label not in seat_prices]
        if invalid_labels:
            raise ValidationError({"cantidad": "La seleccion de asientos no es valida."})

        selected_payload = [
            {"label": label, "price": str(seat_prices[label])}
            for label in labels
        ]
        return sum(seat_prices[label] for label in labels), len(labels), selected_payload

    @classmethod
    def comprar(cls, usuario, funcion, cantidad, selected_seats=None):
        with transaction.atomic():
            cantidad = int(cantidad)
            funcion = Funcion.objects.select_for_update().select_related("sala").get(
                pk=funcion.pk
            )
            list(cls.objects.select_for_update().filter(funcion=funcion))
            total_asientos, cantidad_asientos, selected_payload = cls.total_para_asientos(
                funcion, selected_seats
            )
            if selected_payload:
                occupied_labels = cls.asientos_ocupados(funcion)
                already_taken = [
                    seat["label"]
                    for seat in selected_payload
                    if seat["label"] in occupied_labels
                ]
                if already_taken:
                    raise ValidationError(
                        {"cantidad": "Algunos asientos seleccionados ya no estan disponibles."}
                    )
            if cantidad_asientos:
                cantidad = cantidad_asientos
            total = total_asientos if total_asientos is not None else funcion.precio_desde * cantidad
            compra = cls(
                usuario=usuario,
                funcion=funcion,
                cantidad=cantidad,
                total=total,
                asientos_seleccionados=selected_payload,
            )
            compra.full_clean()
            compra.save()
            return compra

    def clean(self):
        super().clean()
        if self.cantidad < 1:
            raise ValidationError({"cantidad": "Elegí al menos una entrada."})

        disponibles = self.disponibles_para(self.funcion)
        if self.pk:
            disponibles += self.cantidad
        if self.cantidad > disponibles:
            raise ValidationError(
                {
                    "cantidad": (
                        f"Solo tenemos disponibles {disponibles} entradas "
                        "para esta función."
                    )
                }
            )

    def save(self, *args, **kwargs):
        if self.funcion_id and self.cantidad and self.total in (None, ""):
            self.total = self.funcion.precio_desde * self.cantidad
        super().save(*args, **kwargs)
