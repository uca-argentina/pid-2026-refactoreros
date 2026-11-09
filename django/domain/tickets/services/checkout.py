"""Caso de uso transaccional: buy_tickets."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from domain.screenings.models import Screening
from domain.tickets.models import SeatPurchase, SeatReservation, TicketPurchase


def buy_tickets(user, screening, quantity, selected_seats=None, require_reservation=False):
    with transaction.atomic():
        quantity = int(quantity)
        screening = (
            Screening.objects.select_for_update().select_related("room").get(pk=screening.pk)
        )
        SeatReservation.clear_expired(screening)
        list(TicketPurchase.objects.select_for_update().filter(screening=screening))
        list(SeatPurchase.objects.select_for_update().filter(screening=screening))
        list(SeatReservation.objects.select_for_update().filter(screening=screening))
        total_seats, seat_quantity, selected_payload = TicketPurchase.total_for_seats(
            screening, selected_seats
        )
        if require_reservation and not selected_payload:
            raise ValidationError("Seleccioná al menos una butaca válida.")
        if selected_payload:
            occupied_labels = TicketPurchase.occupied_seats(screening)
            already_taken = [
                seat["label"] for seat in selected_payload if seat["label"] in occupied_labels
            ]
            if already_taken:
                raise ValidationError(
                    {"quantity": "Algunos asientos seleccionados ya no estan disponibles."}
                )
            if require_reservation:
                reserved_by_user = set(
                    SeatReservation.active_for(screening)
                    .filter(user=user)
                    .values_list("label", flat=True)
                )
                missing_reservations = [
                    seat["label"]
                    for seat in selected_payload
                    if seat["label"] not in reserved_by_user
                ]
                if missing_reservations:
                    raise ValidationError(
                        {"quantity": "Algunas butacas ya no estan reservadas para tu compra."}
                    )
        if seat_quantity:
            quantity = seat_quantity
        total = total_seats if total_seats is not None else screening.price_from * quantity
        purchase = TicketPurchase(
            user=user,
            screening=screening,
            quantity=quantity,
            total=total,
            selected_seats=selected_payload,
        )
        purchase.full_clean()
        purchase.save()
        sold_seats = [
            SeatPurchase(purchase=purchase, screening=screening, label=seat["label"])
            for seat in selected_payload
        ]
        try:
            SeatPurchase.objects.bulk_create(sold_seats)
        except IntegrityError:
            raise ValidationError(
                {"quantity": "Algunos asientos seleccionados ya no estan disponibles."}
            )
        if not selected_payload:
            TicketPurchase.sync_sold_seats(screening)
        if selected_payload:
            SeatReservation.objects.filter(
                screening=screening,
                user=user,
                label__in=[seat["label"] for seat in selected_payload],
            ).delete()
        return purchase
