from django.contrib import admin

from .models import Pelicula

@admin.register(Pelicula)
class PeliculaAdmin(admin.ModelAdmin):
    list_display = ("titulo", "genero", "clasificacion", "duracion_minutos")
    list_filter = ("genero", "clasificacion")
    search_fields = ("titulo", "sinopsis")
    ordering = ("titulo",)
    fields = (
        "titulo",
        "sinopsis",
        "genero",
        "clasificacion",
        "duracion_minutos",
        "imagen",
    )