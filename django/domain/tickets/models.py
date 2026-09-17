from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Sum

from domain.screenings.models import Funcion


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
    creada_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Compra de entrada"
        verbose_name_plural = "Compras de entradas"
        ordering = ["-creada_en"]

    def __str__(self):
        return f"{self.usuario} - {self.funcion} x{self.cantidad}"

    @classmethod
    def cantidad_vendida(cls, funcion):
        return (
            cls.objects.filter(funcion=funcion).aggregate(total=Sum("cantidad"))["total"]
            or 0
        )

    @classmethod
    def disponibles_para(cls, funcion):
        return max(funcion.sala.capacidad - cls.cantidad_vendida(funcion), 0)

    @classmethod
    def comprar(cls, usuario, funcion, cantidad):
        with transaction.atomic():
            cantidad = int(cantidad)
            funcion = Funcion.objects.select_for_update().select_related("sala").get(
                pk=funcion.pk
            )
            compra = cls(
                usuario=usuario,
                funcion=funcion,
                cantidad=cantidad,
                total=funcion.precio_entrada * cantidad,
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
        if self.funcion_id and self.cantidad:
            self.total = self.funcion.precio_entrada * self.cantidad
        super().save(*args, **kwargs)
