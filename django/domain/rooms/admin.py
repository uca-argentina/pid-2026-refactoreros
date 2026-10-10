from django.contrib import admin
from django.db.models import Count

from .models import Room


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ("name", "total_capacity")
    search_fields = ("name",)
    ordering = ("name",)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_capacidad=Count("seats"))

    @admin.display(description="Capacidad", ordering="_capacity")
    def total_capacity(self, obj):
        return obj._capacity
