from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from domain.cinema.models import CinemaSettings
from domain.screenings.models import Screening
from domain.tickets.models import TicketPurchase, reservation_code_digest
from domain.tickets.services import normalize_purchase_credential
from domain.users.roles import can_validate_tickets

from .models import CANDY_QR_PREFIX, CandyCombo, CandyOrder, CandyPickup, CandyProduct

NOT_FOUND_MESSAGE = "No encontramos un retiro de candy con ese código."


def candy_menu():
    combos = [
        combo
        for combo in CandyCombo.objects.filter(is_active=True).prefetch_related("items__product")
        if combo.items.all()
    ]
    products = CandyProduct.in_menu_order(CandyProduct.objects.filter(is_active=True))
    return {"combos": combos, "products": products}


def buy_tickets_with_candy(user, screening, selected_seats, candy_items):
    with transaction.atomic():
        purchase = TicketPurchase.buy(
            user=user,
            screening=screening,
            quantity=len(selected_seats),
            selected_seats=selected_seats,
            require_reservation=True,
        )
        CandyOrder.create_for(purchase, candy_items)
    return purchase


def pickup_filters(code):
    credential = normalize_purchase_credential(
        code,
        qr_prefix=CANDY_QR_PREFIX,
        invalid_message="El código de retiro no es válido.",
    )
    if len(credential) == 32:
        return {"pickup_token": credential}
    return {"pickup_code_digest": reservation_code_digest(credential)}


def check_candy_order(order):
    if order.is_refunded:
        raise ValidationError("La función está cancelada. Este candy fue devuelto.")
    if order.is_expired:
        raise ValidationError("El retiro venció: la función no está habilitada o ya finalizó.")
    if order.delivered_at is not None:
        raise ValidationError(
            f"Este candy ya fue entregado el {timezone.localtime(order.delivered_at):%d/%m a las %H:%M}."
        )


def inspect_candy_order(code, operator):
    if not can_validate_tickets(operator):
        raise PermissionDenied
    order = CandyOrder.objects.select_related(
        "purchase__screening__movie", "purchase__screening__room", "purchase__refund",
    ).filter(**pickup_filters(code)).first()
    if order is None:
        raise ValidationError(NOT_FOUND_MESSAGE)
    check_candy_order(order)
    return order


def deliver_candy_order(code, operator):
    if not can_validate_tickets(operator):
        raise PermissionDenied
    filters = pickup_filters(code)
    candidate = CandyOrder.objects.select_related("purchase").filter(**filters).first()
    if candidate is None:
        raise ValidationError(NOT_FOUND_MESSAGE)
    with transaction.atomic():
        if not candidate.is_reward_order and not Screening.objects.select_for_update().filter(pk=candidate.purchase.screening_id).exists():
            raise ValidationError("La función no existe.")
        try:
            order = CandyOrder.objects.select_for_update().get(**filters)
        except CandyOrder.DoesNotExist:
            raise ValidationError(NOT_FOUND_MESSAGE)
        check_candy_order(order)
        # Conditional delivery is also safe on databases without row-level locks.
        delivered_at = timezone.now()
        if not CandyOrder.objects.filter(pk=order.pk, delivered_at__isnull=True).update(delivered_at=delivered_at, delivered_by=operator):
            raise ValidationError("Este candy ya fue entregado.")
        order.delivered_at = delivered_at
        order.delivered_by = operator
        pickup = CandyPickup.objects.create(order=order, operator=operator)
        if order.is_reward_order:
            from domain.games.services import audit
            order.prize_coupons.filter(status="requested").update(status="redeemed", redeemed_at=delivered_at, redeemed_by=operator)
            audit(order.reward_user, "coupon_redeemed", {"order": order.pk, "coupons": list(order.prize_coupons.values_list("pk", flat=True))}, operator)
        return order, pickup


def undo_candy_pickup(pickup_id, operator):
    if not can_validate_tickets(operator):
        raise PermissionDenied
    try:
        pickup_id = int(pickup_id)
    except (TypeError, ValueError):
        raise ValidationError("La entrega a deshacer no es válida.")
    with transaction.atomic():
        pickup = CandyPickup.objects.select_for_update(of=("self",)).select_related(
            "order__purchase",
        ).filter(pk=pickup_id, operator=operator).first()
        if pickup is None:
            raise ValidationError("No encontramos esa entrega en tu historial.")
        if pickup.reverted_at is not None:
            raise ValidationError("Esta entrega ya fue deshecha.")
        now = timezone.now()
        undo_seconds = CinemaSettings.current().admission_undo_seconds
        if pickup.created_at < now - timedelta(seconds=undo_seconds):
            raise ValidationError("El plazo para deshacer esta entrega ya venció.")
        if not pickup.order.is_reward_order and not Screening.objects.select_for_update().filter(pk=pickup.order.purchase.screening_id).exists():
            raise ValidationError("La función ya no existe.")
        order = CandyOrder.objects.select_for_update().get(pk=pickup.order_id)
        if order.is_refunded:
            raise ValidationError("La función fue cancelada y el candy ya se devolvió.")
        order.delivered_at = None
        order.delivered_by = None
        order.save(update_fields=["delivered_at", "delivered_by"])
        if order.is_reward_order:
            from domain.games.services import audit
            order.prize_coupons.update(status="requested", redeemed_at=None, redeemed_by=None)
            audit(order.reward_user, "prize_delivery_undone", {"order": order.pk}, operator)
        pickup.reverted_at = now
        pickup.save(update_fields=["reverted_at"])
        return pickup
