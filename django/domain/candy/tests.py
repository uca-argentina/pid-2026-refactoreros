import json
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from domain.movies.models import Movie
from domain.rooms.models import Room
from domain.screenings.models import Screening
from domain.seat_types.models import SeatType
from domain.seats.models import Seat
from domain.tickets.models import PurchaseRefund, SeatReservation, TicketPurchase
from domain.users.models import Customer, Manager, Operator, Usher

from .models import CandyCombo, CandyComboItem, CandyOrder, CandyPickup, CandyProduct, reservation_code_for_token
from .services import (
    buy_tickets_with_candy,
    deliver_candy_order,
    inspect_candy_order,
    undo_candy_pickup,
)


class CandyFixture(TestCase):
    def setUp(self):
        User = get_user_model()
        self.customer = User.objects.create_user(username="cliente@example.com", email="cliente@example.com")
        Customer.objects.create(user=self.customer)
        self.operator = User.objects.create_user(username="operador")
        Operator.objects.create(user=self.operator)
        self.manager = User.objects.create_user(username="gerente")
        Manager.objects.create(user=self.manager)
        CandyCombo.objects.all().delete()
        CandyProduct.objects.all().delete()
        self.popcorn = CandyProduct.objects.create(
            name="Pochoclos grandes", category=CandyProduct.Category.POPCORN, price=Decimal("1500"), stock=5,
        )
        self.soda = CandyProduct.objects.create(
            name="Gaseosa", category=CandyProduct.Category.DRINKS, price=Decimal("800"), stock=10,
        )
        self.combo = CandyCombo.objects.create(name="Combo Pareja", price=Decimal("2600"))
        CandyComboItem.objects.create(combo=self.combo, product=self.popcorn, quantity=1)
        CandyComboItem.objects.create(combo=self.combo, product=self.soda, quantity=2)

        movie = Movie.objects.create(
            title="Película con candy", synopsis="", genre=Movie.Genre.ACCION,
            rating=Movie.Rating.ATP, duration_minutes=120, image="test.jpg",
        )
        room = Room.objects.create(name="Sala candy")
        seat_type = SeatType.objects.order_by("pk").first()
        Seat.objects.create(room=room, row=0, column=0, seat_type=seat_type)
        Seat.objects.create(room=room, row=0, column=1, seat_type=seat_type)
        self.screening = Screening.objects.create(
            movie=movie, room=room, starts_at=timezone.now() + timedelta(hours=1),
            status=Screening.Status.PUBLISHED, ticket_price=Decimal("1000"),
        )
        self.purchase = TicketPurchase.buy(self.customer, self.screening, 1)

    def order_for(self, items, purchase=None):
        return CandyOrder.create_for(purchase or self.purchase, items)


