import logging
import re
from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.mail import send_mail
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.db import transaction
from django.utils import timezone

from domain.cinema.models import CinemaSettings
from domain.screenings.models import Screening
from domain.users.roles import can_validate_tickets
from .models import (
    AdmissionTicket,
    AdmissionValidation,
    PurchaseRefund,
    SeatPurchase,
    SeatReservation,
    TicketPurchase,
    reservation_code_digest,
)

logger = logging.getLogger(__name__)


def normalize_purchase_credential(value):
    value = value.strip()
    if value.startswith("BC2:"):
        value = value[4:]
    if re.fullmatch(r"[A-Za-z2-9]{6}", value):
        # The short, human-entered reservation code is intentionally
        # case-insensitive. Store/query its canonical uppercase form so the
        # unique indexed lookup stays fast.
        return value.upper()
    if not re.fullmatch(r"[A-Za-z0-9_-]{32}", value):
        raise ValidationError("El código de entrada no es válido.")
    return value


def check_purchase(purchase):
    screening = purchase.screening
    if screening.status == Screening.Status.CANCELED or hasattr(purchase, "refund"):
        raise ValidationError("La función está cancelada. Esta entrada no permite ingresar.")
    if screening.status != Screening.Status.PUBLISHED or screening.ends_at <= timezone.now():
        raise ValidationError("La función no está habilitada para el ingreso o ya finalizó.")
    if purchase.remaining_quantity <= 0:
        raise ValidationError("Esta compra ya no tiene entradas disponibles.")


def inspect_ticket(code, operator):
    if not can_validate_tickets(operator):
        raise PermissionDenied
    credential = normalize_purchase_credential(code)
    filters = {"validation_token": credential} if len(credential) == 32 else {"validation_code_digest": reservation_code_digest(credential)}
    purchase = TicketPurchase.objects.select_related(
        "screening__movie", "screening__room", "refund",
    ).prefetch_related("tickets").filter(**filters).first()
    if purchase is None:
        raise ValidationError("No encontramos una entrada con ese código.")
    check_purchase(purchase)
    return purchase


def validate_ticket(code, operator, quantity=None, ticket_numbers=None):
    if not can_validate_tickets(operator):
        raise PermissionDenied
    credential = normalize_purchase_credential(code)
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
        # Compatibility for service callers; the operator UI always sends the
        # specific seats selected for admission.
        try:
            quantity = int(quantity or 1)
        except (TypeError, ValueError):
            raise ValidationError("Indicá cuántas personas ingresan.")
        if quantity < 1:
            raise ValidationError("Indicá al menos una persona.")
    filters = {"validation_token": credential} if len(credential) == 32 else {"validation_code_digest": reservation_code_digest(credential)}
    candidate = TicketPurchase.objects.select_related("screening").filter(**filters).first()
    if candidate is None:
        raise ValidationError("No encontramos una entrada con ese código.")
    with transaction.atomic():
        # Same lock order as sales/cancellation: screening first, then ticket.
        # Serializes simultaneous scans and cancellation against admissions.
        screening = Screening.objects.select_for_update().filter(pk=candidate.screening_id).first()
        if screening is None:
            raise ValidationError("La función no existe.")
        try:
            purchase = TicketPurchase.objects.select_for_update().select_related("screening").get(**filters)
        except TicketPurchase.DoesNotExist:
            raise ValidationError("No encontramos una entrada con ese código.")
        check_purchase(purchase)
        if selected_numbers is None:
            if quantity > purchase.remaining_quantity:
                raise ValidationError(f"Solo quedan {purchase.remaining_quantity} entradas sin utilizar en esta compra.")
            tickets = list(AdmissionTicket.objects.select_for_update().filter(
                purchase=purchase, used_at__isnull=True,
            ).order_by("number")[:quantity])
        else:
            tickets = list(AdmissionTicket.objects.select_for_update().filter(
                purchase=purchase, number__in=selected_numbers, used_at__isnull=True,
            ).order_by("number"))
            if len(tickets) != len(selected_numbers):
                raise ValidationError("Alguna de las butacas seleccionadas ya no está disponible.")
        if not tickets:
            raise ValidationError("Las entradas disponibles cambiaron. Volvé a consultar la compra.")
        now = timezone.now()
        AdmissionTicket.objects.filter(pk__in=[ticket.pk for ticket in tickets]).update(used_at=now, used_by=operator)
        # Preserve the existing sold-seat audit used by older admin/reporting.
        SeatPurchase.objects.filter(purchase=purchase, label__in=[ticket.seat_label for ticket in tickets],
                                    used_at__isnull=True).update(used_at=now)
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
        validation = AdmissionValidation.objects.select_for_update().select_related(
            "purchase__screening"
        ).filter(pk=validation_id, operator=operator).first()
        if validation is None:
            raise ValidationError("No encontramos esa validación en tu historial.")
        if validation.reverted_at is not None:
            raise ValidationError("Esta validación ya fue deshecha.")
        now = timezone.now()
        undo_seconds = CinemaSettings.current().admission_undo_seconds
        if validation.created_at < now - timedelta(seconds=undo_seconds):
            raise ValidationError("El plazo para deshacer esta validación ya venció.")
        screening = Screening.objects.select_for_update().filter(pk=validation.purchase.screening_id).first()
        if screening is None:
            raise ValidationError("La función ya no existe.")
        tickets = list(validation.tickets.select_for_update())
        AdmissionTicket.objects.filter(pk__in=[ticket.pk for ticket in tickets]).update(used_at=None, used_by=None)
        labels = [ticket.seat_label for ticket in tickets if ticket.seat_label]
        if labels:
            SeatPurchase.objects.filter(purchase=validation.purchase, label__in=labels).update(used_at=None)
        validation.reverted_at = now
        validation.save(update_fields=["reverted_at"])
        return validation, tickets


