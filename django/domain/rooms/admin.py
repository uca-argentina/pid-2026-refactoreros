from django.contrib import admin
from django.db.models import Count

from .models import Sala


@admin.register(Sala)
class SalaAdmin(admin.ModelAdmin):
    list_display = ("nombre", "capacidad")
    search_fields = ("nombre",)
    ordering = ("nombre",)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_capacidad=Count("seats"))

    @admin.display(description="Capacidad", ordering="_capacidad")
    def capacidad_total(self, obj):
        return obj._capacidad