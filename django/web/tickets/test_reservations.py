import json

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from domain.tickets.models import SeatPurchase, SeatReservation, TicketPurchase
from .tests import crear_funcion_con_butacas


class ReservationInputTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="reservation-input")
        self.client.force_login(self.user)
        self.screening = crear_funcion_con_butacas()

    def test_non_object_json_is_rejected_without_server_error(self):
        for route in ("seat_reservation", "seat_reservation_batch"):
            for payload in ([], None, "seat", 42, True):
                with self.subTest(route=route, payload=payload):
                    response = self.client.post(
                        reverse(route, args=[self.screening.pk]),
                        json.dumps(payload),
                        content_type="application/json",
                    )
                    self.assertEqual(response.status_code, 400)
        self.assertFalse(SeatReservation.objects.exists())

    def test_invalid_seat_selection_cannot_fall_back_to_quantity_purchase(self):
        for selection in ([{}], [None], [{"label": []}], [{"label": 1}], [], None):
            with self.subTest(selection=selection), self.assertRaises(ValidationError):
                TicketPurchase.buy(
                    self.user, self.screening, 1, selected_seats=selection, require_reservation=True
                )
        self.assertFalse(TicketPurchase.objects.exists())

    def test_invalid_operation_types_and_large_batches_are_controlled(self):
        url = reverse("seat_reservation", args=[self.screening.pk])
        for payload in ({"label": [], "action": "reserve"}, {"label": "1A", "action": []}):
            self.assertEqual(
                self.client.post(
                    url, json.dumps(payload), content_type="application/json"
                ).status_code,
                400,
            )
        batch = reverse("seat_reservation_batch", args=[self.screening.pk])
        response = self.client.post(
            batch,
            json.dumps({"operations": [{"label": "1A", "action": "reserve"}] * 101}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_reading_availability_does_not_repair_or_delete_records(self):
        purchase = TicketPurchase.buy(self.user, self.screening, 1, selected_seats=["1A"])
        SeatPurchase.objects.filter(purchase=purchase).delete()
        from django.utils import timezone
        from datetime import timedelta

        reservation = SeatReservation.objects.create(
            user=self.user,
            screening=self.screening,
            label="1B",
            expires_at=timezone.now() - timedelta(minutes=1),
        )
        self.assertEqual(TicketPurchase.available_for(self.screening), 1)
        self.assertIn("1A", TicketPurchase.occupied_seats(self.screening))
        self.assertFalse(SeatPurchase.objects.filter(purchase=purchase).exists())
        self.assertFalse(SeatReservation.active_for(self.screening).exists())
        self.assertTrue(SeatReservation.objects.filter(pk=reservation.pk).exists())
