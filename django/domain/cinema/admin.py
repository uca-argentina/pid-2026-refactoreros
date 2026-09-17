from django.contrib import admin

from .models import ConfiguracionCine


@admin.register(ConfiguracionCine)
class ConfiguracionCineAdmin(admin.ModelAdmin):
    list_display = ("nombre", "slogan", "actualizado_en")
    readonly_fields = ("actualizado_en",)

    def has_add_permission(self, request):
        if ConfiguracionCine.objects.exists():
            return False
        return super().has_add_permission(request)
