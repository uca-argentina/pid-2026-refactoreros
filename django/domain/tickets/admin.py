from django.contrib import admin

from .models import CompraAsiento, CompraEntrada, ReservaAsiento


@admin.register(CompraEntrada)
class CompraEntradaAdmin(admin.ModelAdmin):
    list_display = ("usuario", "funcion", "cantidad", "total", "creada_en")
    list_filter = ("funcion__sala", "creada_en")
    search_fields = ("usuario__email", "usuario__username", "funcion__pelicula__titulo")
    readonly_fields = ("total", "creada_en")


@admin.register(CompraAsiento)
class CompraAsientoAdmin(admin.ModelAdmin):
    list_display = ("funcion", "label", "compra", "creada_en")
    list_filter = ("funcion__sala", "creada_en")
    search_fields = ("label", "funcion__pelicula__titulo", "compra__usuario__email")


@admin.register(ReservaAsiento)
class ReservaAsientoAdmin(admin.ModelAdmin):
    list_display = ("usuario", "funcion", "label", "expira_en")
    list_filter = ("funcion__sala", "expira_en")
    search_fields = ("label", "usuario__email", "funcion__pelicula__titulo")
