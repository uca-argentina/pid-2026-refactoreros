"""Entorno de pruebas local/CI: sin correo ni almacenamiento externos."""

from .settings import *  # noqa: F403

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
# Solo acelera las cuentas descartables de pruebas. Producción mantiene su hash.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
TEST_RUNNER = "butacaCero.test_runner.LocalTestRunner"
