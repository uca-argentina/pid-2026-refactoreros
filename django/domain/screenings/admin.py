from django.contrib import admin

from .models import Screening


@admin.register(Screening)
class ScreeningAdmin(admin.ModelAdmin):
    list_display = ("movie", "room", "starts_at", "status", "price_from")
    list_filter = ("room", "status")
    date_hierarchy = "starts_at"
    ordering = ("starts_at",)
