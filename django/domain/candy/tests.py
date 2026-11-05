import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, TransactionTestCase
from django.db import close_old_connections, connection
from django.urls import reverse
from django.utils import timezone

from domain.movies.models import Movie
from domain.cinema.models import CinemaSettings
from domain.rooms.models import Room
from domain.screenings.models import Screening
from domain.seat_types.models import SeatType
from domain.seats.models import Seat
from domain.tickets.models import PurchaseRefund, SeatReservation, TicketPurchase
from domain.users.models import Customer, Manager, Operator, Usher

from .models import CandyCombo, CandyComboItem, CandyOrder, CandyPickup, CandyProduct, reservation_code_for_token
from .services import (
    buy_candy_only,
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


class StandaloneCandyTests(CandyFixture):
    def selection(self, quantity=1):
        return [{"kind": "product", "id": self.popcorn.pk, "quantity": quantity, "unit_price": "0", "subtotal": "0"}]

    def test_server_prices_stock_origin_and_idempotency(self):
        checkout_key = uuid.uuid4()
        order = buy_candy_only(self.customer, self.selection(2), checkout_key)
        self.assertEqual(order.total, Decimal("3000"))
        self.assertEqual(order.customer, self.customer)
        self.assertIsNone(order.purchase_id)
        self.assertFalse(order.is_reward_order)
        self.assertTrue(order.pickup_open)
        self.assertEqual(buy_candy_only(self.customer, self.selection(2), checkout_key).pk, order.pk)
        self.popcorn.refresh_from_db()
        self.assertEqual(self.popcorn.stock, 3)
        with self.assertRaises(ValidationError):
            buy_candy_only(self.customer, self.selection(1), checkout_key)
        with self.assertRaises(ValidationError):
            buy_candy_only(self.customer, self.selection(4), uuid.uuid4())
        self.assertEqual(CandyOrder.objects.count(), 1)
        self.assertEqual(TicketPurchase.objects.count(), 1)

    def test_combo_stock_delivery_and_undo_use_existing_flow(self):
        order = buy_candy_only(self.customer, [{"kind": "combo", "id": self.combo.pk, "quantity": 1}], uuid.uuid4())
        self.assertEqual(order.total, Decimal("2600"))
        self.assertEqual(inspect_candy_order(order.qr_payload, self.operator).pk, order.pk)
        delivered, pickup = deliver_candy_order(order.qr_payload, self.operator)
        self.assertEqual(delivered.user_id, self.customer.pk)
        with self.assertRaises(ValidationError):
            deliver_candy_order(order.qr_payload, self.operator)
        self.client.force_login(self.operator)
        self.assertContains(self.client.get(reverse("manager:entregar_candy")), f"Pedido de Candy #{order.pk}")
        undo_candy_pickup(pickup.pk, self.operator)
        order.refresh_from_db()
        self.assertTrue(order.pickup_open)
        self.popcorn.refresh_from_db()
        self.soda.refresh_from_db()
        self.assertEqual((self.popcorn.stock, self.soda.stock), (4, 8))

    def test_automatic_checkout_validation_privacy_csrf_and_qr(self):
        self.assertEqual(self.client.get(reverse("candy_store")).status_code, 302)
        self.client.force_login(self.customer)
        payload = {"checkout_key": str(uuid.uuid4()), "candy_items": "[]"}
        self.assertRedirects(self.client.post(reverse("candy_purchase"), payload), reverse("candy_store"))
        self.assertFalse(CandyOrder.objects.exists())
        self.popcorn.refresh_from_db()
        self.assertEqual(self.popcorn.stock, 5)
        payload["candy_items"] = json.dumps(self.selection())
        store = self.client.get(reverse("candy_store"))
        self.assertNotContains(store, "simulado")
        self.assertNotContains(store, 'name="payment_result"')
        for _ in range(2):
            response = self.client.post(reverse("candy_purchase"), payload)
            self.assertEqual(response.status_code, 302)
        order = CandyOrder.objects.get()
        self.assertRedirects(response, reverse("candy_order_detail", args=[order.pk]))
        self.assertContains(self.client.get(response.url), order.qr_payload)
        self.assertContains(self.client.get(response.url), "Pago aprobado")
        self.assertNotContains(self.client.get(response.url), "simulado")
        self.assertContains(self.client.get(reverse("candy_store")), "Mis pedidos de retiro")
        self.assertEqual(self.client.get(reverse("candy_purchase")).status_code, 405)
        from django.test import Client
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.customer)
        self.assertEqual(strict.post(reverse("candy_purchase"), payload).status_code, 403)
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get(response.url).status_code, 404)
        self.assertNotContains(self.client.get(reverse("candy_store")), reverse("candy_order_detail", args=[order.pk]))

    def test_empty_invalid_and_insufficient_combo_do_not_create_orders(self):
        for items in ([], "bad", self.selection(11), [{"kind": "combo", "id": self.combo.pk, "quantity": 6}]):
            with self.subTest(items=items), self.assertRaises(ValidationError):
                buy_candy_only(self.customer, items, uuid.uuid4())
        self.assertFalse(CandyOrder.objects.exists())
        self.popcorn.refresh_from_db()
        self.assertEqual(self.popcorn.stock, 5)


