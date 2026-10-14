from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from domain.movies.models import Movie
from domain.rooms.models import Room
from domain.screenings.models import Screening
from domain.users.models import Customer, Manager, Operator, Usher
from .models import AdmissionValidation, PurchaseRefund, TicketPurchase, reservation_code_for_token
from .services import inspect_ticket, undo_ticket_validation, validate_ticket


class AdmissionFixture(TestCase):
    def setUp(self):
        User = get_user_model()
        self.customer = User.objects.create_user(username="buyer", email="buyer@example.com")
        Customer.objects.create(user=self.customer)
        self.operator = User.objects.create_user(username="operator")
        Operator.objects.create(user=self.operator)
        self.manager = User.objects.create_user(username="manager")
        Manager.objects.create(user=self.manager)
        movie = Movie.objects.create(title="Película", synopsis="", genre="ACCION", rating="ATP", duration_minutes=120, image="test.jpg")
        room = Room.objects.create(name="Sala 1")
        self.screening = Screening.objects.create(
            movie=movie, room=room, starts_at=timezone.now() + timedelta(hours=1),
            status=Screening.Status.PUBLISHED, ticket_price=Decimal("1000"), capacity_snapshot=4,
        )
        self.purchase = TicketPurchase.buy(self.customer, self.screening, 4)


class PurchaseAdmissionTests(AdmissionFixture):
    def test_operator_can_validate_during_projection(self):
        self.screening.status = Screening.Status.IN_PROGRESS
        self.screening.save(update_fields=["status"])

        purchase, validated, _ = validate_ticket(
            self.purchase.validation_token, self.operator, quantity=1
        )

        self.assertEqual(purchase.pk, self.purchase.pk)
        self.assertEqual(len(validated), 1)

    def test_purchase_has_one_qr_credential_and_short_visible_code(self):
        self.assertRegex(self.purchase.validation_code, r"^[A-Z2-9]{6}$")
        self.assertRegex(self.purchase.validation_token, r"^[A-Za-z0-9_-]{32}$")
        self.assertEqual(self.purchase.qr_payload, f"BC2:{self.purchase.validation_code}")
        self.assertNotEqual(self.purchase.validation_code_digest, self.purchase.validation_code)
        self.assertEqual(self.purchase.tickets.count(), 4)

    def test_one_qr_supports_partial_validation(self):
        purchase, validated, _ = validate_ticket(self.purchase.qr_payload, self.operator, quantity=2)
        self.assertEqual(len(validated), 2)
        self.assertEqual(purchase.remaining_quantity, 2)
        _, validated, _ = validate_ticket(self.purchase.validation_code, self.operator, quantity=2)
        self.assertEqual(len(validated), 2)
        with self.assertRaisesMessage(ValidationError, "ya no tiene entradas"):
            validate_ticket(self.purchase.validation_token, self.operator)

    def test_cannot_validate_more_than_the_purchase_has_left(self):
        with self.assertRaisesMessage(ValidationError, "Solo quedan 4"):
            validate_ticket(self.purchase.validation_token, self.operator, quantity=5)

    def test_operator_can_validate_specific_seats(self):
        purchase, validated, _ = validate_ticket(
            self.purchase.validation_token, self.operator, ticket_numbers=[2, 4]
        )
        self.assertEqual([ticket.number for ticket in validated], [2, 4])
        self.assertEqual(purchase.remaining_quantity, 2)

    def test_operator_can_undo_a_recent_validation(self):
        _, tickets, validation = validate_ticket(
            self.purchase.validation_token, self.operator, ticket_numbers=[1, 2]
        )
        _, reverted = undo_ticket_validation(validation.pk, self.operator)
        self.assertEqual([ticket.pk for ticket in reverted], [ticket.pk for ticket in tickets])
        self.assertFalse(self.purchase.tickets.filter(pk__in=[ticket.pk for ticket in tickets], used_at__isnull=False).exists())
        validation.refresh_from_db()
        self.assertIsNotNone(validation.reverted_at)

    def test_preview_does_not_consume_entries(self):
        purchase = inspect_ticket(self.purchase.validation_token, self.operator)
        self.assertEqual(purchase.remaining_quantity, 4)

    def test_short_reservation_code_is_case_insensitive(self):
        purchase = inspect_ticket(self.purchase.validation_code.lower(), self.operator)
        self.assertEqual(purchase.pk, self.purchase.pk)

    @override_settings(SECRET_KEY="a-rotated-secret-key")
    def test_existing_ticket_remains_valid_after_secret_key_rotation(self):
        purchase = inspect_ticket(self.purchase.validation_code, self.operator)
        self.assertEqual(purchase.pk, self.purchase.pk)

    def test_purchase_retries_when_a_short_code_collides(self):
        calls = 0
        existing_code = self.purchase.validation_code

        def collide_once(token):
            nonlocal calls
            calls += 1
            if calls == 1:
                return existing_code
            return reservation_code_for_token(token)

        with patch(
            "domain.tickets.models.reservation_code_for_token",
            side_effect=collide_once,
        ):
            second_purchase = TicketPurchase(
                user=self.customer,
                screening=self.screening,
                quantity=1,
                total=Decimal("1000"),
            )
            second_purchase.save()

        self.assertNotEqual(
            second_purchase.validation_code_digest,
            self.purchase.validation_code_digest,
        )
        self.assertEqual(second_purchase.tickets.count(), 1)

    def test_invalid_code_inactive_operator_and_usher_are_rejected(self):
        with self.assertRaises(ValidationError):
            validate_ticket("not-a-valid-code", self.operator)
        self.operator.is_active = False
        with self.assertRaises(PermissionDenied):
            validate_ticket(self.purchase.validation_token, self.operator)
        usher = get_user_model().objects.create_user(username="usher")
        Usher.objects.create(user=usher)
        with self.assertRaises(PermissionDenied):
            validate_ticket(self.purchase.validation_token, usher)

    def test_canceling_creates_refund_and_blocks_remaining_entries(self):
        validate_ticket(self.purchase.validation_token, self.operator, quantity=1)
        self.screening.change_status(Screening.Status.CANCELED)
        self.assertEqual(PurchaseRefund.objects.get(purchase=self.purchase).amount, self.purchase.total)
        with self.assertRaises(ValidationError):
            validate_ticket(self.purchase.validation_token, self.operator)


