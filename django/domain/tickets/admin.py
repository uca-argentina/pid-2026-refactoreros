from django.contrib import admin

from .models import CompraEntrada


@admin.register(CompraEntrada)
class CompraEntradaAdmin(admin.ModelAdmin):
    list_display = ("usuario", "funcion", "cantidad", "total", "creada_en")
    list_filter = ("funcion__sala", "creada_en")
    search_fields = ("usuario__email", "usuario__username", "funcion__pelicula__titulo")
    readonly_fields = ("total", "creada_en")
