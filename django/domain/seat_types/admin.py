from django.contrib import admin


from .models import SeatType

@admin.register(SeatType)
class SeatTypeAdmin(admin.ModelAdmin):
    list_display = ("nombre", "precio_base", "color","icono")
    list_filter = ("precio_base",)
    ordering = ("nombre",)