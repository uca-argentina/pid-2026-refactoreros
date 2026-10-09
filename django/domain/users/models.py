from django.conf import settings
from django.db import models


class Customer(models.Model):
    customer_id = models.BigAutoField(primary_key=True, db_column="id_cliente")
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="customer_profile",
        db_column="id_usuario",
    )

    class Meta:
        verbose_name = "Cliente"
        verbose_name_plural = "Clientes"
        db_table = "users_cliente"
        ordering = ["user__username"]

    def __str__(self):
        return self.user.get_username()


class Usher(models.Model):
    usher_id = models.BigAutoField(primary_key=True, db_column="id_acomodador")
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="usher_profile",
        db_column="id_usuario",
    )

    class Meta:
        verbose_name = "Acomodador"
        verbose_name_plural = "Acomodadores"
        db_table = "users_acomodador"
        ordering = ["user__username"]

    def __str__(self):
        return self.user.get_username()


class Manager(models.Model):
    manager_id = models.BigAutoField(primary_key=True, db_column="id_gerente")
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="manager_profile",
        db_column="id_usuario",
    )

    class Meta:
        verbose_name = "Gerente"
        verbose_name_plural = "Gerentes"
        db_table = "users_gerente"
        ordering = ["user__username"]

    def __str__(self):
        return self.user.get_username()