class CandyStockTests(CandyFixture):
    def test_combo_availability_comes_from_its_products(self):
        self.assertEqual(self.combo.available_stock, 5)
        self.soda.stock = 3
        self.soda.save()
        self.assertEqual(CandyCombo.objects.get(pk=self.combo.pk).available_stock, 1)
        self.assertEqual(self.combo.contents_label, "Pochoclos grandes + 2 × Gaseosa")
        self.assertEqual(self.combo.saving, Decimal("500"))

    def test_order_discounts_stock_of_products_and_combo_components(self):
        order = self.order_for([
            {"kind": "combo", "id": self.combo.pk, "quantity": 2},
            {"kind": "product", "id": self.soda.pk, "quantity": 1},
        ])

        self.popcorn.refresh_from_db()
        self.soda.refresh_from_db()
        self.assertEqual(self.popcorn.stock, 3)
        self.assertEqual(self.soda.stock, 5)
        self.assertEqual(order.total, Decimal("6000"))
        self.assertEqual(order.item_count, 3)
        self.assertEqual(order.summary, "2 × Combo Pareja, 1 × Gaseosa")

    def test_insufficient_stock_rejects_the_whole_order(self):
        with self.assertRaisesMessage(ValidationError, "No queda stock suficiente de Gaseosa"):
            self.order_for([
                {"kind": "combo", "id": self.combo.pk, "quantity": 5},
                {"kind": "product", "id": self.soda.pk, "quantity": 1},
            ])

        self.soda.refresh_from_db()
        self.popcorn.refresh_from_db()
        self.assertEqual((self.popcorn.stock, self.soda.stock), (5, 10))
        self.assertFalse(CandyOrder.objects.exists())

    def test_paused_products_and_invalid_selections_are_rejected(self):
        self.soda.is_active = False
        self.soda.save()
        with self.assertRaisesMessage(ValidationError, "ya no está a la venta"):
            self.order_for([{"kind": "product", "id": self.soda.pk, "quantity": 1}])
        for invalid in ([{"kind": "otro", "id": 1, "quantity": 1}], [{"kind": "combo", "id": "x", "quantity": 1}], "nada"):
            with self.assertRaises(ValidationError):
                self.order_for(invalid)
        with self.assertRaisesMessage(ValidationError, "hasta 10 unidades"):
            self.order_for([{"kind": "product", "id": self.popcorn.pk, "quantity": 11}])

    def test_paused_product_still_sells_inside_an_active_combo(self):
        self.soda.is_active = False
        self.soda.save()
        order = self.order_for([{"kind": "combo", "id": self.combo.pk, "quantity": 1}])
        self.assertEqual(order.total, Decimal("2600"))

    def test_empty_selection_creates_no_order(self):
        self.assertIsNone(self.order_for([{"kind": "product", "id": self.soda.pk, "quantity": 0}]))
        self.assertFalse(CandyOrder.objects.exists())

    def test_candy_failure_rolls_back_the_ticket_purchase(self):
        SeatReservation.reserve(self.customer, self.screening, "1B")
        with self.assertRaises(ValidationError):
            buy_tickets_with_candy(
                self.customer, self.screening, [{"label": "1B"}],
                [{"kind": "product", "id": self.popcorn.pk, "quantity": 6}],
            )
        self.assertEqual(TicketPurchase.objects.filter(screening=self.screening).count(), 1)
        self.assertTrue(SeatReservation.objects.filter(screening=self.screening, label="1B").exists())


class CandyPickupTests(CandyFixture):
    def setUp(self):
        super().setUp()
        self.order = self.order_for([{"kind": "combo", "id": self.combo.pk, "quantity": 1}])

    def test_pickup_code_is_independent_from_the_ticket_code(self):
        self.assertRegex(self.order.pickup_code, r"^[A-Z2-9]{6}$")
        self.assertEqual(self.order.qr_payload, f"BCC:{self.order.pickup_code}")
        self.assertNotEqual(self.order.pickup_token, self.purchase.validation_token)
        with self.assertRaisesMessage(ValidationError, "No encontramos un retiro"):
            inspect_candy_order(self.purchase.validation_token, self.operator)

    def test_operator_delivers_only_once(self):
        preview = inspect_candy_order(self.order.qr_payload, self.operator)
        self.assertIsNone(preview.delivered_at)

        order, pickup = deliver_candy_order(self.order.pickup_code.lower(), self.operator)

        self.assertEqual(order.delivered_by, self.operator)
        self.assertEqual(pickup.order, order)
        with self.assertRaisesMessage(ValidationError, "ya fue entregado"):
            deliver_candy_order(self.order.qr_payload, self.operator)

    def test_pickup_is_allowed_during_projection_but_not_after_it_ends(self):
        self.screening.status = Screening.Status.IN_PROGRESS
        self.screening.save(update_fields=["status"])
        inspect_candy_order(self.order.qr_payload, self.operator)

        Screening.objects.filter(pk=self.screening.pk).update(starts_at=timezone.now() - timedelta(hours=3))
        with self.assertRaisesMessage(ValidationError, "El retiro venció"):
            deliver_candy_order(self.order.qr_payload, self.operator)

    def test_only_operators_and_managers_can_deliver(self):
        usher = get_user_model().objects.create_user(username="acomodador")
        Usher.objects.create(user=usher)
        with self.assertRaises(PermissionDenied):
            deliver_candy_order(self.order.qr_payload, usher)
        with self.assertRaises(PermissionDenied):
            deliver_candy_order(self.order.qr_payload, self.customer)
        deliver_candy_order(self.order.qr_payload, self.manager)

    def test_operator_can_undo_a_recent_delivery(self):
        _order, pickup = deliver_candy_order(self.order.qr_payload, self.operator)

        undo_candy_pickup(pickup.pk, self.operator)

        self.order.refresh_from_db()
        self.assertIsNone(self.order.delivered_at)
        deliver_candy_order(self.order.qr_payload, self.operator)
        CandyPickup.objects.filter(pk=pickup.pk).update(reverted_at=None, created_at=timezone.now() - timedelta(hours=1))
        with self.assertRaisesMessage(ValidationError, "ya venció"):
            undo_candy_pickup(pickup.pk, self.operator)

    def test_canceling_the_screening_refunds_candy_and_restocks_it(self):
        self.popcorn.refresh_from_db()
        self.assertEqual(self.popcorn.stock, 4)

        self.screening.change_status(Screening.Status.CANCELED)

        refund = PurchaseRefund.objects.get(purchase=self.purchase)
        self.assertEqual(refund.amount, self.purchase.total + Decimal("2600"))
        self.assertIn("entradas y candy", refund.notice)
        self.popcorn.refresh_from_db()
        self.soda.refresh_from_db()
        self.assertEqual((self.popcorn.stock, self.soda.stock), (5, 10))
        with self.assertRaisesMessage(ValidationError, "fue devuelto"):
            deliver_candy_order(self.order.qr_payload, self.operator)

    def test_delivered_candy_is_refunded_but_not_restocked(self):
        deliver_candy_order(self.order.qr_payload, self.operator)
        self.screening.change_status(Screening.Status.CANCELED)
        self.popcorn.refresh_from_db()
        self.assertEqual(self.popcorn.stock, 4)

    def test_order_retries_when_a_short_code_collides(self):
        calls = 0
        existing_code = self.order.pickup_code

        def collide_once(token):
            nonlocal calls
            calls += 1
            if calls == 1:
                return existing_code
            return reservation_code_for_token(token)

        second_purchase = TicketPurchase.buy(self.customer, self.screening, 1)
        with patch("domain.candy.models.reservation_code_for_token", side_effect=collide_once):
            second = self.order_for([{"kind": "product", "id": self.soda.pk, "quantity": 1}], second_purchase)

        self.assertNotEqual(second.pickup_code_digest, self.order.pickup_code_digest)