class PurchaseAdmissionViewTests(AdmissionFixture):
    def test_operator_preview_names_the_last_available_seat_on_the_validation_button(self):
        tickets = list(self.purchase.tickets.order_by("number"))
        tickets[-1].seat_label = "3B"
        tickets[-1].save(update_fields=["seat_label"])
        self.purchase.tickets.exclude(pk=tickets[-1].pk).update(
            used_at=timezone.now(),
            used_by=self.operator,
        )
        self.client.force_login(self.operator)

        response = self.client.post(reverse("manager:validar_entradas"), {
            "code": self.purchase.validation_code,
            "action": "preview",
        })

        self.assertContains(response, 'data-single-seat-label="3B"')
        self.assertContains(response, "Validar ingreso · 3B")

    def test_operator_history_is_paginated_and_limited_to_last_24_hours(self):
        ticket = self.purchase.tickets.first()
        expired_validation = AdmissionValidation.objects.create(
            purchase=self.purchase,
            operator=self.operator,
        )
        expired_validation.tickets.add(ticket)
        AdmissionValidation.objects.filter(pk=expired_validation.pk).update(
            created_at=timezone.now() - timedelta(hours=24, seconds=1)
        )
        recent_validations = []
        for _ in range(16):
            validation = AdmissionValidation.objects.create(
                purchase=self.purchase,
                operator=self.operator,
            )
            validation.tickets.add(ticket)
            recent_validations.append(validation)

        self.client.force_login(self.operator)
        url = reverse("manager:validar_entradas")
        first_page = self.client.get(url)

        self.assertContains(first_page, "Tu historial de validaciones recientes")
        self.assertContains(first_page, "24 horas")
        self.assertEqual(first_page.context["validation_history_page"].paginator.count, 16)
        self.assertEqual(len(first_page.context["validation_history"]), 15)
        self.assertNotIn(expired_validation.pk, [
            validation.pk for validation in first_page.context["validation_history"]
        ])

        second_page = self.client.get(url, {"page": 2})

        self.assertEqual(second_page.context["validation_history_page"].number, 2)
        self.assertEqual(len(second_page.context["validation_history"]), 1)
        self.assertIn(
            second_page.context["validation_history"][0].pk,
            [validation.pk for validation in recent_validations],
        )

    def test_customer_sees_one_compact_purchase_and_one_qr_for_purchase(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse("my_tickets"))
        self.assertContains(response, "MOSTRAR QR")
        self.assertContains(response, "has-imminent-ticket")
        self.assertContains(response, "is-imminent-ticket")
        self.assertNotContains(response, "Entrada 1")
        detail = self.client.get(reverse("ticket_detail", args=[self.purchase.pk]))
        self.assertContains(detail, self.purchase.validation_code)
        self.assertContains(detail, "data-qr-payload")
        self.assertContains(detail, "qrcode.min.js")

    def test_customer_can_poll_a_summary_of_their_validated_entries(self):
        validate_ticket(self.purchase.validation_code, self.operator, ticket_numbers=[1, 2])
        self.client.force_login(self.customer)

        response = self.client.get(reverse("ticket_admission_status", args=[self.purchase.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            "used_count": 2,
            "remaining_count": 2,
            "room": "Sala 1",
            "used_seat_summary": "Entrada 1 · Entrada 2",
        })

    def test_customer_sees_and_reads_their_cancellation_notification(self):
        self.screening.change_status(Screening.Status.CANCELED)
        refund = PurchaseRefund.objects.get(purchase=self.purchase)
        self.assertIsNone(refund.read_at)
        self.client.force_login(self.customer)

        response = self.client.get(reverse("notifications"))

        self.assertContains(response, "Función cancelada")
        self.assertContains(response, "Devolución registrada")
        refund.refresh_from_db()
        self.assertIsNotNone(refund.read_at)

    def test_finished_purchase_moves_to_history_without_a_qr(self):
        self.screening.starts_at = timezone.now() - timedelta(hours=3)
        self.screening.save(update_fields=["starts_at"])
        self.client.force_login(self.customer)
        response = self.client.get(reverse("my_tickets"))
        self.assertContains(response, "Función finalizada")
        self.assertContains(response, "Ver detalle")
        self.assertNotContains(response, "MOSTRAR QR")
        detail = self.client.get(reverse("ticket_detail", args=[self.purchase.pk]))
        self.assertContains(detail, "Detalle de la compra")
        self.assertContains(detail, "Función finalizada")
        self.assertNotContains(detail, "data-qr-payload")

    def test_operator_confirms_selected_quantity_and_has_no_management_access(self):
        self.client.force_login(self.operator)
        url = reverse("manager:validar_entradas")
        response = self.client.post(url, {
            "code": self.purchase.qr_payload, "ticket_numbers": [1, 2], "action": "validate",
        })
        self.assertEqual(response.status_code, 302)
        self.purchase.refresh_from_db()
        self.assertEqual(self.purchase.remaining_quantity, 2)
        self.assertEqual(self.client.get(reverse("manager:peliculas_list")).status_code, 403)

    def test_qr_detail_is_only_available_to_the_buyer(self):
        self.client.force_login(self.operator)
        self.assertEqual(self.client.get(reverse("ticket_detail", args=[self.purchase.pk])).status_code, 404)

    def test_manager_designates_and_removes_operator_from_user_status_actions(self):
        self.client.force_login(self.manager)
        url = reverse("manager:usuarios_update", args=[self.customer.pk])
        response = self.client.get(url)
        self.assertContains(response, "Designar como operador")
        action = reverse("manager:usuarios_toggle_operator", args=[self.customer.pk])
        self.assertEqual(self.client.post(action).status_code, 302)
        self.assertTrue(Operator.objects.filter(user=self.customer).exists())
        self.assertContains(self.client.get(url), "Quitar rol de operador")
        self.client.post(action)
        self.assertFalse(Operator.objects.filter(user=self.customer).exists())
