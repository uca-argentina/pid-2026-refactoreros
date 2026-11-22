import uuid
from copy import deepcopy

from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from domain.candy.models import CandyOrder
from domain.candy.services import buy_candy_only
from domain.candy.tests import CandyFixture
from domain.games.models import GameEvent, PrizeCoupon, Question, QuestionUse, TriviaRun, WheelConfig, WheelSlot, WheelSpin
from domain.rooms.models import Room
from domain.users.models import Manager
from django.contrib.auth import get_user_model
from toolbox.candy import editar_componentes_combo, pedido_de, pedidos_de, seleccion_candy
from toolbox.juegos import cupones_de, editar_pregunta, historial_juegos_de, partida_publica_de
from toolbox.orm import buscar_texto, describir_campos


class SelectionTests(SimpleTestCase):
    def test_builds_payload_without_mutating_inputs(self):
        products, combos = {2: 3, 4: 0}, {2: 1}
        self.assertEqual(seleccion_candy(productos=products, combos=combos), [
            {"kind": "product", "id": 2, "quantity": 3},
            {"kind": "combo", "id": 2, "quantity": 1},
        ])
        self.assertEqual(products, {2: 3, 4: 0})
        self.assertEqual(seleccion_candy(), [])
        for invalid in ([1], {True: 1}, {1: False}, {1: -1}, {"1": 2}):
            with self.assertRaises(ValidationError):
                seleccion_candy(productos=invalid)


class CandyToolboxTests(CandyFixture):
    def test_all_order_origins_are_scoped_to_owner(self):
        attached = self.order_for(seleccion_candy(productos={self.soda.pk: 1}))
        standalone = buy_candy_only(self.customer, seleccion_candy(productos={self.soda.pk: 1}), uuid.uuid4())
        reward = CandyOrder.objects.create(reward_user=self.customer, reward_key=uuid.uuid4(), total=0, items=[])
        self.assertEqual(set(pedidos_de(self.customer).values_list("pk", flat=True)), {attached.pk, standalone.pk, reward.pk})
        for order in (attached, standalone, reward):
            self.assertEqual(pedido_de(self.customer, order.pk), order)
            self.assertIsNone(pedido_de(self.operator, order.pk))
        self.assertFalse(pedidos_de(AnonymousUser()).exists())

    def test_combo_uses_form_rules_and_preserves_order_snapshot(self):
        order = self.order_for(seleccion_candy(combos={self.combo.pk: 1}))
        snapshot = deepcopy(order.items)
        stocks = (self.popcorn.stock, self.soda.stock)
        self.combo.image = "candy/previous.png"
        self.combo.save()
        combo = editar_componentes_combo(self.manager, self.combo.pk, {self.soda.pk: 3})
        self.assertEqual(dict(combo.items.values_list("product_id", "quantity")), {self.soda.pk: 3})
        self.assertEqual(combo.image.name, "candy/previous.png")
        order.refresh_from_db()
        self.assertEqual(order.items, snapshot)
        self.popcorn.refresh_from_db()
        self.soda.refresh_from_db()
        self.assertEqual((self.popcorn.stock, self.soda.stock), (stocks[0]-1, stocks[1]-2))

    def test_rejected_combo_edit_preserves_components(self):
        before = dict(self.combo.items.values_list("product_id", "quantity"))
        for quantities in ({self.soda.pk: 1}, {self.soda.pk: 21}, {999999: 2}, {}, None):
            with self.assertRaises(ValidationError):
                editar_componentes_combo(self.manager, self.combo.pk, quantities)
        self.assertEqual(dict(self.combo.items.values_list("product_id", "quantity")), before)
        with self.assertRaises(PermissionDenied):
            editar_componentes_combo(self.operator, self.combo.pk, {self.soda.pk: 2})

    def test_coupon_and_public_game_scope(self):
        slot = WheelSlot.objects.create(kind="prize", label="Premio", product=self.soda)
        spin = WheelSpin.objects.create(user=self.customer, key=uuid.uuid4(), slot=slot, label="Premio", kind="prize", layout=[], index=0)
        coupon = PrizeCoupon.objects.create(spin=spin, user=self.customer, product=self.soda, label="Premio")
        self.assertEqual(list(cupones_de(self.customer, estado="available")), [coupon])
        self.assertFalse(cupones_de(self.operator).exists())
        self.assertFalse(cupones_de(AnonymousUser()).exists())
        with self.assertRaises(ValidationError):
            cupones_de(self.customer, estado="invalid")
        private = [{"text": "Pregunta", "options": ["A", "B", "C"], "correct": 1, "difficulty": 1}]
        run = TriviaRun.objects.create(user=self.customer, key=uuid.uuid4(), questions=private, source="daily")
        public = partida_publica_de(self.customer, run.pk)
        self.assertNotIn("correct", public["question"])
        self.assertNotIn("questions", public)
        self.assertIsNone(partida_publica_de(self.operator, run.pk))
        self.assertEqual(run.answers.count(), 0)
        event = GameEvent.objects.create(user=self.customer, actor=self.manager, kind="test")
        GameEvent.objects.create(user=None, actor=self.customer, kind="global")
        self.assertEqual(list(historial_juegos_de(self.customer)), [event])