class CandyClientViewTests(CandyFixture):
    def test_seat_selection_offers_active_candy_with_stock(self):
        CandyProduct.objects.create(name="Producto pausado", price=Decimal("100"), stock=3, is_active=False)
        CandyProduct.objects.create(name="Sin stock", price=Decimal("100"), stock=0)
        self.client.force_login(self.customer)

        response = self.client.get(reverse("seat_selection", args=[self.screening.pk]))

        self.assertContains(response, "data-candy-picker")
        self.assertContains(response, "Combo Pareja")
        self.assertNotContains(response, "Ahorrás $500")
        self.assertNotContains(response, "Producto pausado")
        self.assertContains(response, "Agotado")
        self.assertContains(response, 'name="candy_items"')

    def test_customer_buys_tickets_with_candy_and_sees_its_own_qr(self):
        SeatReservation.reserve(self.customer, self.screening, "1B")
        self.client.force_login(self.customer)

        response = self.client.post(
            reverse("ticket_purchase", args=[self.screening.pk]),
            data={
                "selected_seats": json.dumps([{"label": "1B"}]),
                "candy_items": json.dumps([{"kind": "combo", "id": self.combo.pk, "quantity": 1}]),
            },
            follow=True,
        )

        self.assertRedirects(response, reverse("my_tickets"))
        self.assertContains(response, "y candy")
        purchase = TicketPurchase.objects.exclude(pk=self.purchase.pk).get()
        order = CandyOrder.objects.get(purchase=purchase)
        self.assertContains(response, reverse("candy_detail", args=[purchase.pk]))
        self.assertContains(response, "QR CANDY")

        detail = self.client.get(reverse("candy_detail", args=[purchase.pk]))
        self.assertContains(detail, order.qr_payload)
        self.assertContains(detail, order.pickup_code)
        self.assertNotContains(detail, purchase.validation_code)
        self.assertIn("no-store", detail.headers["Cache-Control"])
        ticket = self.client.get(reverse("ticket_detail", args=[purchase.pk]))
        self.assertContains(ticket, "Tu candy")
        self.assertNotContains(ticket, order.pickup_code)

    def test_failed_candy_keeps_seats_reserved_and_shows_the_error(self):
        SeatReservation.reserve(self.customer, self.screening, "1B")
        self.client.force_login(self.customer)

        response = self.client.post(
            reverse("ticket_purchase", args=[self.screening.pk]),
            data={
                "selected_seats": json.dumps([{"label": "1B"}]),
                "candy_items": json.dumps([{"kind": "product", "id": self.popcorn.pk, "quantity": 6}]),
            },
            follow=True,
        )

        self.assertContains(response, "No queda stock suficiente de Pochoclos grandes")
        self.assertEqual(TicketPurchase.objects.count(), 1)

    def test_candy_detail_is_only_available_to_the_buyer(self):
        self.order_for([{"kind": "product", "id": self.soda.pk, "quantity": 1}])
        self.client.force_login(self.operator)
        self.assertEqual(self.client.get(reverse("candy_detail", args=[self.purchase.pk])).status_code, 404)