class UnifiedCandyOrdersTests(CandyFixture):
    def setUp(self):
        super().setUp()
        self.attached = self.order_for([{"kind": "product", "id": self.popcorn.pk, "quantity": 1}])
        self.standalone = buy_candy_only(self.customer, [{"kind": "product", "id": self.popcorn.pk, "quantity": 1}], uuid.uuid4())
        self.reward = CandyOrder.objects.create(reward_user=self.customer, reward_key=uuid.uuid4(), total=0, items=self.attached.items)
        self.foreign = buy_candy_only(self.manager, [{"kind": "product", "id": self.popcorn.pk, "quantity": 1}], uuid.uuid4())
        self.client.force_login(self.customer)

    def test_all_sources_share_one_private_list_and_detail(self):
        response = self.client.get(reverse("candy_store"))
        self.assertEqual({order.pk for order in response.context["orders"]}, {self.attached.pk, self.standalone.pk, self.reward.pk})
        self.assertContains(response, 'data-candy-order=', count=3)
        self.assertContains(response, "Premio de ruleta")
        self.assertContains(response, "Con tus entradas")
        for order in (self.attached, self.standalone, self.reward):
            detail = self.client.get(reverse("candy_order_detail", args=[order.pk]))
            self.assertContains(detail, order.qr_payload)
            self.assertContains(detail, reverse("candy_store") + "#mis-retiros")
            self.assertEqual(detail.context["client_nav_section"], "candy")
        self.assertEqual(self.client.get(reverse("candy_order_detail", args=[self.foreign.pk])).status_code, 404)
        self.assertNotContains(response, reverse("candy_order_detail", args=[self.foreign.pk]))
        old_detail = self.client.get(reverse("candy_detail", args=[self.purchase.pk]))
        self.assertContains(old_detail, self.attached.qr_payload)
        self.assertEqual(old_detail.context["client_nav_section"], "candy")

    def test_reprogramming_tickets_preserves_attached_candy_and_its_qr(self):
        self.screening.starts_at = timezone.now() + timedelta(hours=3)
        self.screening.save(update_fields=["starts_at"])
        new_screening = Screening.objects.create(
            movie=self.screening.movie, room=self.screening.room,
            starts_at=timezone.now() + timedelta(hours=5),
            status=Screening.Status.PUBLISHED, ticket_price=Decimal("1000"),
        )
        self.assertEqual(self.client.get(reverse("screening_reprogram", args=[self.purchase.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("seat_reprogram_selection", args=[self.purchase.pk, new_screening.pk])).status_code, 200)
        SeatReservation.reserve(self.customer, new_screening, "1A")
        original_qr = self.attached.qr_payload
        self.popcorn.refresh_from_db()
        original_stock = self.popcorn.stock
        response = self.client.post(reverse("screening_reprogram_confirm", args=[self.purchase.pk, new_screening.pk]),
            {"selected_seats": json.dumps([{"label": "1A"}])})
        self.assertRedirects(response, reverse("my_tickets"))
        self.purchase.refresh_from_db()
        self.assertEqual(self.purchase.screening_id, new_screening.pk)
        self.attached.refresh_from_db()
        self.assertEqual(self.attached.qr_payload, original_qr)
        self.assertEqual(self.attached.purchase_id, self.purchase.pk)
        self.popcorn.refresh_from_db()
        self.assertEqual(self.popcorn.stock, original_stock)
        self.assertContains(self.client.get(reverse("candy_order_detail", args=[self.attached.pk])), original_qr)

    def test_configured_reprogramming_window_applies_to_ui_direct_urls_and_confirmation(self):
        config = CinemaSettings.objects.create(ticket_reprogram_minutes=120)
        self.screening.starts_at = timezone.now() + timedelta(minutes=60)
        self.screening.save(update_fields=["starts_at"])
        target = Screening.objects.create(movie=self.screening.movie, room=self.screening.room,
            starts_at=timezone.now() + timedelta(hours=4), status=Screening.Status.PUBLISHED, ticket_price=Decimal("1000"))
        options_url = reverse("screening_reprogram", args=[self.purchase.pk])
        seats_url = reverse("seat_reprogram_selection", args=[self.purchase.pk, target.pk])
        confirm_url = reverse("screening_reprogram_confirm", args=[self.purchase.pk, target.pk])
        payload = {"selected_seats": json.dumps([{"label": "1A"}])}
        detail_url = reverse("ticket_detail", args=[self.purchase.pk])
        self.assertFalse(self.client.get(detail_url).context["reprogram_opition_avialable"])
        for url in (options_url, seats_url):
            self.assertRedirects(self.client.get(url), reverse("my_tickets"))
        self.client.post(confirm_url, payload)
        self.purchase.refresh_from_db()
        self.assertEqual(self.purchase.screening_id, self.screening.pk)
        config.ticket_reprogram_minutes = 30
        config.save(update_fields=["ticket_reprogram_minutes"])
        self.assertTrue(self.client.get(detail_url).context["reprogram_opition_avialable"])
        self.assertEqual(self.client.get(options_url).status_code, 200)
        self.assertEqual(self.client.get(seats_url).status_code, 200)
        SeatReservation.reserve(self.customer, target, "1A")
        self.assertRedirects(self.client.post(confirm_url, payload), reverse("my_tickets"))
        self.purchase.refresh_from_db()
        self.assertEqual(self.purchase.screening_id, target.pk)

    def test_reprogramming_deadline_default_exact_boundary_and_zero(self):
        from domain.tickets.services import reprogramming_window_is_open
        now = timezone.now()
        config = CinemaSettings()
        self.assertEqual(config.ticket_reprogram_minutes, 120)
        self.screening.starts_at = now + timedelta(minutes=60)
        self.assertFalse(reprogramming_window_is_open(self.screening, cinema=config, now=now))
        config.ticket_reprogram_minutes = 30
        self.assertTrue(reprogramming_window_is_open(self.screening, cinema=config, now=now))
        self.screening.starts_at = now + timedelta(minutes=30)
        self.assertFalse(reprogramming_window_is_open(self.screening, cinema=config, now=now))
        self.screening.starts_at += timedelta(microseconds=1)
        self.assertTrue(reprogramming_window_is_open(self.screening, cinema=config, now=now))
        config.ticket_reprogram_minutes = 0
        self.screening.starts_at = now + timedelta(seconds=1)
        self.assertTrue(reprogramming_window_is_open(self.screening, cinema=config, now=now))
        self.screening.starts_at = now
        self.assertFalse(reprogramming_window_is_open(self.screening, cinema=config, now=now))

    def test_ready_orders_precede_delivered_and_invalid_orders_have_no_qr(self):
        deliver_candy_order(self.standalone.qr_payload, self.operator)
        self.screening.starts_at = timezone.now() - timedelta(days=1)
        self.screening.save(update_fields=["starts_at"])
        response = self.client.get(reverse("candy_store"))
        self.assertEqual(response.context["orders"][0].pk, self.reward.pk)
        self.assertContains(response, 'class="ticket-qr-link is-imminent-ticket"', count=1)
        self.assertContains(response, "Vencido")
        self.assertContains(response, "Retirado")
        expired = self.client.get(reverse("candy_order_detail", args=[self.attached.pk]))
        self.assertNotContains(expired, 'data-qr-payload=')
        self.screening.status = Screening.Status.CANCELED
        self.screening.save(update_fields=["status"])
        response = self.client.get(reverse("candy_store"))
        self.assertContains(response, "Devuelto")
        self.assertContains(response, 'class="ticket-qr-link is-imminent-ticket"', count=1)


class StandaloneCandyConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.users = [get_user_model().objects.create_user(username=f"candy-concurrent-{i}") for i in range(2)]
        self.product = CandyProduct.objects.create(name="Último pochoclo", price=100, stock=1)

    def concurrent_orders(self, user_ids):
        if connection.vendor != "postgresql":
            self.skipTest("La verificación de bloqueos requiere PostgreSQL.")
        barrier = Barrier(2)
        checkout_key = uuid.uuid4()
        def buy(user_id):
            close_old_connections()
            try:
                user = get_user_model().objects.get(pk=user_id)
                barrier.wait(timeout=10)
                return buy_candy_only(user, [{"kind": "product", "id": self.product.pk, "quantity": 1}], checkout_key).pk
            except ValidationError:
                return None
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(buy, user_ids))

    def test_parallel_customers_cannot_oversell_stock(self):
        results = self.concurrent_orders([user.pk for user in self.users])
        self.assertEqual(sum(result is not None for result in results), 1)
        self.assertEqual(CandyOrder.objects.count(), 1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 0)

    def test_parallel_retries_create_one_order_and_spend_stock_once(self):
        results = self.concurrent_orders([self.users[0].pk] * 2)
        self.assertIsNotNone(results[0])
        self.assertEqual(results[0], results[1])
        self.assertEqual(CandyOrder.objects.count(), 1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 0)


class CandyStockTests(CandyFixture):
    def test_configured_limit_applies_to_products_combos_and_aggregated_selection(self):
        from .services import candy_menu
        config = CinemaSettings.objects.create(candy_max_item_quantity=2)
        self.assertEqual(self.popcorn.max_quantity, 2)
        self.assertEqual(self.combo.max_quantity, 2)
        menu = candy_menu()
        with self.assertNumQueries(0):
            self.assertTrue(all(item.max_quantity <= 2 for item in menu["products"] + menu["combos"]))
        for selection in (
            [{"kind": "product", "id": self.popcorn.pk, "quantity": 3}],
            [{"kind": "combo", "id": self.combo.pk, "quantity": 3}],
            [{"kind": "product", "id": self.popcorn.pk, "quantity": 2}, {"kind": "product", "id": self.popcorn.pk, "quantity": 1}],
        ):
            with self.assertRaisesMessage(ValidationError, "hasta 2 unidades"):
                self.order_for(selection)
        config.candy_max_item_quantity = 20
        config.save(update_fields=["candy_max_item_quantity"])
        self.assertEqual(self.popcorn.max_quantity, 5)
        self.assertEqual(self.combo.max_quantity, 5)
        CandyProduct.objects.filter(pk=self.popcorn.pk).update(stock=30)
        order = self.order_for([{"kind": "product", "id": self.popcorn.pk, "quantity": 11}])
        self.assertEqual(order.item_count, 11)

    def test_lowering_limit_preserves_idempotent_orders_but_blocks_new_purchases(self):
        config = CinemaSettings.objects.create(candy_max_item_quantity=3)
        selection = [{"kind": "product", "id": self.popcorn.pk, "quantity": 3}]
        checkout_key = uuid.uuid4()
        order = buy_candy_only(self.customer, selection, checkout_key)
        config.candy_max_item_quantity = 1
        config.save(update_fields=["candy_max_item_quantity"])
        self.assertEqual(buy_candy_only(self.customer, selection, checkout_key).pk, order.pk)
        with self.assertRaisesMessage(ValidationError, "hasta 1 unidad"):
            buy_candy_only(self.customer, selection, uuid.uuid4())
        self.popcorn.refresh_from_db()
        self.assertEqual(self.popcorn.stock, 2)
        self.assertEqual(CandyOrder.objects.count(), 1)

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
    def test_candy_codes_in_admission_show_specific_error_without_using_either_qr(self):
        self.client.force_login(self.operator)
        order = self.order_for([{"kind": "product", "id": self.popcorn.pk, "quantity": 1}])
        url = reverse("manager:validar_entradas")
        for code in (order.pickup_code.lower(), order.pickup_token, order.qr_payload):
            for action in ("preview", "validate"):
                with self.subTest(code_type=len(code), action=action):
                    response = self.client.post(url, {"code": code, "action": action, "ticket_numbers": ["1"]})
                    self.assertContains(response, "Este código corresponde a un pedido de Candy.")
                    self.assertNotContains(response, "No encontramos una entrada con ese código.")
        order.refresh_from_db()
        self.assertIsNone(order.delivered_at)
        self.assertFalse(self.purchase.tickets.filter(used_at__isnull=False).exists())

    def test_switching_qr_modes_only_prefills_and_never_delivers(self):
        self.client.force_login(self.operator)
        order = self.order_for([{"kind": "product", "id": self.popcorn.pk, "quantity": 1}])
        response = self.client.get(reverse("manager:entregar_candy"), {"code": order.qr_payload})
        self.assertEqual(response.context["form"].initial["code"], order.pickup_code)
        self.assertContains(response, "data-qr-mismatch")
        order.refresh_from_db()
        self.assertIsNone(order.delivered_at)
        response = self.client.get(reverse("manager:validar_entradas"), {"code": self.purchase.qr_payload})
        self.assertEqual(response.context["form"].initial["code"], self.purchase.validation_code)
        self.assertFalse(self.purchase.tickets.filter(used_at__isnull=False).exists())

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
