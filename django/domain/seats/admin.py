from django.contrib import admin


from .models import Seat

@admin.register(Seat)
class SeatAdmin(admin.ModelAdmin):
    list_display = ("room", "row", "column","seat_type")
    list_filter = ("room",)
    ordering = ("room",)