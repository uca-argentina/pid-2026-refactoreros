"""Contrato JSON de reservas; la vista decide cómo responder a los errores."""

import json

from django.core.exceptions import ValidationError

MAX_RESERVATION_BODY_BYTES = 64 * 1024
MAX_RESERVATION_OPERATIONS = 100


def reservation_request(request):
    if len(request.body) > MAX_RESERVATION_BODY_BYTES:
        raise ValidationError("La solicitud es demasiado grande.")
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except (ValueError, UnicodeDecodeError):
        raise ValidationError("Solicitud inválida.")
    if not isinstance(payload, dict):
        raise ValidationError("La solicitud debe ser un objeto JSON.")
    return payload


def reservation_operation(payload):
    if not isinstance(payload, dict):
        raise ValidationError("Solicitud inválida.")
    label, action = payload.get("label"), payload.get("action")
    if not isinstance(label, str) or not label.strip() or len(label) > 12:
        raise ValidationError("La butaca no es válida.")
    if not isinstance(action, str) or action not in {"reserve", "release"}:
        raise ValidationError("La acción no es válida.")
    return label.strip(), action
