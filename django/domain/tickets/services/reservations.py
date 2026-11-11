"""Caso de uso transaccional: reserve_seat."""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from domain.screenings.models import Screening
from domain.tickets.models import SeatReservation, TicketPurchase


def reserve_seat(user, screening, label):
    with transaction.atomic():
        screening = Screening.objects.select_for_update().get(pk=screening.pk)
        if screening.status != Screening.Status.PUBLISHED or screening.starts_at <= timezone.now():
            raise ValidationError("Esta función no tiene entradas a la venta.")
        SeatReservation.clear_expired(screening)
        if label not in TicketPurchase.seat_prices(screening):
            raise ValidationError("La butaca no es valida para esta funcion.")
        if label in TicketPurchase.occupied_seats(screening):
            raise ValidationError("La butaca ya fue comprada.")

        reservation = (
            SeatReservation.objects.select_for_update()
            .filter(
                screening=screening,
                label=label,
            )
            .first()
        )
        expiration = timezone.now() + SeatReservation.duration()
        if (
            reservation
            and reservation.user_id != user.pk
            and reservation.expires_at > timezone.now()
        ):
            raise ValidationError("La butaca esta reservada temporalmente.")
        if reservation:
            reservation.user = user
            reservation.expires_at = expiration
            reservation.save(update_fields=["user", "expires_at", "updated_at"])
        else:
            reservation = SeatReservation.objects.create(
                user=user,
                screening=screening,
                label=label,
                expires_at=expiration,
            )
        return reservation
