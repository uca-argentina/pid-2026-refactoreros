from django.contrib import admin

from .models import CinemaSettings


@admin.register(CinemaSettings)
class CinemaSettingsAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "slogan",
        "seat_reservation_minutes",
        "seat_refresh_seconds",
        "updated_at",
    )
    readonly_fields = ("updated_at",)

    def has_add_permission(self, request):
        if CinemaSettings.objects.exists():
            return False
        return super().has_add_permission(request)
