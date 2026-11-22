from copy import deepcopy
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ValidationError
from django.test import TestCase, SimpleTestCase

from domain.rooms.models import Room
from domain.tickets.test_admission import AdmissionFixture
from toolbox.orm import (
    a_diccionarios, buscar_uno, buscar_usuario_por_email, compras_de,
    editar_campos, entrada_de, entradas_sin_usar, exigir_uno, filtrar,
    ordenar, separar_butaca, total_butacas, valores,
)


class QueryHelpersTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.a = Room.objects.create(name="Sala A")
        cls.b = Room.objects.create(name="Sala B")

    def test_queries_preserve_existing_scope(self):
        scope = Room.objects.filter(pk=self.a.pk)
        self.assertEqual(list(filtrar(scope, "name", "sala", comparacion="contiene")), [self.a])
        self.assertIsNone(buscar_uno(scope, pk=self.b.pk))
        self.assertEqual(list(ordenar(scope, "name")), [self.a])

    def test_comparisons_and_sorting(self):
        self.assertEqual(valores(ordenar(Room, "name", descendente=True), "name"), ["Sala B", "Sala A"])
        self.assertEqual(valores(filtrar(Room, "id", [self.a.pk], comparacion="en"), "name"), ["Sala A"])
        self.assertEqual(filtrar(Room, "id", self.a.pk, comparacion="mayor").get(), self.b)
        self.assertEqual(filtrar(Room, "name", "sala a", comparacion="igual_sin_mayusculas").get(), self.a)
        for comparison in ("menor", "menor_o_igual", "mayor_o_igual", "igual", "empieza_con", "es_nulo"):
            value = False if comparison == "es_nulo" else "Sala A" if comparison == "empieza_con" else self.a.pk
            field = "name" if comparison == "empieza_con" else "pk"
            list(filtrar(Room, field, value, comparacion=comparison))

    def test_one_missing_and_ambiguous(self):
        self.assertEqual(exigir_uno(Room, pk=self.a.pk), self.a)
        self.assertIsNone(buscar_uno(Room, pk=0))
        with self.assertRaises(ValidationError):
            exigir_uno(Room, pk=0)
        with self.assertRaises(ValidationError):
            buscar_uno(Room)

    def test_invalid_filter_options(self):
        for comparison, value in [("desconocida", 1), ("en", "12"), ("es_nulo", "false")]:
            with self.assertRaises(ValidationError):
                filtrar(Room, "pk", value, comparacion=comparison)
        with self.assertRaises(ValidationError):
            ordenar(Room, "-name")

    def test_values_are_materialized(self):
        self.assertEqual(a_diccionarios(Room.objects.filter(pk=self.a.pk), "name"), [{"name": "Sala A"}])

    def test_edit_validates_and_reads_latest_row(self):
        stale = Room.objects.get(pk=self.a.pk)
        Room.objects.filter(pk=self.a.pk).update(layout_configuration={"rows": 4})
        changed = editar_campos(stale, name="Sala renovada")
        self.assertEqual(changed.name, "Sala renovada")
        self.assertEqual(changed.layout_configuration, {"rows": 4})
        stale.refresh_from_db()
        self.assertEqual(stale.name, "Sala renovada")

    def test_rejected_edit_does_not_persist(self):
        for changes in ({"name": "Sala B"}, {"layout_configuration": {}}, {"name": "x" * 101}, {}):
            with self.assertRaises(ValidationError):
                editar_campos(self.a, **changes)
        self.a.refresh_from_db()
        self.assertEqual(self.a.name, "Sala A")

    def test_email_ambiguity_inactive_and_normalization(self):
        user = get_user_model().objects.create_user(username="one", email="One@local.test")
        self.assertEqual(buscar_usuario_por_email("  one@LOCAL.test  "), user)
        for email in ("", "not-an-email", "missing@local.test", None):
            with self.assertRaises(ValidationError):
                buscar_usuario_por_email(email)
        user.is_active = False
        user.save()
        with self.assertRaises(ValidationError):
            buscar_usuario_por_email("one@local.test")
        user.is_active = True
        user.save()
        get_user_model().objects.create_user(username="two", email="one@local.test")
        with self.assertRaises(ValidationError):
            buscar_usuario_por_email("one@local.test")


class OwnershipHelpersTests(AdmissionFixture):
    def test_owner_scope_cannot_be_widened(self):
        ticket = self.purchase.tickets.first()
        self.assertEqual(entrada_de(self.customer, self.purchase.pk, ticket.pk), ticket)
        self.assertIsNone(entrada_de(self.operator, self.purchase.pk, ticket.pk))
        self.assertIsNone(entrada_de(self.customer, 0, ticket.pk))
        self.assertFalse(compras_de(AnonymousUser()).exists())
        self.assertEqual(entradas_sin_usar(self.purchase).count(), 4)

    def test_purchase_edits_are_not_simple_edits(self):
        with self.assertRaises(ValidationError):
            editar_campos(self.purchase, quantity=1)
        self.purchase.refresh_from_db()
        self.assertEqual(self.purchase.quantity, 4)


class PayloadHelpersTests(SimpleTestCase):
    def test_split_is_a_deep_copy_and_keeps_prices(self):
        original = [
            {"label": "A1", "price": "8.20", "extra": {"promotion": "Promo"}},
            {"label": "A2", "price": "10.00"},
        ]
        before = deepcopy(original)
        chosen, remaining = separar_butaca(original, "A1")
        self.assertEqual(total_butacas(remaining), Decimal("10.00"))
        self.assertEqual(total_butacas([chosen]) + total_butacas(remaining), Decimal("18.20"))
        chosen["extra"]["promotion"] = "Cambio"
        remaining[0]["price"] = "0.00"
        self.assertEqual(original, before)
        self.assertEqual(total_butacas([]), Decimal("0"))

    def test_invalid_payloads_are_rejected(self):
        for payload in (None, ["A1"], [{}], [{"label": []}], [{"label": "A1"}] * 2):
            with self.assertRaises(ValidationError):
                separar_butaca(payload, "A1")
        with self.assertRaises(ValidationError):
            separar_butaca([{"label": "A1"}], "A2")
        for price in (None, "NaN", "Infinity", "-1", "invalid"):
            with self.assertRaises(ValidationError):
                total_butacas([{"price": price}])
        with self.assertRaises(ValidationError):
            total_butacas([{}])
