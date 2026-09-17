import re

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _


class NumberPasswordValidator:
    def validate(self, password, user=None):
        if not re.search(r"\d", password):
            raise ValidationError(
                _("La contraseña debe incluir al menos un número."),
                code="password_no_number",
            )

    def get_help_text(self):
        return _("Tu contraseña debe incluir al menos un número.")


class SpecialCharacterPasswordValidator:
    def validate(self, password, user=None):
        if not re.search(r"[^A-Za-z0-9]", password):
            raise ValidationError(
                _("La contraseña debe incluir al menos un carácter especial."),
                code="password_no_special_character",
            )

    def get_help_text(self):
        return _("Tu contraseña debe incluir al menos un carácter especial.")
