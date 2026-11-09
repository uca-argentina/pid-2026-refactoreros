"""Refunds."""

import logging
from threading import Thread

from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from domain.tickets.models import PurchaseRefund, SeatReservation, TicketPurchase

logger = logging.getLogger(__name__)


def refund_canceled_screening(screening):
    from domain.candy.models import CandyOrder

    refund_ids = []
    for purchase in TicketPurchase.objects.filter(screening=screening):
        candy_order = CandyOrder.objects.filter(purchase=purchase).first()
        amount = purchase.total + (candy_order.total if candy_order else 0)
        notice = (
            f"Se canceló la función de {screening.movie.title} del "
            f"{timezone.localtime(screening.starts_at):%d/%m/%Y %H:%M}. "
            f"Registramos una devolución de ${amount:.2f} "
            f"por tu compra #{purchase.pk}{' (entradas y candy)' if candy_order else ''}. "
            "No se realizó un movimiento de dinero real."
        )
        refund, _ = PurchaseRefund.objects.get_or_create(
            purchase=purchase,
            defaults={"amount": amount, "notice": notice},
        )
        if candy_order:
            candy_order.restock()
        if refund.email_sent_at is None:
            refund_ids.append(refund.pk)
    SeatReservation.objects.filter(screening=screening).delete()
    return refund_ids


def enqueue_refund_notifications(refund_ids):
    if not refund_ids:
        return
    Thread(
        target=send_refund_notifications,
        args=(refund_ids,),
        daemon=True,
        name="refund-notifications",
    ).start()


def send_refund_notifications(refund_ids=None):
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
                    subject="Función cancelada · Devolución registrada",
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
        except Exception:
            logger.exception("No se pudo enviar el aviso de devolución %s", pk)
    return sent