class QuestionEditingTests(TestCase):
    def setUp(self):
        self.manager = get_user_model().objects.create_user(username="manager-toolbox")
        Manager.objects.create(user=self.manager)
        self.regular = get_user_model().objects.create_user(username="regular-toolbox")
        self.question = Question.objects.create(text="Original", options=["A", "B", "C"], correct=0, difficulty=1)
        self.config, _ = WheelConfig.objects.get_or_create(pk=1)

    def test_edit_preserves_existing_runs_and_cooldown_history(self):
        private = [{"id": self.question.pk, "text": "Original", "options": ["A", "B", "C"], "correct": 0, "difficulty": 1}]
        run = TriviaRun.objects.create(user=self.regular, key=uuid.uuid4(), questions=private, source="extra", finished_at=timezone.now())
        usage = QuestionUse.objects.create(question=self.question, run=run, fingerprint="a"*64)
        old_revision = self.config.revision
        changed = editar_pregunta(self.manager, self.question.pk, text="Actualizada", options=["X", "Y", "Z"], correct=2)
        self.assertEqual(changed.options, ["X", "Y", "Z"])
        run.refresh_from_db()
        self.assertEqual(run.questions, private)
        self.assertTrue(QuestionUse.objects.filter(pk=usage.pk).exists())
        self.config.refresh_from_db()
        self.assertEqual(self.config.revision, old_revision+1)
        self.assertTrue(GameEvent.objects.filter(actor=self.manager, kind="question_saved", data__id=changed.pk).exists())

    def test_invalid_edit_rolls_back_revision_and_audit(self):
        revision = self.config.revision
        events = GameEvent.objects.count()
        for changes in ({"options": ["A", "A", "B"]}, {"correct": 3}, {"unknown": True}, {}):
            with self.assertRaises(ValidationError):
                editar_pregunta(self.manager, self.question.pk, **changes)
        self.question.refresh_from_db()
        self.config.refresh_from_db()
        self.assertEqual(self.question.text, "Original")
        self.assertEqual(self.config.revision, revision)
        self.assertEqual(GameEvent.objects.count(), events)
        with self.assertRaises(PermissionDenied):
            editar_pregunta(self.regular, self.question.pk, active=False)


class GeneralQueryTests(TestCase):
    def test_or_search_does_not_expand_scope(self):
        user = get_user_model().objects.create_user(username="target", first_name="Otro", last_name="Apellido")
        get_user_model().objects.create_user(username="other", first_name="TARGET")
        scope = get_user_model().objects.filter(pk=user.pk)
        self.assertEqual(list(buscar_texto(scope, "target", "username", "first_name")), [user])
        self.assertEqual(list(buscar_texto(scope, " ", "username")), [user])

    def test_metadata_does_not_query_database_or_include_properties(self):
        with self.assertNumQueries(0):
            fields = describir_campos(Room)
        self.assertIn("name", [f["nombre"] for f in fields])
        self.assertNotIn("capacity", [f["nombre"] for f in fields])
