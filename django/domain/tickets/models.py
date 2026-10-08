from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction
from django.utils import timezone
from datetime import timedelta

from domain.cinema.models import ConfiguracionCine
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
        cls.sincronizar_asientos_vendidos(funcion)
        sold_seats = CompraAsiento.objects.filter(funcion=funcion).count()
        legacy_total = 0
        legacy_compras = cls.objects.filter(funcion=funcion, asientos_seleccionados=[]).prefetch_related(
            "asientos_vendidos"
        )
        for compra in legacy_compras:
            legacy_total += max(compra.cantidad - compra.asientos_vendidos.count(), 0)
        return sold_seats + legacy_total

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
        cls.sincronizar_asientos_vendidos(funcion)
        return set(CompraAsiento.objects.filter(funcion=funcion).values_list("label", flat=True))

    @classmethod
    def asientos_bloqueados(cls, funcion, usuario=None):
        occupied = cls.asientos_ocupados(funcion)
        reserved = ReservaAsiento.vigentes_para(funcion).exclude(usuario=usuario)
        return occupied | set(reserved.values_list("label", flat=True))

    @classmethod
    def sincronizar_asientos_vendidos(cls, funcion):
        compras = cls.objects.filter(funcion=funcion)
        legacy_compras = []
        legacy_sold_count = 0
        for compra in compras:
            labels = cls._labels_from_selected_seats(compra.asientos_seleccionados)
            if labels:
                for label in labels:
                    CompraAsiento.objects.get_or_create(
                        compra=compra,
                        funcion=funcion,
                        label=label,
                    )
            else:
                assigned_count = CompraAsiento.objects.filter(compra=compra).count()
                remaining = max(compra.cantidad - assigned_count, 0)
                if remaining:
                    legacy_compras.append({"compra": compra, "remaining": remaining})
                    legacy_sold_count += remaining

        if legacy_sold_count:
            occupied_labels = set(
                CompraAsiento.objects.filter(funcion=funcion).values_list("label", flat=True)
            )
            legacy_index = 0
            legacy_remaining = legacy_compras[legacy_index]["remaining"] if legacy_compras else 0
            for label in cls.precios_por_asiento(funcion):
                if label in occupied_labels:
                    continue
                while legacy_compras and legacy_remaining <= 0:
                    legacy_index += 1
                    if legacy_index >= len(legacy_compras):
                        break
                    legacy_remaining = legacy_compras[legacy_index]["remaining"]
                if legacy_index >= len(legacy_compras):
                    break
                CompraAsiento.objects.get_or_create(
                    compra=legacy_compras[legacy_index]["compra"],
                    funcion=funcion,
                    label=label,
                )
                occupied_labels.add(label)
                legacy_remaining -= 1
                legacy_sold_count -= 1
                if legacy_sold_count <= 0:
                    break

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
    def comprar(cls, usuario, funcion, cantidad, selected_seats=None, require_reservation=False):
        with transaction.atomic():
            cantidad = int(cantidad)
            funcion = Funcion.objects.select_for_update().select_related("sala").get(
                pk=funcion.pk
            )
            ReservaAsiento.limpiar_expiradas()
            list(cls.objects.select_for_update().filter(funcion=funcion))
            list(CompraAsiento.objects.select_for_update().filter(funcion=funcion))
            list(ReservaAsiento.objects.select_for_update().filter(funcion=funcion))
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
                if require_reservation:
                    reserved_by_user = set(
                        ReservaAsiento.vigentes_para(funcion)
                        .filter(usuario=usuario)
                        .values_list("label", flat=True)
                    )
                    missing_reservations = [
                        seat["label"]
                        for seat in selected_payload
                        if seat["label"] not in reserved_by_user
                    ]
                    if missing_reservations:
                        raise ValidationError(
                            {"cantidad": "Algunas butacas ya no estan reservadas para tu compra."}
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
            sold_seats = [
                CompraAsiento(compra=compra, funcion=funcion, label=seat["label"])
                for seat in selected_payload
            ]
            try:
                CompraAsiento.objects.bulk_create(sold_seats)
            except IntegrityError:
                raise ValidationError(
                    {"cantidad": "Algunos asientos seleccionados ya no estan disponibles."}
                )
            if selected_payload:
                ReservaAsiento.objects.filter(
                    funcion=funcion,
                    usuario=usuario,
                    label__in=[seat["label"] for seat in selected_payload],
                ).delete()
            return compra

    def clean(self):
        super().clean()
        if self.cantidad < 1:
            raise ValidationError({"cantidad": "Elegí al menos una entrada."})

        if not self.pk and self.funcion.estado != Funcion.Estado.PUBLICADA:
            raise ValidationError("Esta función no tiene entradas a la venta.")

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


class CompraAsiento(models.Model):
    compra = models.ForeignKey(
        CompraEntrada,
        on_delete=models.CASCADE,
        related_name="asientos_vendidos",
    )
    funcion = models.ForeignKey(
        Funcion,
        on_delete=models.CASCADE,
        related_name="asientos_vendidos",
    )
    label = models.CharField(max_length=12)
    creada_en = models.DateTimeField(auto_now_add=True)
    utilizada_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Asiento vendido"
        verbose_name_plural = "Asientos vendidos"
        constraints = [
            models.UniqueConstraint(
                fields=["funcion", "label"],
                name="unique_sold_seat_per_screening",
            )
        ]

    def __str__(self):
        return f"{self.funcion} - {self.label}"


class ReservaAsiento(models.Model):
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reservas_asientos",
    )
    funcion = models.ForeignKey(
        Funcion,
        on_delete=models.CASCADE,
        related_name="reservas_asientos",
    )
    label = models.CharField(max_length=12)
    expira_en = models.DateTimeField()
    creada_en = models.DateTimeField(auto_now_add=True)
    actualizada_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Reserva temporal de asiento"
        verbose_name_plural = "Reservas temporales de asientos"
        constraints = [
            models.UniqueConstraint(
                fields=["funcion", "label"],
                name="unique_reserved_seat_per_screening",
            )
        ]

    def __str__(self):
        return f"{self.usuario} - {self.funcion} - {self.label}"

    @classmethod
    def duracion(cls):
        minutos = ConfiguracionCine.actual().reserva_asientos_minutos or 5
        return timedelta(minutes=minutos)

    @classmethod
    def limpiar_expiradas(cls):
        return cls.objects.filter(expira_en__lte=timezone.now()).delete()

    @classmethod
    def vigentes_para(cls, funcion):
        cls.limpiar_expiradas()
        return cls.objects.filter(funcion=funcion, expira_en__gt=timezone.now())

    @classmethod
    def reservar(cls, usuario, funcion, label):
        with transaction.atomic():
            funcion = Funcion.objects.select_for_update().get(pk=funcion.pk)
            cls.limpiar_expiradas()
            CompraEntrada.sincronizar_asientos_vendidos(funcion)
            if label not in CompraEntrada.precios_por_asiento(funcion):
                raise ValidationError("La butaca no es valida para esta funcion.")
            if CompraAsiento.objects.filter(funcion=funcion, label=label).exists():
                raise ValidationError("La butaca ya fue comprada.")

            reserva = cls.objects.select_for_update().filter(
                funcion=funcion,
                label=label,
            ).first()
            expiration = timezone.now() + cls.duracion()
            if reserva and reserva.usuario_id != usuario.pk and reserva.expira_en > timezone.now():
                raise ValidationError("La butaca esta reservada temporalmente.")
            if reserva:
                reserva.usuario = usuario
                reserva.expira_en = expiration
                reserva.save(update_fields=["usuario", "expira_en", "actualizada_en"])
            else:
                reserva = cls.objects.create(
                    usuario=usuario,
                    funcion=funcion,
                    label=label,
                    expira_en=expiration,
                )
            return reserva

    @classmethod
    def liberar(cls, usuario, funcion, label):
        cls.objects.filter(usuario=usuario, funcion=funcion, label=label).delete()
