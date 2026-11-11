"""Reprogramming."""

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from domain.cinema.models import CinemaSettings
from domain.screenings.models import Screening
from domain.tickets.models import AdmissionTicket, SeatPurchase, SeatReservation, TicketPurchase


def reprogramming_deadline(screening, *, cinema=None):
    cinema = cinema if cinema is not None else CinemaSettings.current()
    return screening.starts_at - timedelta(minutes=cinema.ticket_reprogram_minutes)


def reprogramming_window_is_open(screening, *, cinema=None, now=None):
    now = now if now is not None else timezone.now()
    return screening.status == Screening.Status.PUBLISHED and now < reprogramming_deadline(
        screening, cinema=cinema
    )


def check_reprogramming_window(screening):
    cinema = CinemaSettings.current()
    if not reprogramming_window_is_open(screening, cinema=cinema):
        minutes = cinema.ticket_reprogram_minutes
        raise ValidationError(
            f"La reprogramación solo está permitida hasta {minutes} {'minuto' if minutes == 1 else 'minutos'} antes del inicio de la función."
        )


@transaction.atomic
def reprogram_purchase(*, user, purchase_pk, new_screening_pk, selected_seats):
    old_screening_id = (
        TicketPurchase.objects.filter(pk=purchase_pk, user=user)
        .values_list("screening_id", flat=True)
        .first()
    )
    if old_screening_id is None:
        raise ValidationError("No encontramos esa compra.")

    screenings = {
        s.pk: s
        for s in Screening.objects.select_for_update()
        .filter(pk__in=[old_screening_id, new_screening_pk])
        .order_by("pk")
    }
    old_screening = screenings.get(old_screening_id)
    new_screening = screenings.get(new_screening_pk)
    if new_screening is None:
        raise ValidationError("La función elegida no existe.")

    purchase = TicketPurchase.objects.select_for_update().get(pk=purchase_pk, user=user)
    if purchase.screening_id != old_screening.pk:
        raise ValidationError("La compra ya fue modificada. Volvé a intentarlo.")

    now = timezone.now()
    if hasattr(purchase, "refund"):
        raise ValidationError("Esta compra fue reembolsada y no se puede reprogramar.")
    check_reprogramming_window(old_screening)
    if AdmissionTicket.objects.filter(purchase=purchase, used_at__isnull=False).exists():
        raise ValidationError("Ya usaste entradas de esta compra, no se puede reprogramar.")
    if new_screening.pk == old_screening.pk or new_screening.movie_id != old_screening.movie_id:
        raise ValidationError("Solo podés reprogramar a otra función de la misma película.")
    if new_screening.status != Screening.Status.PUBLISHED or new_screening.starts_at <= now:
        raise ValidationError("La función elegida no tiene entradas a la venta.")

    SeatReservation.clear_expired(new_screening)
    list(TicketPurchase.objects.select_for_update().filter(screening=new_screening))
    list(SeatPurchase.objects.select_for_update().filter(screening=new_screening))
    list(SeatReservation.objects.select_for_update().filter(screening=new_screening))

    total, seat_quantity, payload = TicketPurchase.total_for_seats(new_screening, selected_seats)
    if seat_quantity != purchase.quantity:
        raise ValidationError(
            f"Tenés que elegir exactamente {purchase.quantity} "
            f"butaca{'s' if purchase.quantity != 1 else ''}."
        )
    labels = [seat["label"] for seat in payload]

    if TicketPurchase.available_for(new_screening) < purchase.quantity:
        raise ValidationError("No hay lugar suficiente en esa función.")
    if set(labels) & TicketPurchase.occupied_seats(new_screening):
        raise ValidationError("Algunas butacas seleccionadas ya no están disponibles.")
    reserved_by_user = set(
        SeatReservation.active_for(new_screening).filter(user=user).values_list("label", flat=True)
    )
    if not set(labels) <= reserved_by_user:
        raise ValidationError("Algunas butacas ya no están reservadas para tu compra.")

    previous_total = purchase.total
    SeatPurchase.objects.filter(purchase=purchase).delete()
    purchase.screening = new_screening
    purchase.selected_seats = payload
    purchase.total = total
    purchase.save(update_fields=["screening", "selected_seats", "total"])
    SeatPurchase.objects.bulk_create(
        [SeatPurchase(purchase=purchase, screening=new_screening, label=label) for label in labels]
    )

    tickets = list(purchase.tickets.order_by("number"))
    for ticket, label in zip(tickets, labels):
        ticket.seat_label = label
    AdmissionTicket.objects.bulk_update(tickets, ["seat_label"])

    SeatReservation.objects.filter(screening=new_screening, user=user, label__in=labels).delete()
    return purchase, previous_total