def refund_canceled_screening(screening):
    """Caller holds the screening lock. One refund and in-app notice per purchase."""
    for purchase in TicketPurchase.objects.filter(screening=screening):
        notice = (
            f"Se canceló la función de {screening.movie.title} del "
            f"{timezone.localtime(screening.starts_at):%d/%m/%Y %H:%M}. "
            f"Registramos una devolución simulada de ${purchase.total:.2f} "
            f"por tu compra #{purchase.pk}. No se realizó un movimiento de dinero real."
        )
        PurchaseRefund.objects.get_or_create(
            purchase=purchase, defaults={"amount": purchase.total, "notice": notice},
        )
    SeatReservation.objects.filter(screening=screening).delete()


def send_refund_notifications(refund_ids=None):
    """Retryable outbox: SMTP failure never undoes a cancellation/refund."""
    pending = PurchaseRefund.objects.filter(email_sent_at__isnull=True)
    if refund_ids is not None:
        pending = pending.filter(pk__in=refund_ids)
    sent = 0
    for pk in pending.values_list("pk", flat=True):
        try:
            with transaction.atomic():
                refund = PurchaseRefund.objects.select_for_update().get(pk=pk)
                if refund.email_sent_at:
                    continue
                email = refund.purchase.user.email
                if not email:
                    continue
                context = {
                    "refund": refund,
                    "purchase": refund.purchase,
                    "user": refund.purchase.user,
                    "notice": refund.notice,
                }
                html_body = render_to_string("emails/refund_notice.html", context)
                text_body = refund.notice
                
                msg = EmailMultiAlternatives(
                    subject="Función cancelada · Devolución simulada",
                    body=text_body,
                    from_email=None,
                    to=[email],
                )
                msg.attach_alternative(html_body, "text/html")
                delivered = msg.send()

                if delivered:
                    refund.email_sent_at = timezone.now()
                    refund.save(update_fields=["email_sent_at"])
                    sent += 1
                if delivered:
                    refund.email_sent_at = timezone.now()
                    refund.save(update_fields=["email_sent_at"])
                    sent += 1
        except Exception:
            logger.exception("No se pudo enviar el aviso de devolución %s", pk)
    return sent
