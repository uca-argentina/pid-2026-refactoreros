from django.contrib import admin


from .models import SeatType

@admin.register(SeatType)
class SeatTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "base_price", "color","icon")
    list_filter = ("base_price",)
    ordering = ("name",)