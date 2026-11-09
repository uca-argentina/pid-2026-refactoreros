"""Credentials."""

import re

from django.core.exceptions import ValidationError

from domain.tickets.models import reservation_code_digest

CANDY_CODE_MESSAGE = "Este código corresponde a un pedido de Candy."


def normalize_purchase_credential(
    value, qr_prefix="BC2:", invalid_message="El código de entrada no es válido."
):
    value = value.strip()
    if value.startswith(qr_prefix):
        value = value[len(qr_prefix) :]
    if re.fullmatch(r"[A-Za-z2-9]{6}", value):
        return value.upper()
    if not re.fullmatch(r"[A-Za-z0-9_-]{32}", value):
        raise ValidationError(invalid_message)
    return value


def ticket_credential(code):
    if code.strip().upper().startswith("BCC:"):
        normalize_purchase_credential(code.strip()[4:])
        raise ValidationError(CANDY_CODE_MESSAGE)
    return normalize_purchase_credential(code)


def ticket_not_found(credential):
    from domain.candy.models import CandyOrder

    filters = (
        {"pickup_token": credential}
        if len(credential) == 32
        else {"pickup_code_digest": reservation_code_digest(credential)}
    )
    if CandyOrder.objects.filter(**filters).exists():
        raise ValidationError(CANDY_CODE_MESSAGE)
    raise ValidationError("No encontramos una entrada con ese código.")