class CandyManagerViewTests(CandyFixture):
    def test_manager_creates_a_product_and_a_combo(self):
        self.client.force_login(self.manager)
        response = self.client.post(reverse("manager:candy_products_create"), {
            "name": "Nachos", "category": CandyProduct.Category.SNACKS, "price": "1300", "stock": "20", "is_active": "on",
        })
        self.assertRedirects(response, reverse("manager:candy_products_list"))
        nachos = CandyProduct.objects.get(name="Nachos")

        response = self.client.post(reverse("manager:candy_combos_create"), {
            "name": "Combo Nachos", "price": "1800", "is_active": "on",
            f"product_{nachos.pk}": "1", f"product_{self.soda.pk}": "1", f"product_{self.popcorn.pk}": "0",
        })

        self.assertRedirects(response, reverse("manager:candy_combos_list"))
        combo = CandyCombo.objects.get(name="Combo Nachos")
        self.assertEqual(
            {(item.product_id, item.quantity) for item in combo.items.all()},
            {(nachos.pk, 1), (self.soda.pk, 1)},
        )
        listing = self.client.get(reverse("manager:candy_combos_list"))
        self.assertContains(listing, "Nachos + Gaseosa")

    def test_combo_edit_replaces_its_products_and_requires_two_units(self):
        self.client.force_login(self.manager)
        url = reverse("manager:candy_combos_update", args=[self.combo.pk])

        invalid = self.client.post(url, {"name": "Combo Pareja", "price": "2600", f"product_{self.soda.pk}": "1"})
        self.assertContains(invalid, "al menos dos unidades")

        self.client.post(url, {"name": "Combo Pareja", "price": "2600", "is_active": "on", f"product_{self.soda.pk}": "3"})
        self.assertEqual(
            list(self.combo.items.values_list("product_id", "quantity")),
            [(self.soda.pk, 3)],
        )

    def test_products_in_a_combo_cannot_be_deleted(self):
        self.client.force_login(self.manager)
        response = self.client.post(reverse("manager:candy_products_delete", args=[self.popcorn.pk]), follow=True)
        self.assertContains(response, "forma parte de un combo")
        self.assertTrue(CandyProduct.objects.filter(pk=self.popcorn.pk).exists())

    def test_products_list_flags_low_stock(self):
        self.client.force_login(self.manager)
        response = self.client.get(reverse("manager:candy_products_list"))
        self.assertContains(response, "Stock bajo")
        self.assertContains(response, reverse("manager:candy_combos_list"))

    def test_operator_delivers_from_the_panel_but_cannot_manage_candy(self):
        order = self.order_for([{"kind": "combo", "id": self.combo.pk, "quantity": 1}])
        self.client.force_login(self.operator)
        url = reverse("manager:entregar_candy")

        preview = self.client.post(url, {"code": order.qr_payload, "action": "preview"})
        self.assertContains(preview, "Retiro encontrado")
        self.assertContains(preview, "Combo Pareja")
        self.assertContains(preview, "Pochoclos grandes + 2 × Gaseosa")

        response = self.client.post(url, {"code": order.pickup_code, "action": "deliver"}, follow=True)
        self.assertContains(response, "Candy entregado")
        self.assertContains(response, "Deshacer")
        order.refresh_from_db()
        self.assertIsNotNone(order.delivered_at)

        again = self.client.post(url, {"code": order.pickup_code, "action": "preview"})
        self.assertContains(again, "ya fue entregado")
        self.assertEqual(self.client.get(reverse("manager:candy_products_list")).status_code, 403)

    def test_operator_panel_links_to_candy_pickup(self):
        self.client.force_login(self.operator)
        response = self.client.get(reverse("manager:validar_entradas"))
        self.assertContains(response, reverse("manager:entregar_candy"))
        self.assertContains(response, 'data-qr-prefix="BC2:"')
        self.assertContains(self.client.get(reverse("manager:entregar_candy")), 'data-qr-prefix="BCC:"')
