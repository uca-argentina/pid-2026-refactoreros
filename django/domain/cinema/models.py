from django.db import models


class ConfiguracionCine(models.Model):
    nombre = models.CharField(max_length=120, default="Butaca Cero")
    slogan = models.CharField(max_length=160, default="Tu entrada al cine")
    logo = models.ImageField(upload_to="branding/", blank=True)
    imagen_login = models.ImageField(upload_to="branding/", blank=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Configuracion del cine"
        verbose_name_plural = "Configuracion del cine"

    def __str__(self):
        return self.nombre

    @classmethod
    def actual(cls):
        configuracion = cls.objects.order_by("id").first()
        if configuracion:
            return configuracion
        return cls(nombre="Butaca Cero", slogan="Tu entrada al cine")
