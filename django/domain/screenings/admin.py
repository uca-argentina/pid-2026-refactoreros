from django.contrib import admin

from .models import Funcion


@admin.register(Funcion)
class FuncionAdmin(admin.ModelAdmin):
    list_display = ("pelicula", "sala", "fecha_horario", "publicada", "precio_entrada")
    list_filter = ("sala", "publicada")
    date_hierarchy = "fecha_horario"
    ordering = ("fecha_horario",)