from django.contrib import admin

from .models import Promotion


@admin.register(Promotion)
class PromotionAdmin(admin.ModelAdmin):
    list_display = ("name", "discount_type", "discount_value", "is_active")
    list_filter = ("is_active", "discount_type")
    search_fields = ("name",)
    filter_horizontal = ("seat_types",)
