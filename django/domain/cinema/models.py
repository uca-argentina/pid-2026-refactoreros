from django.db import models


class CinemaSettings(models.Model):
    name = models.CharField(max_length=120, default="Butaca Cero", db_column="nombre")
    slogan = models.CharField(max_length=160, default="Tu entrada al cine")
    logo = models.ImageField(upload_to="branding/", blank=True)
    login_image = models.ImageField(upload_to="branding/", blank=True, db_column="imagen_login")
    seat_reservation_minutes = models.PositiveIntegerField(default=5, db_column="reserva_asientos_minutos")
    seat_refresh_seconds = models.PositiveIntegerField(default=5, db_column="recarga_asientos_segundos")
    updated_at = models.DateTimeField(auto_now=True, db_column="actualizado_en")

    class Meta:
        verbose_name = "Configuracion del cine"
        verbose_name_plural = "Configuracion del cine"
        db_table = "cinema_configuracioncine"

    def __str__(self):
        return self.name

    @classmethod
    def current(cls):
        cinema_settings = cls.objects.order_by("id").first()
        if cinema_settings:
            return cinema_settings
        return cls(name="Butaca Cero", slogan="Tu entrada al cine")
