from django.contrib import admin


from .models import Seat

@admin.register(Seat)
class SeatAdmin(admin.ModelAdmin):
    list_display = ("sala", "fila", "columna","precio_base")
    list_filter = ("sala",)
    ordering = ("sala",)