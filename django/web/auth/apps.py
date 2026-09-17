from django.apps import AppConfig


class WebAuthConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "web.auth"
    label = "web_auth"
    verbose_name = "Autenticación"
