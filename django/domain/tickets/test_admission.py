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
from domain.users.models import Customer, Manager, Operator, Usher
from .models import PurchaseRefund, TicketPurchase
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
        with self.captureOnCommitCallbacks(execute=True), patch("domain.tickets.services.send_mail", return_value=1):
            self.screening.change_status(Screening.Status.CANCELED)
        self.assertEqual(PurchaseRefund.objects.get(purchase=self.purchase).amount, self.purchase.total)
        with self.assertRaises(ValidationError):
            validate_ticket(self.purchase.validation_token, self.operator)


class PurchaseAdmissionViewTests(AdmissionFixture):
    def test_customer_sees_one_compact_purchase_and_one_qr_for_purchase(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse("my_tickets"))
        self.assertContains(response, "MOSTRAR QR")
        self.assertContains(response, "has-imminent-ticket")
        self.assertNotContains(response, "Entrada 1")
        detail = self.client.get(reverse("ticket_detail", args=[self.purchase.pk]))
        self.assertContains(detail, self.purchase.validation_code)
        self.assertContains(detail, "data-qr-payload")
        self.assertContains(detail, "qrcode.min.js")

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
