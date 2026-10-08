from django.contrib import admin
from django.utils import timezone

from .models import CompraAsiento, CompraEntrada, ReservaAsiento


@admin.register(CompraEntrada)
class CompraEntradaAdmin(admin.ModelAdmin):
    list_display = ("usuario", "funcion", "cantidad", "total", "creada_en")
    list_filter = ("funcion__sala", "creada_en")
    search_fields = ("usuario__email", "usuario__username", "funcion__pelicula__titulo")
    readonly_fields = ("total", "creada_en")


@admin.register(CompraAsiento)
class CompraAsientoAdmin(admin.ModelAdmin):
    list_display = ("funcion", "label", "compra", "creada_en", "utilizada_en")
    list_filter = ("funcion__sala", "creada_en", ("utilizada_en", admin.EmptyFieldListFilter))
    search_fields = ("label", "funcion__pelicula__titulo", "compra__usuario__email")
    actions = ("marcar_utilizadas",)

    @admin.action(description="Marcar como utilizadas")
    def marcar_utilizadas(self, request, queryset):
        actualizadas = queryset.filter(utilizada_en__isnull=True).update(utilizada_en=timezone.now())
        self.message_user(request, f"{actualizadas} entradas marcadas como utilizadas.")


@admin.register(ReservaAsiento)
class ReservaAsientoAdmin(admin.ModelAdmin):
    list_display = ("usuario", "funcion", "label", "expira_en")
    list_filter = ("funcion__sala", "expira_en")
    search_fields = ("label", "usuario__email", "funcion__pelicula__titulo")
