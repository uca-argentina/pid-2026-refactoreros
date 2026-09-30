from django.contrib import admin


from .models import Seat

@admin.register(Seat)
class SeatAdmin(admin.ModelAdmin):
    list_display = ("sala", "fila", "columna","tipo")
    list_filter = ("sala",)
    ordering = ("sala",)