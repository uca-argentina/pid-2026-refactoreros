from django.contrib import admin
from django.utils import timezone

from .models import SeatPurchase, TicketPurchase, SeatReservation


@admin.register(TicketPurchase)
class TicketPurchaseAdmin(admin.ModelAdmin):
    list_display = ("user", "screening", "quantity", "total", "created_at")
    list_filter = ("screening__room", "created_at")
    search_fields = ("user__email", "user__username", "screening__movie__title")
    readonly_fields = ("total", "created_at")


@admin.register(SeatPurchase)
class SeatPurchaseAdmin(admin.ModelAdmin):
    list_display = ("screening", "label", "purchase", "created_at", "used_at")
    list_filter = ("screening__room", "created_at", ("used_at", admin.EmptyFieldListFilter))
    search_fields = ("label", "screening__movie__title", "purchase__user__email")
    actions = ("mark_used",)

    @admin.action(description="Marcar como utilizadas")
    def mark_used(self, request, queryset):
        updated = queryset.filter(used_at__isnull=True).update(used_at=timezone.now())
        self.message_user(request, f"{updated} entradas marcadas como utilizadas.")


@admin.register(SeatReservation)
class SeatReservationAdmin(admin.ModelAdmin):
    list_display = ("user", "screening", "label", "expires_at")
    list_filter = ("screening__room", "expires_at")
    search_fields = ("label", "user__email", "screening__movie__title")
