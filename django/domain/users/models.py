from django.conf import settings
from django.db import models


class Cliente(models.Model):
    id_cliente = models.BigAutoField(primary_key=True)
    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="cliente",
        db_column="id_usuario",
    )

    class Meta:
        verbose_name = "Cliente"
        verbose_name_plural = "Clientes"
        ordering = ["usuario__username"]

    def __str__(self):
        return self.usuario.get_username()


class Acomodador(models.Model):
    id_acomodador = models.BigAutoField(primary_key=True)
    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="acomodador",
        db_column="id_usuario",
    )

    class Meta:
        verbose_name = "Acomodador"
        verbose_name_plural = "Acomodadores"
        ordering = ["usuario__username"]

    def __str__(self):
        return self.usuario.get_username()


class Gerente(models.Model):
    id_gerente = models.BigAutoField(primary_key=True)
    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="gerente",
        db_column="id_usuario",
    )

    class Meta:
        verbose_name = "Gerente"
        verbose_name_plural = "Gerentes"
        ordering = ["usuario__username"]

    def __str__(self):
        return self.usuario.get_username()
