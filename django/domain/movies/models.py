from django.db import models


class Pelicula(models.Model):
    class Clasificacion(models.TextChoices):
        ATP = "ATP", "ATP - Apta para todo público"
        MAS_13 = "+13", "+13 años"
        MAS_16 = "+16", "+16 años"
        MAS_18 = "+18", "+18 años"

    class Genero(models.TextChoices):
        ACCION = "ACCION", "Acción"
        AVENTURA = "AVENTURA", "Aventura"
        ANIMACION = "ANIMACION", "Animación"
        COMEDIA = "COMEDIA", "Comedia"
        DRAMA = "DRAMA", "Drama"
        TERROR = "TERROR", "Terror"
        CIENCIA_FICCION = "CIENCIA_FICCION", "Ciencia ficción"
        SUSPENSO = "SUSPENSO", "Suspenso"
        ROMANCE = "ROMANCE", "Romance"
        DOCUMENTAL = "DOCUMENTAL", "Documental"
        FANTASIA = "FANTASIA", "Fantasía"
        MUSICAL = "MUSICAL", "Musical"

    titulo = models.CharField(max_length=200)
    sinopsis = models.TextField()
    genero = models.CharField(max_length=20, verbose_name="Género", choices=Genero.choices)
    clasificacion = models.CharField(max_length=5, verbose_name="Clasificación", choices=Clasificacion.choices)
    duracion_minutos = models.PositiveIntegerField(
        help_text="Duración de la película en minutos",
        verbose_name="Duración en minutos"
    )
    imagen = models.ImageField(upload_to="peliculas/", verbose_name="Imagen del cartel")

    class Meta:
        verbose_name = "Película"
        verbose_name_plural = "Películas"
        ordering = ["titulo"]

    @property
    def duracion_horas_minutos(self):
        horas, minutos = divmod(self.duracion_minutos, 60)
        if horas and minutos:
            return f"{horas} h {minutos} min"
        if horas:
            return f"{horas} h"
        return f"{minutos} min"

    def __str__(self):
        return self.titulo
