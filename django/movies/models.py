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
    genero = models.CharField(max_length=20, choices=Genero.choices)
    clasificacion = models.CharField(max_length=5, choices=Clasificacion.choices)
    duracion_minutos = models.PositiveIntegerField(
        help_text="Duración de la película en minutos"
    )
    imagen = models.ImageField(upload_to="peliculas/")

    class Meta:
        verbose_name = "Película"
        verbose_name_plural = "Películas"
        ordering = ["titulo"]

    def __str__(self):
        return self.titulo