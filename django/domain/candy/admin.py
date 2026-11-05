from django.contrib import admin

from domain.tickets.admin import AuditOnlyAdmin

from .models import CandyCombo, CandyComboItem, CandyOrder, CandyPickup, CandyProduct


@admin.register(CandyProduct)
class CandyProductAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "price", "stock", "is_active")
    list_filter = ("is_active", "category")
    search_fields = ("name",)


class CandyComboItemInline(admin.TabularInline):
    model = CandyComboItem
    extra = 1


@admin.register(CandyCombo)
class CandyComboAdmin(admin.ModelAdmin):
    list_display = ("name", "price", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)
    inlines = (CandyComboItemInline,)


@admin.register(CandyOrder)
class CandyOrderAdmin(AuditOnlyAdmin):
    list_display = ("purchase", "reward_user", "total", "created_at", "delivered_at", "delivered_by")
    list_filter = (("delivered_at", admin.EmptyFieldListFilter), "created_at")
    search_fields = ("purchase__user__email", "purchase__screening__movie__title", "reward_user__email")


@admin.register(CandyPickup)
class CandyPickupAdmin(AuditOnlyAdmin):
    list_display = ("order", "operator", "created_at", "reverted_at")
    list_filter = (("reverted_at", admin.EmptyFieldListFilter), "created_at")
