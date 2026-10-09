from django.db import models


class Movie(models.Model):
    class Rating(models.TextChoices):
        ATP = "ATP", "ATP - Apta para todo publico"
        MAS_13 = "+13", "+13 anos"
        MAS_16 = "+16", "+16 anos"
        MAS_18 = "+18", "+18 anos"

    class Genre(models.TextChoices):
        ACCION = "ACCION", "Accion"
        AVENTURA = "AVENTURA", "Aventura"
        ANIMACION = "ANIMACION", "Animacion"
        COMEDIA = "COMEDIA", "Comedia"
        DRAMA = "DRAMA", "Drama"
        TERROR = "TERROR", "Terror"
        CIENCIA_FICCION = "CIENCIA_FICCION", "Ciencia ficcion"
        SUSPENSO = "SUSPENSO", "Suspenso"
        ROMANCE = "ROMANCE", "Romance"
        DOCUMENTAL = "DOCUMENTAL", "Documental"
        FANTASIA = "FANTASIA", "Fantasia"
        MUSICAL = "MUSICAL", "Musical"

    title = models.CharField(max_length=200, db_column="titulo")
    synopsis = models.TextField(db_column="sinopsis")
    genre = models.CharField(max_length=20, verbose_name="Genero", choices=Genre.choices, db_column="genero")
    rating = models.CharField(max_length=5, verbose_name="Clasificacion", choices=Rating.choices, db_column="clasificacion")
    duration_minutes = models.PositiveIntegerField(
        help_text="Duracion de la pelicula en minutos",
        verbose_name="Duracion en minutos",
        db_column="duracion_minutos",
    )
    image = models.ImageField(upload_to="peliculas/", verbose_name="Imagen del cartel", db_column="imagen")

    class Meta:
        verbose_name = "Pelicula"
        verbose_name_plural = "Peliculas"
        db_table = "movies_pelicula"
        ordering = ["title"]

    @property
    def runtime_label(self):
        hours, minutes = divmod(self.duration_minutes, 60)
        if hours and minutes:
            return f"{hours} h {minutes} min"
        if hours:
            return f"{hours} h"
        return f"{minutes} min"

    def __str__(self):
        return self.title
