from django.contrib import admin

from .models import Funcion


@admin.register(Funcion)
class FuncionAdmin(admin.ModelAdmin):
    list_display = ("pelicula", "sala", "fecha_horario", "estado", "precio_desde")
    list_filter = ("sala", "estado")
    date_hierarchy = "fecha_horario"
    ordering = ("fecha_horario",)
