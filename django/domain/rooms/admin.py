from django.contrib import admin

from .models import Sala


@admin.register(Sala)
class SalaAdmin(admin.ModelAdmin):
    list_display = ("nombre", "capacidad")
    search_fields = ("nombre",)
    ordering = ("nombre",)