from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from domain.candy.models import CandyOrder
from domain.cinema.models import CinemaSettings
from domain.screenings.models import Screening
from domain.tickets.models import PurchaseRefund, SeatPurchase, SeatReservation, TicketPurchase
from domain.tickets.services import reprogram_purchase, reprogramming_window_is_open
from web.tickets.tests import crear_funcion_con_butacas


class ReprogrammingTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="reprogramming")
        self.other = get_user_model().objects.create_user(username="other-reprogramming")
        self.original = crear_funcion_con_butacas("Original")
        self.target = crear_funcion_con_butacas("Destino")
        self.original.starts_at = timezone.now() + timedelta(days=1)
        self.original.save(update_fields=["starts_at"])
        self.target.movie = self.original.movie
        self.target.starts_at = self.original.starts_at + timedelta(days=1)
        self.target.prices_by_type = {key: "2000.00" for key in self.target.prices_by_type}
        self.target.save(update_fields=["movie", "starts_at", "prices_by_type"])
        self.purchase = TicketPurchase.buy(self.user, self.original, 1, selected_seats=["1A"])
        SeatReservation.reserve(self.user, self.target, "1B")

    def reprogram(self, **overrides):
        return reprogram_purchase(
            **{
                "user": self.user,
                "purchase_pk": self.purchase.pk,
                "new_screening_pk": self.target.pk,
                "selected_seats": ["1B"],
                **overrides,
            }
        )

    def assert_original_preserved(self):
        self.purchase.refresh_from_db()
        self.assertEqual(self.purchase.screening_id, self.original.pk)
        self.assertEqual(self.purchase.tickets.get().seat_label, "1A")
        self.assertTrue(
            SeatPurchase.objects.filter(
                purchase=self.purchase, screening=self.original, label="1A"
            ).exists()
        )

    def test_moves_seats_tickets_and_candy_without_replacing_credentials(self):
        order = CandyOrder.objects.create(purchase=self.purchase, total=100)
        code = self.purchase.validation_code
        purchase, previous = self.reprogram()
        self.assertEqual(previous, Decimal("1000.00"))
        self.assertEqual(purchase.total, Decimal("2000.00"))
        self.assertEqual(purchase.validation_code, code)
        self.assertEqual(purchase.tickets.get().seat_label, "1B")
        self.assertFalse(SeatPurchase.objects.filter(screening=self.original).exists())
        self.assertFalse(SeatReservation.active_for(self.target).filter(user=self.user).exists())
        order.refresh_from_db()
        self.assertEqual(order.purchase.screening_id, self.target.pk)
        self.assertEqual(order.total, 100)

    def test_rejects_other_user_and_different_movie(self):
        with self.assertRaises(ValidationError):
            self.reprogram(user=self.other)
        self.target.movie = crear_funcion_con_butacas("Otra película").movie
        self.target.save(update_fields=["movie"])
        with self.assertRaises(ValidationError):
            self.reprogram()
        self.assert_original_preserved()

    def test_deadline_excludes_exact_boundary(self):
        cinema = CinemaSettings(ticket_reprogram_minutes=120)
        deadline = self.original.starts_at - timedelta(minutes=120)
        self.assertTrue(
            reprogramming_window_is_open(
                self.original, cinema=cinema, now=deadline - timedelta(microseconds=1)
            )
        )
        self.assertFalse(reprogramming_window_is_open(self.original, cinema=cinema, now=deadline))
        with patch("domain.tickets.services.reprogramming.timezone.now", return_value=deadline):
            with self.assertRaises(ValidationError):
                self.reprogram()
        self.assert_original_preserved()

    def test_used_and_refunded_purchases_cannot_move(self):
        ticket = self.purchase.tickets.get()
        ticket.used_at = timezone.now()
        ticket.save(update_fields=["used_at"])
        with self.assertRaises(ValidationError):
            self.reprogram()
        ticket.used_at = None
        ticket.save(update_fields=["used_at"])
        PurchaseRefund.objects.create(
            purchase=self.purchase, amount=self.purchase.total, notice="Prueba"
        )
        with self.assertRaises(ValidationError):
            self.reprogram()
        self.assert_original_preserved()

    def test_quantity_expired_reservation_and_unpublished_target_are_rejected(self):
        with self.assertRaises(ValidationError):
            self.reprogram(selected_seats=["1A", "1B"])
        SeatReservation.objects.filter(screening=self.target).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        with self.assertRaises(ValidationError):
            self.reprogram()
        self.target.status = Screening.Status.DRAFT
        self.target.save(update_fields=["status"])
        with self.assertRaises(ValidationError):
            self.reprogram()
        self.assert_original_preserved()

    def test_failure_after_purchase_update_rolls_back_all_changes(self):
        with patch(
            "domain.tickets.models.AdmissionTicket.objects.bulk_update",
            side_effect=RuntimeError("fallo simulado"),
        ):
            with self.assertRaises(RuntimeError):
                self.reprogram()
        self.assert_original_preserved()
        self.assertTrue(SeatReservation.active_for(self.target).filter(user=self.user).exists())
