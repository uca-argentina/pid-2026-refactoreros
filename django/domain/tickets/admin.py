from django.contrib import admin
from .models import AdmissionTicket, AdmissionValidation, PurchaseRefund, SeatPurchase, TicketPurchase, SeatReservation


class AuditOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(AdmissionTicket)
class AdmissionTicketAdmin(AuditOnlyAdmin):
    list_display = ("purchase", "number", "seat_label", "used_at", "used_by")
    list_filter = (("used_at", admin.EmptyFieldListFilter),)


@admin.register(AdmissionValidation)
class AdmissionValidationAdmin(AuditOnlyAdmin):
    list_display = ("purchase", "operator", "created_at", "reverted_at")
    list_filter = (("reverted_at", admin.EmptyFieldListFilter), "created_at")
    filter_horizontal = ("tickets",)


@admin.register(PurchaseRefund)
class PurchaseRefundAdmin(AuditOnlyAdmin):
    list_display = ("purchase", "amount", "reference", "created_at", "email_sent_at")


@admin.register(TicketPurchase)
class TicketPurchaseAdmin(AuditOnlyAdmin):
    list_display = ("user", "screening", "quantity", "total", "created_at")
    list_filter = ("screening__room", "created_at")
    search_fields = ("user__email", "user__username", "screening__movie__title")
    readonly_fields = ("total", "created_at")


@admin.register(SeatPurchase)
class SeatPurchaseAdmin(AuditOnlyAdmin):
    list_display = ("screening", "label", "purchase", "created_at", "used_at")
    list_filter = ("screening__room", "created_at", ("used_at", admin.EmptyFieldListFilter))
    search_fields = ("label", "screening__movie__title", "purchase__user__email")


@admin.register(SeatReservation)
class SeatReservationAdmin(admin.ModelAdmin):
    list_display = ("user", "screening", "label", "expires_at")
    list_filter = ("screening__room", "expires_at")
    search_fields = ("label", "user__email", "screening__movie__title")
