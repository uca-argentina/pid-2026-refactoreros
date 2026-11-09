"""Admission."""

from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from domain.cinema.models import CinemaSettings
from domain.screenings.models import Screening
from domain.tickets.models import (
    AdmissionTicket,
    AdmissionValidation,
    SeatPurchase,
    TicketPurchase,
    reservation_code_digest,
)
from domain.tickets.services.credentials import ticket_credential, ticket_not_found
from domain.users.roles import can_validate_tickets


def check_purchase(purchase):
    screening = purchase.screening
    if screening.status == Screening.Status.CANCELED or hasattr(purchase, "refund"):
        raise ValidationError("La función está cancelada. Esta entrada no permite ingresar.")
    if (
        screening.status not in (Screening.Status.PUBLISHED, Screening.Status.IN_PROGRESS)
        or screening.ends_at <= timezone.now()
    ):
        raise ValidationError("La función no está habilitada para el ingreso o ya finalizó.")
    if purchase.remaining_quantity <= 0:
        raise ValidationError("Esta compra ya no tiene entradas disponibles.")


def inspect_ticket(code, operator):
    if not can_validate_tickets(operator):
        raise PermissionDenied
    credential = ticket_credential(code)
    filters = (
        {"validation_token": credential}
        if len(credential) == 32
        else {"validation_code_digest": reservation_code_digest(credential)}
    )
    purchase = (
        TicketPurchase.objects.select_related(
            "screening__movie",
            "screening__room",
            "refund",
        )
        .prefetch_related("tickets")
        .filter(**filters)
        .first()
    )
    if purchase is None:
        ticket_not_found(credential)
    check_purchase(purchase)
    return purchase


def validate_ticket(code, operator, quantity=None, ticket_numbers=None):
    if not can_validate_tickets(operator):
        raise PermissionDenied
    credential = ticket_credential(code)
    selected_numbers = None
    if ticket_numbers is not None:
        try:
            selected_numbers = [int(number) for number in ticket_numbers]
        except (TypeError, ValueError):
            raise ValidationError("Las entradas seleccionadas no son válidas.")
        if not selected_numbers:
            raise ValidationError("Seleccioná al menos una butaca para validar.")
        if len(selected_numbers) != len(set(selected_numbers)):
            raise ValidationError("No podés validar la misma butaca más de una vez.")
    else:
        try:
            quantity = int(quantity or 1)
        except (TypeError, ValueError):
            raise ValidationError("Indicá cuántas personas ingresan.")
        if quantity < 1:
            raise ValidationError("Indicá al menos una persona.")
    filters = (
        {"validation_token": credential}
        if len(credential) == 32
        else {"validation_code_digest": reservation_code_digest(credential)}
    )
    candidate = TicketPurchase.objects.select_related("screening").filter(**filters).first()
    if candidate is None:
        ticket_not_found(credential)
    with transaction.atomic():
        screening = Screening.objects.select_for_update().filter(pk=candidate.screening_id).first()
        if screening is None:
            raise ValidationError("La función no existe.")
        try:
            purchase = (
                TicketPurchase.objects.select_for_update()
                .select_related("screening")
                .get(**filters)
            )
        except TicketPurchase.DoesNotExist:
            raise ValidationError("No encontramos una entrada con ese código.")
        check_purchase(purchase)
        if selected_numbers is None:
            if quantity > purchase.remaining_quantity:
                raise ValidationError(
                    f"Solo quedan {purchase.remaining_quantity} entradas sin utilizar en esta compra."
                )
            tickets = list(
                AdmissionTicket.objects.select_for_update()
                .filter(
                    purchase=purchase,
                    used_at__isnull=True,
                )
                .order_by("number")[:quantity]
            )
        else:
            tickets = list(
                AdmissionTicket.objects.select_for_update()
                .filter(
                    purchase=purchase,
                    number__in=selected_numbers,
                    used_at__isnull=True,
                )
                .order_by("number")
            )
            if len(tickets) != len(selected_numbers):
                raise ValidationError("Alguna de las butacas seleccionadas ya no está disponible.")
        if not tickets:
            raise ValidationError(
                "Las entradas disponibles cambiaron. Volvé a consultar la compra."
            )
        now = timezone.now()
        AdmissionTicket.objects.filter(pk__in=[ticket.pk for ticket in tickets]).update(
            used_at=now, used_by=operator
        )
        SeatPurchase.objects.filter(
            purchase=purchase,
            label__in=[ticket.seat_label for ticket in tickets],
            used_at__isnull=True,
        ).update(used_at=now)
        validation = AdmissionValidation.objects.create(purchase=purchase, operator=operator)
        validation.tickets.set(tickets)
        return purchase, tickets, validation


def undo_ticket_validation(validation_id, operator):
    if not can_validate_tickets(operator):
        raise PermissionDenied
    try:
        validation_id = int(validation_id)
    except (TypeError, ValueError):
        raise ValidationError("La validación a deshacer no es válida.")
    with transaction.atomic():
        validation = (
            AdmissionValidation.objects.select_for_update()
            .select_related("purchase__screening")
            .filter(pk=validation_id, operator=operator)
            .first()
        )
        if validation is None:
            raise ValidationError("No encontramos esa validación en tu historial.")
        if validation.reverted_at is not None:
            raise ValidationError("Esta validación ya fue deshecha.")
        now = timezone.now()
        undo_seconds = CinemaSettings.current().admission_undo_seconds
        if validation.created_at < now - timedelta(seconds=undo_seconds):
            raise ValidationError("El plazo para deshacer esta validación ya venció.")
        screening = (
            Screening.objects.select_for_update()
            .filter(pk=validation.purchase.screening_id)
            .first()
        )
        if screening is None:
            raise ValidationError("La función ya no existe.")
        tickets = list(validation.tickets.select_for_update())
        AdmissionTicket.objects.filter(pk__in=[ticket.pk for ticket in tickets]).update(
            used_at=None, used_by=None
        )
        labels = [ticket.seat_label for ticket in tickets if ticket.seat_label]
        if labels:
            SeatPurchase.objects.filter(purchase=validation.purchase, label__in=labels).update(
                used_at=None
            )
        validation.reverted_at = now
        validation.save(update_fields=["reverted_at"])
        return validation, tickets
