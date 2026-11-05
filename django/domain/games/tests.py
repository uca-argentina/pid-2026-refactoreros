import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import OperationalError, close_old_connections
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from domain.candy.models import CandyOrder, CandyProduct
from domain.candy.services import deliver_candy_order, undo_candy_pickup
from domain.users.models import Manager, Operator
from . import services
from .models import GameAccount, GameEvent, PrizeCoupon, Question, QuestionUse, TriviaAnswer, TriviaRun, WheelConfig, WheelSlot, WheelSpin


def key():
    return uuid.uuid4()


class GameTests(TestCase):
    def test_admin_can_grant_single_question_extra_trivia(self):
        self.client.force_login(self.manager)
        payload = {"key": key(), "amount": 2, "reason": "Compensación", "reward": "attempt"}
        url = reverse("games:user", args=[self.user.pk])
        self.assertEqual(self.client.post(url, payload).status_code, 302)
        self.client.post(url, payload)
        account = GameAccount.objects.get(user=self.user)
        self.assertEqual((account.extra_attempts, account.spins), (2, 0))
        event = GameEvent.objects.get(kind="attempts_granted")
        self.assertEqual(event.actor, self.manager)

    def test_archived_slots_and_audit_export(self):
        self.client.force_login(self.manager)
        self.client.post(reverse("games:delete", args=["slot", self.slot.pk]))
        self.slot.refresh_from_db()
        self.assertFalse(self.slot.active)
        url = reverse("games:dashboard")
        self.assertNotContains(self.client.get(url, {"tab": "wheel"}), "Pochoclos")
        self.assertContains(self.client.get(url, {"tab": "archived"}), "Pochoclos")
        today = timezone.localdate().isoformat()
        query = {"tab": "events", "export": "csv", "date_from": today, "date_to": today}
        response = self.client.get(url, query)
        self.assertContains(response, "slot_archived")
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertNotContains(self.client.get(url, {**query, "date_from": "2099-01-01", "date_to": "2099-01-01"}), "slot_archived")
        self.assertEqual(self.client.get(url, {**query, "date_from": "2026-02-31"}).status_code, 400)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(url, query).status_code, 403)

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="player", password="game-test-password")
        self.other = User.objects.create_user(username="other")
        self.manager = User.objects.create_user(username="manager")
        Manager.objects.create(user=self.manager)
        self.operator = User.objects.create_user(username="operator")
        Operator.objects.create(user=self.operator)
        self.product = CandyProduct.objects.create(name="Premio test", price=100, stock=2)
        Question.objects.all().delete()
        for difficulty in (1, 2, 3):
            for variant in range(3):
                Question.objects.create(text=f"Pregunta {difficulty} variante {variant}", options=["A", "B", "C"], correct=1, difficulty=difficulty)
        WheelSlot.objects.all().delete()
        self.slot = WheelSlot.objects.create(kind="prize", label="Pochoclos", product=self.product)

    def credits(self, spins=1, attempts=0):
        return GameAccount.objects.create(user=self.user, spins=spins, extra_attempts=attempts)

    def test_three_questions_reward_and_no_correct_answer_exposure(self):
        run = services.start(self.user, key())
        self.assertNotIn("correct", json.dumps(run))
        for step in range(3):
            result = services.answer(self.user, run["id"], step, 1, key())
            self.assertTrue(result["correct"])
        self.assertTrue(result["run"]["finished"])
        self.assertNotIn("question", result["run"])
        self.assertEqual(GameAccount.objects.get(user=self.user).spins, 3)
        self.assertEqual(TriviaAnswer.objects.count(), 3)
        self.assertEqual(TriviaRun.objects.get().step, 3)

    def test_global_question_allocation_and_duplicate_text_cannot_repeat(self):
        first = services.start(self.user, key())
        second = services.start(self.other, key())
        run1 = TriviaRun.objects.get(pk=first["id"])
        run2 = TriviaRun.objects.get(pk=second["id"])
        self.assertTrue({q["id"] for q in run1.questions}.isdisjoint({q["id"] for q in run2.questions}))
        services.answer(self.user, first["id"], 0, 0, key())
        services.grant(self.manager, self.user, 2, "Prueba de oportunidades", key())
        third = services.start(self.user, key())
        run3 = TriviaRun.objects.get(pk=third["id"])
        self.assertTrue({q["id"] for q in run1.questions}.isdisjoint({q["id"] for q in run3.questions}))
        services.answer(self.user, third["id"], 0, 0, key())
        used = run1.questions[0]
        Question.objects.create(text="  " + used["text"].upper() + "  ", options=used["options"], correct=1, difficulty=1)
        with self.assertRaises(ValidationError): services.start(self.user, key())
        self.assertEqual(GameAccount.objects.get(user=self.user).extra_attempts, 1)
        self.assertFalse(services.state(self.user)["bank_ready"])

    def test_questions_reusable_after_exactly_24_hours_and_history_preserved(self):
        for difficulty in (1, 2, 3):
            keep = Question.objects.filter(difficulty=difficulty).first()
            Question.objects.filter(difficulty=difficulty).exclude(pk=keep.pk).delete()
        clock = timezone.now()
        with patch("domain.games.services.timezone.now", return_value=clock):
            first = services.start(self.user, key())
            services.answer(self.user, first["id"], 0, 0, key())
        QuestionUse.objects.update(created_at=clock)
        with patch("domain.games.services.timezone.now", return_value=clock + timedelta(hours=24) - timedelta(microseconds=1)):
            self.assertFalse(services.state(self.other)["bank_ready"])
            with self.assertRaises(ValidationError): services.start(self.other, key())
        with patch("domain.games.services.timezone.now", return_value=clock + timedelta(hours=24)):
            self.assertTrue(services.state(self.other)["bank_ready"])
            second = services.start(self.other, key())
            services.answer(self.other, second["id"], 0, 0, key())
            self.assertFalse(services.state(self.user)["bank_ready"])
        first_questions = TriviaRun.objects.get(pk=first["id"]).questions
        self.assertEqual(first_questions, TriviaRun.objects.get(pk=second["id"]).questions)
        self.assertEqual(QuestionUse.objects.count(), 6)
        with patch("domain.games.services.timezone.now", return_value=clock + timedelta(hours=48)):
            third = services.start(self.user, key())
        self.assertEqual(first_questions, TriviaRun.objects.get(pk=third["id"]).questions)
        self.assertEqual(QuestionUse.objects.count(), 9)

    def test_duplicate_text_across_difficulties_never_repeated_in_one_run(self):
        Question.objects.all().delete()
        for difficulty in (1, 2, 3):
            Question.objects.create(text="La misma pregunta", options=["A", "B", "C"], correct=0, difficulty=difficulty)
        run = services.start(self.user, key())
        self.assertEqual(run["total"], 1)
        self.assertEqual(QuestionUse.objects.count(), 1)

    def test_dashboard_reports_reusable_questions_after_cooldown(self):
        run = services.start(self.user, key())
        QuestionUse.objects.update(created_at=timezone.now() - timedelta(days=1, seconds=1))
        self.client.force_login(self.manager)
        response = self.client.get(reverse("games:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["question_count"], 9)
        self.assertContains(response, "24 horas")

    def test_server_timeout_rejects_late_correct_answer_and_is_idempotent(self):
        run = services.start(self.user, key())
        TriviaRun.objects.filter(pk=run["id"]).update(question_started_at=timezone.now() - timedelta(seconds=11))
        answer_key = key()
        result = services.answer(self.user, run["id"], 0, 1, answer_key)
        self.assertTrue(result["timed_out"])
        self.assertFalse(result["correct"])
        self.assertTrue(result["run"]["finished"])
        self.assertEqual(services.answer(self.user, run["id"], 0, 1, answer_key), result)
        self.assertEqual(GameAccount.objects.get(user=self.user).spins, 0)
        self.assertTrue(TriviaAnswer.objects.get().timed_out)

    def test_early_timeout_rejected_and_reload_does_not_reset_deadline(self):
        run = services.start(self.user, key())
        self.assertEqual(services.state(self.user)["run"]["deadline"], run["deadline"])
        with self.assertRaises(ValidationError): services.answer(self.user, run["id"], 0, None, key())
        TriviaRun.objects.filter(pk=run["id"]).update(question_started_at=timezone.now() - timedelta(seconds=11))
        self.assertIsNone(services.state(self.user)["run"])
        self.assertTrue(TriviaAnswer.objects.get().timed_out)
        self.assertEqual(GameEvent.objects.filter(kind="trivia_timed_out").count(), 1)
        services.state(self.user)
        self.assertEqual(TriviaAnswer.objects.count(), 1)

    def test_timer_configuration_permissions_and_run_snapshot(self):
        self.client.force_login(self.user)
        url = reverse("games:settings")
        self.assertEqual(self.client.post(url, {"question_seconds": 30}).status_code, 403)
        self.client.force_login(self.manager)
        self.assertEqual(self.client.post(url, {"question_seconds": 0}).status_code, 200)
        self.assertEqual(self.client.post(url, {"question_seconds": 30}).status_code, 302)
        run = services.start(self.user, key())
        self.assertEqual(run["question_seconds"], 30)
        self.client.post(url, {"question_seconds": 5})
        self.assertEqual(services.state(self.user)["run"]["question_seconds"], 30)
        self.assertEqual(GameEvent.objects.filter(kind="game_settings_saved").count(), 2)

    def test_extra_spin_slot_consumed_per_user_and_layout_redistributed(self):
        self.slot.product = None; self.slot.kind = "spin"; self.slot.count = 2; self.slot.save()
        WheelSlot.objects.create(kind="over", label="Game Over", count=2)
        self.credits()
        first_key = key()
        with patch("domain.games.services.secrets.randbelow", return_value=0):
            services.spin(self.user, first_key)
            self.assertEqual(len(services.wheel_layout(self.user)), 3)
            services.spin(self.user, first_key)
            self.assertEqual(len(services.wheel_layout(self.user)), 3)
            services.spin(self.user, key())
        layout = services.wheel_layout(self.user)
        self.assertEqual(len(layout), 2)
        self.assertTrue(all(s["kind"] == "over" for s in layout))
        self.assertEqual(len(services.wheel_layout(self.other)), 4)
        self.assertEqual(GameAccount.objects.get(user=self.user).spins, 1)

    def test_wrong_answer_stops_and_24_hour_cooldown(self):
        run = services.start(self.user, key())
        services.answer(self.user, run["id"], 0, 0, key())
        with self.assertRaises(ValidationError): services.answer(self.user, run["id"], 1, 1, key())
        with self.assertRaises(ValidationError): services.start(self.user, key())
        GameAccount.objects.filter(user=self.user).update(next_daily_at=timezone.now() - timedelta(seconds=1))
        self.assertNotEqual(services.start(self.user, key())["id"], run["id"])

    def test_idempotent_start_and_answer_and_ownership(self):
        start_key, answer_key = key(), key()
        run = services.start(self.user, start_key)
        self.assertEqual(run, services.start(self.user, start_key))
        alias_key = key()
        self.assertEqual(run, services.start(self.user, alias_key))
        with self.assertRaises(ValidationError): services.answer(self.other, run["id"], 0, 1, key())
        services.answer(self.user, run["id"], 0, 1, answer_key)
        services.answer(self.user, run["id"], 0, 1, answer_key)
        with self.assertRaises(ValidationError): services.answer(self.user, run["id"], 0, 0, answer_key)
        with self.assertRaises(ValidationError): services.answer(self.user, run["id"], 0, 1, key())
        self.assertEqual(GameAccount.objects.get(user=self.user).spins, 1)
        services.answer(self.user, run["id"], 1, 0, key())
        GameAccount.objects.filter(user=self.user).update(extra_attempts=1)
        self.assertEqual(services.start(self.user, alias_key)["id"], run["id"])
        self.assertEqual(GameAccount.objects.get(user=self.user).extra_attempts, 1)

    def test_question_snapshot_survives_edit_and_delete(self):
        run = services.start(self.user, key())
        Question.objects.all().delete()
        result = services.answer(self.user, run["id"], 0, 1, key())
        self.assertTrue(result["correct"])

    def test_empty_bank_does_not_consume_attempt(self):
        Question.objects.all().delete()
        with self.assertRaises(ValidationError): services.start(self.user, key())
        self.assertFalse(TriviaRun.objects.exists())
        self.assertFalse(GameAccount.objects.filter(user=self.user, next_daily_at__isnull=False).exists())

    def test_partial_bank_stops_at_first_missing_difficulty(self):
        Question.objects.filter(difficulty=2).delete()
        run = services.start(self.user, key())
        self.assertEqual(run["total"], 1)
        self.assertTrue(services.answer(self.user, run["id"], 0, 1, key())["run"]["finished"])

    def test_grants_permissions_reason_and_idempotency(self):
        grant_key = key()
        for actor in (self.user, self.operator):
            with self.assertRaises(PermissionDenied): services.grant(actor, self.user, 2, "Campaña", grant_key)
        with self.assertRaises(ValidationError): services.grant(self.manager, self.user, 2, "", grant_key)
        services.grant(self.manager, self.user, 2, "Campaña", grant_key)
        services.grant(self.manager, self.user, 2, "Campaña", grant_key)
        account = GameAccount.objects.get(user=self.user)
        self.assertEqual(account.extra_attempts, 2)
        event = GameEvent.objects.get(kind="attempts_granted")
        self.assertEqual(event.actor, self.manager)
        self.assertEqual(event.data["reason"], "Campaña")
        run = services.start(self.user, key())
        services.answer(self.user, run["id"], 0, 0, key())
        extra = services.start(self.user, key())
        self.assertEqual(TriviaRun.objects.get(pk=extra["id"]).source, "extra")
        self.assertEqual(extra["total"], 1)
        self.assertEqual(GameAccount.objects.get(user=self.user).extra_attempts, 1)

    def test_extra_trivia_has_one_question_and_at_most_one_spin(self):
        account = self.credits(spins=0, attempts=2)
        account.next_daily_at = timezone.now() + timedelta(hours=12)
        account.save(update_fields=["next_daily_at"])
        start_key = key()
        run = services.start(self.user, start_key)
        self.assertEqual(run["source"], "extra")
        self.assertEqual(run["total"], 1)
        self.assertEqual(len(TriviaRun.objects.get(pk=run["id"]).questions), 1)
        self.assertEqual(QuestionUse.objects.count(), 1)
        self.assertEqual(services.start(self.user, start_key), run)
        answer_key = key()
        result = services.answer(self.user, run["id"], 0, 1, answer_key)
        self.assertTrue(result["correct"])
        self.assertTrue(result["run"]["finished"])
        self.assertNotIn("question", result["run"])
        services.answer(self.user, run["id"], 0, 1, answer_key)
        with self.assertRaises(ValidationError): services.answer(self.user, run["id"], 1, 1, key())
        account.refresh_from_db()
        self.assertEqual(account.spins, 1)
        self.assertEqual(account.extra_attempts, 1)
        self.assertGreater(account.next_daily_at, timezone.now())
        second = services.start(self.user, key())
        self.assertEqual(second["total"], 1)
        self.assertNotEqual(run["question"]["text"], second["question"]["text"])
        self.assertTrue(services.answer(self.user, second["id"], 0, 0, key())["run"]["finished"])
        account.refresh_from_db()
        self.assertEqual(account.spins, 1)
        self.assertEqual(account.extra_attempts, 0)

    def test_daily_trivia_keeps_three_questions_even_with_extra_available(self):
        self.credits(spins=0, attempts=1)
        run = services.start(self.user, key())
        self.assertEqual(run["source"], "daily")
        self.assertEqual(run["total"], 3)
        self.assertEqual(GameAccount.objects.get(user=self.user).extra_attempts, 1)

    def test_extra_trivia_empty_bank_does_not_spend_opportunity(self):
        account = self.credits(spins=0, attempts=1)
        account.next_daily_at = timezone.now() + timedelta(hours=12)
        account.save(update_fields=["next_daily_at"])
        Question.objects.filter(difficulty=1).delete()
        with self.assertRaises(ValidationError): services.start(self.user, key())
        account.refresh_from_db()
        self.assertEqual(account.extra_attempts, 1)
        self.assertFalse(TriviaRun.objects.exists())

    def test_manual_spins_grant_is_authorized_audited_and_idempotent(self):
        self.credits(spins=1, attempts=2)
        grant_key = key()
        for actor in (self.user, self.operator):
            with self.assertRaises(PermissionDenied): services.grant(actor, self.user, 3, "Campaña", grant_key, reward="spin")
        services.grant(self.manager, self.user, 3, "Campaña", grant_key, reward="spin")
        services.grant(self.manager, self.user, 3, "Campaña", grant_key, reward="spin")
        account = GameAccount.objects.get(user=self.user)
        self.assertEqual(account.spins, 4)
        self.assertEqual(account.extra_attempts, 2)
        event = GameEvent.objects.get(kind="spins_granted")
        self.assertEqual(event.actor, self.manager)
        self.assertEqual(event.data, {"amount": 3, "reason": "Campaña"})
        with self.assertRaises(ValidationError): services.grant(self.manager, self.user, 3, "Campaña", grant_key, reward="attempt")
        with self.assertRaises(ValidationError): services.grant(self.manager, self.user, 4, "Campaña", grant_key, reward="spin")

    def test_admin_stepper_grants_spins_instead_of_trivia_attempts(self):
        url = reverse("games:user", args=[self.user.pk])
        self.client.force_login(self.operator)
        self.assertEqual(self.client.post(url, {"key": key(), "amount": 2, "reason": "Prueba"}).status_code, 403)
        self.client.force_login(self.manager)
        self.assertContains(self.client.get(url), "Otorgar tiradas o trivias adicionales manualmente")
        self.assertContains(self.client.get(url), "data-spin-stepper")
        for amount in (0, 101, -1, "1.5"):
            self.assertEqual(self.client.post(url, {"key": key(), "amount": amount, "reason": "Prueba"}).status_code, 200)
        self.assertEqual(GameAccount.objects.get(user=self.user).spins, 0)
        grant_key = key()
        payload = {"key": grant_key, "amount": 2, "reason": "Compensación"}
        self.assertEqual(self.client.post(url, payload).status_code, 302)
        self.assertEqual(self.client.post(url, payload).status_code, 302)
        account = GameAccount.objects.get(user=self.user)
        self.assertEqual(account.spins, 2)
        self.assertEqual(account.extra_attempts, 0)
        self.assertEqual(GameEvent.objects.filter(kind="spins_granted").count(), 1)

    def test_prize_spin_idempotency_stock_reserved_once_and_redeemed_once(self):
        self.credits()
        spin_key = key()
        result = services.spin(self.user, spin_key)
        self.assertEqual(result, services.spin(self.user, spin_key))
        coupon = PrizeCoupon.objects.get()
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 1)
        self.assertEqual(GameAccount.objects.get(user=self.user).spins, 0)
        self.assertFalse(CandyOrder.objects.exists())
        self.assertIsNone(coupon.pickup_order_id)
        order = services.request_pickup(self.user, [coupon.pk], key())
        with self.assertRaises(PermissionDenied): deliver_candy_order(order.qr_payload, self.user)
        deliver_candy_order(order.qr_payload, self.operator)
        coupon.refresh_from_db()
        self.assertEqual(coupon.status, "redeemed")
        with self.assertRaises(ValidationError): deliver_candy_order(order.pickup_code, self.operator)
        self.assertEqual(GameEvent.objects.filter(kind="coupon_redeemed").count(), 1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 1)

    def test_empty_wheel_out_of_stock_and_inactive_product_do_not_spend(self):
        self.credits()
        for field, value in (("stock", 0), ("is_active", False)):
            CandyProduct.objects.filter(pk=self.product.pk).update(**{field: value})
            with self.assertRaises(ValidationError): services.spin(self.user, key())
        self.assertEqual(GameAccount.objects.get(user=self.user).spins, 1)
        self.assertEqual(WheelSpin.objects.count(), 0)

    def test_bonus_results_and_no_spin_no_reward(self):
        with self.assertRaises(ValidationError): services.spin(self.user, key())
        GameAccount.objects.update_or_create(user=self.user, defaults={"spins": 1})
        self.slot.product = None
        for kind in ("spin", "attempt", "over"):
            GameAccount.objects.filter(user=self.user).update(spins=1)
            self.slot.kind = kind; self.slot.save()
            services.spin(self.user, key())
            account = GameAccount.objects.get(user=self.user)
            self.assertEqual(account.spins, 1 if kind == "spin" else 0)
        self.assertEqual(account.extra_attempts, 1)
        self.assertFalse(PrizeCoupon.objects.exists())

    def test_api_auth_csrf_tampering_and_admin_permissions(self):
        url = reverse("games:action", args=["start"])
        self.assertEqual(self.client.post(url).status_code, 302)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(self.client.post(url, "[]", content_type="application/json").status_code, 400)
        self.assertEqual(self.client.post(url, '{"key":"bad"}', content_type="application/json").status_code, 400)
        strict = Client(enforce_csrf_checks=True); strict.force_login(self.user)
        self.assertEqual(strict.post(url, '{}', content_type="application/json").status_code, 403)
        self.assertEqual(self.client.get(reverse("games:dashboard")).status_code, 403)
        self.assertEqual(self.client.get(reverse("games:export")).status_code, 403)
        self.credits()
        response = self.client.post(reverse("games:action", args=["spin"]), json.dumps({"key": str(key()), "index": 8000, "kind": "spin"}), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["spin"]["index"], 0)
        self.assertEqual(response.json()["spin"]["kind"], "prize")

    def test_manager_pages_import_export_and_atomic_validation(self):
        self.client.force_login(self.manager)
        for tab in ("questions", "wheel", "users", "events", "runs", "spins", "coupons"):
            self.assertEqual(self.client.get(reverse("games:dashboard"), {"tab": tab}).status_code, 200)
        exported = self.client.get(reverse("games:export")).json()
        count = Question.objects.count()
        payload = {"questions": [exported["questions"][0], {"text": "bad"}]}
        response = self.client.post(reverse("games:import"), {"payload": json.dumps(payload)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Question.objects.count(), count)
        self.assertEqual(self.client.post(reverse("games:import"), {"payload": json.dumps(exported)}).status_code, 302)
        self.assertEqual(Question.objects.count(), count * 2)
        self.assertEqual(self.client.get(reverse("games:user", args=[self.user.pk])).status_code, 200)

    def test_crud_slot_validation_limit_and_archive(self):
        self.client.force_login(self.manager)
        create = reverse("games:create", args=["slot"])
        response = self.client.post(create, {"kind": "prize", "label": "Invalid", "count": 1, "position": 0, "active": "on"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(WheelSlot.objects.count(), 1)
        response = self.client.post(create, {"kind": "over", "label": "Too many", "count": 24, "position": 0, "active": "on"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(WheelSlot.objects.count(), 1)
        self.credits(); services.spin(self.user, key())
        self.client.post(reverse("games:delete", args=["slot", self.slot.pk]))
        self.slot.refresh_from_db()
        self.assertFalse(self.slot.active)
        self.assertEqual(PrizeCoupon.objects.count(), 1)

    def test_existing_candy_scanner_delivers_reward_order_once(self):
        self.credits(); services.spin(self.user, key())
        coupon = PrizeCoupon.objects.get()
        order = services.request_pickup(self.user, [coupon.pk], key())
        self.client.force_login(self.operator)
        url = reverse("manager:entregar_candy")
        self.assertContains(self.client.get(url), 'data-qr-prefix="BCC:"')
        self.assertContains(self.client.post(url, {"code": order.pickup_code, "action": "preview"}), "Premio test")
        self.assertEqual(self.client.post(url, {"code": order.qr_payload, "action": "deliver"}).status_code, 302)
        self.assertContains(self.client.post(url, {"code": order.qr_payload, "action": "deliver"}), "ya fue entregado")

    def test_client_coupons_are_private(self):
        self.credits(); services.spin(self.user, key())
        coupon = PrizeCoupon.objects.get()
        self.client.force_login(self.other)
        order = services.request_pickup(self.user, [coupon.pk], key())
        response = self.client.get(reverse("games:coupons"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, order.pickup_code)
        self.assertEqual(self.client.get(reverse("games:pickup_detail", args=[order.pk])).status_code, 404)
        self.client.force_login(self.user)
        self.assertContains(self.client.get(reverse("games:pickup_detail", args=[order.pk])), order.qr_payload)

    def test_pickup_orders_prioritize_ready_orders_and_highlight_only_their_qrs(self):
        delivered = CandyOrder.objects.create(reward_user=self.user, reward_key=key(), total=0, delivered_at=timezone.now())
        ready = CandyOrder.objects.create(reward_user=self.user, reward_key=key(), total=0)
        CandyOrder.objects.filter(pk=ready.pk).update(created_at=timezone.now() - timedelta(days=2))
        other = CandyOrder.objects.create(reward_user=self.other, reward_key=key(), total=0)
        self.client.force_login(self.user)
        response = self.client.get(reverse("candy_store"))
        self.assertEqual([order.pk for order in response.context["orders"]], [ready.pk, delivered.pk])
        self.assertContains(response, 'class="ticket-qr-link is-imminent-ticket"', count=1)
        self.assertContains(response, 'class="ticket-history-link"', count=1)
        self.assertNotContains(response, reverse("candy_order_detail", args=[other.pk]))

    def test_prizes_empty_state_and_shared_modal_preserve_coupons_and_orders(self):
        self.client.force_login(self.user)
        url = reverse("games:coupons")
        response = self.client.get(url)
        self.assertContains(response, 'class="prizes-empty"')
        self.assertContains(response, 'class="prizes-empty-icon"')
        self.assertContains(response, 'data-open-games')
        self.assertContains(response, 'id="games-dialog"')
        self.assertNotContains(response, "Mis pedidos de retiro")
        self.assertEqual(response.context["game_initial"]["spins"], 0)
        GameAccount.objects.filter(user=self.user).update(spins=1)
        services.spin(self.user, key())
        response = self.client.get(url)
        self.assertNotContains(response, 'class="prizes-empty"')
        self.assertContains(response, 'id="prize-pickup-form"')
        self.assertContains(response, "Premio test")
        self.assertFalse(CandyOrder.objects.exists())
        coupon = PrizeCoupon.objects.get(user=self.user)
        order = services.request_pickup(self.user, [coupon.pk], key())
        response = self.client.get(url)
        self.assertNotContains(response, 'class="prizes-empty"')
        self.assertNotContains(response, 'id="prize-pickup-form"')
        self.assertContains(response, reverse("candy_store") + "#mis-retiros")
        self.assertNotContains(response, "data-candy-order")
        self.assertContains(response, 'id="games-dialog"')

    def test_home_has_permanent_launcher_and_modal_without_separate_game_page(self):
        self.assertContains(self.client.get(reverse("home")), 'id="games-launcher"')
        self.assertContains(self.client.get(reverse("home")), '<dialog id="games-dialog"')
        self.assertRedirects(self.client.get(reverse("games:home")), '/?juegos=1', fetch_redirect_response=False)
        self.client.force_login(self.user)
        self.credits(spins=2)
        self.assertEqual(self.client.get(reverse("games:state")).json()["spins"], 2)
        self.assertContains(self.client.get(reverse("listing")), 'id="game-initial"')

    def test_selected_coupons_create_one_candy_order_only_on_request(self):
        self.credits(spins=2)
        services.spin(self.user, key()); services.spin(self.user, key())
        coupons = list(PrizeCoupon.objects.all())
        self.assertFalse(CandyOrder.objects.exists())
        pickup_key = key()
        ids = [c.pk for c in coupons]
        with self.assertRaises(ValidationError): services.request_pickup(self.other, ids, key())
        order = services.request_pickup(self.user, ids, pickup_key)
        self.assertEqual(order.pk, services.request_pickup(self.user, ids, pickup_key).pk)
        with self.assertRaises(ValidationError): services.request_pickup(self.user, ids, key())
        with self.assertRaises(ValidationError): services.request_pickup(self.user, ids[:1], pickup_key)
        self.assertEqual(order.item_count, 2)
        self.assertEqual(order.total, 0)
        self.assertTrue(order.qr_payload.startswith("BCC:"))
        self.product.refresh_from_db(); self.assertEqual(self.product.stock, 0)
        self.assertEqual(PrizeCoupon.objects.filter(status="requested").count(), 2)
        _, pickup = deliver_candy_order(order.qr_payload, self.operator)
        self.assertEqual(PrizeCoupon.objects.filter(status="redeemed").count(), 2)
        undo_candy_pickup(pickup.pk, self.operator)
        self.assertEqual(PrizeCoupon.objects.filter(status="requested").count(), 2)
        deliver_candy_order(order.qr_payload, self.operator)
        self.product.refresh_from_db(); self.assertEqual(self.product.stock, 0)

    def test_pickup_endpoint_ownership_csrf_and_duplicate_selection(self):
        self.credits(); services.spin(self.user, key())
        coupon = PrizeCoupon.objects.get()
        self.client.force_login(self.other)
        url = reverse("games:pickup")
        self.client.post(url, {"key": key(), "coupons": [coupon.pk]})
        self.assertFalse(CandyOrder.objects.exists())
        self.client.force_login(self.user)
        self.client.post(url, {"key": key(), "coupons": [coupon.pk, coupon.pk]})
        self.assertFalse(CandyOrder.objects.exists())
        strict = Client(enforce_csrf_checks=True); strict.force_login(self.user)
        self.assertEqual(strict.post(url, {"key": key(), "coupons": [coupon.pk]}).status_code, 403)
        response = self.client.post(url, {"key": key(), "coupons": [coupon.pk]})
        self.assertRedirects(response, reverse("candy_store") + "#mis-retiros", fetch_redirect_response=False)
        self.assertEqual(CandyOrder.objects.count(), 1)


class ConcurrentGameTests(TransactionTestCase):
    """Exercise real independent connections; busy SQLite requests must retry.

    PostgreSQL runs these same tests in the existing CI service with row locks.
    """
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="concurrent")
        self.operator = get_user_model().objects.create_user(username="operator")
        Operator.objects.create(user=self.operator)
        self.product = CandyProduct.objects.create(name="Last prize", price=1, stock=1)
        WheelSlot.objects.all().delete()
        self.slot = WheelSlot.objects.create(kind="prize", label="Last prize", product=self.product)
        GameAccount.objects.create(user=self.user, spins=1)
        Question.objects.all().delete()
        Question.objects.create(text="Question", options=["A", "B", "C"], correct=0, difficulty=1)

    def parallel(self, fn):
        def worker(index):
            close_old_connections()
            try:
                return fn(index)
            except (ValidationError, OperationalError):
                return None
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as executor:
            return list(executor.map(worker, range(2)))

    def test_simultaneous_spins_cannot_double_spend(self):
        keys = [key(), key()]
        self.parallel(lambda i: services.spin(get_user_model().objects.get(pk=self.user.pk), keys[i]))
        # SQLite can reject both lock upgrades. Retrying does not bypass balances.
        if not WheelSpin.objects.exists(): services.spin(self.user, keys[0])
        self.assertEqual(WheelSpin.objects.count(), 1)
        self.assertEqual(PrizeCoupon.objects.count(), 1)
        self.assertEqual(GameAccount.objects.get(user=self.user).spins, 0)
        self.assertEqual(CandyProduct.objects.get(pk=self.product.pk).stock, 0)

    def test_last_stock_two_users(self):
        other = get_user_model().objects.create_user(username="second")
        GameAccount.objects.create(user=other, spins=1)
        users = [self.user.pk, other.pk]
        self.parallel(lambda i: services.spin(get_user_model().objects.get(pk=users[i]), key()))
        if not WheelSpin.objects.exists(): services.spin(self.user, key())
        self.assertEqual(PrizeCoupon.objects.count(), 1)
        self.assertEqual(CandyProduct.objects.get(pk=self.product.pk).stock, 0)
        self.assertEqual(sum(GameAccount.objects.values_list("spins", flat=True)), 1)

    def test_simultaneous_answers_and_starts(self):
        self.parallel(lambda i: services.start(get_user_model().objects.get(pk=self.user.pk), key()))
        run = TriviaRun.objects.filter(user=self.user).first()
        if not run: run = TriviaRun.objects.get(pk=services.start(self.user, key())["id"])
        self.assertEqual(TriviaRun.objects.count(), 1)
        before = GameAccount.objects.get(user=self.user).spins
        self.parallel(lambda i: services.answer(get_user_model().objects.get(pk=self.user.pk), run.pk, 0, 0, key()))
        if not TriviaAnswer.objects.exists(): services.answer(self.user, run.pk, 0, 0, key())
        self.assertEqual(TriviaAnswer.objects.count(), 1)
        self.assertEqual(GameAccount.objects.get(user=self.user).spins, before + 1)

    def test_simultaneous_redemptions_have_one_audit_event(self):
        services.spin(self.user, key())
        coupon = PrizeCoupon.objects.get()
        order = services.request_pickup(self.user, [coupon.pk], key())
        self.parallel(lambda i: deliver_candy_order(order.qr_payload, get_user_model().objects.get(pk=self.operator.pk)))
        if not GameEvent.objects.filter(kind="coupon_redeemed").exists(): deliver_candy_order(order.qr_payload, self.operator)
        self.assertEqual(GameEvent.objects.filter(kind="coupon_redeemed").count(), 1)
        coupon.refresh_from_db()
        self.assertEqual(coupon.status, "redeemed")

    def test_simultaneous_pickups_cannot_reuse_coupons(self):
        services.spin(self.user, key())
        coupon = PrizeCoupon.objects.get()
        self.parallel(lambda i: services.request_pickup(get_user_model().objects.get(pk=self.user.pk), [coupon.pk], key()))
        if not CandyOrder.objects.exists(): services.request_pickup(self.user, [coupon.pk], key())
        self.assertEqual(CandyOrder.objects.count(), 1)
        coupon.refresh_from_db()
        self.assertEqual(coupon.status, "requested")

    def test_two_users_cannot_receive_the_same_question(self):
        other = get_user_model().objects.create_user(username="other-trivia-player")
        GameAccount.objects.create(user=other)
        ids = [self.user.pk, other.pk]
        self.parallel(lambda i: services.start(get_user_model().objects.get(pk=ids[i]), key()))
        if not TriviaRun.objects.exists(): services.start(self.user, key())
        self.assertEqual(TriviaRun.objects.count(), 1)
        self.assertEqual(QuestionUse.objects.count(), 1)
        self.assertEqual(GameAccount.objects.filter(next_daily_at__isnull=False).count(), 1)


class StarterConfigTests(TestCase):
    def test_no_other_trivia_slot_active_by_default(self):
        self.assertFalse(WheelSlot.objects.filter(active=True, kind="attempt").exists())
        self.assertEqual(WheelConfig.objects.get(pk=1).question_seconds, 10)


class QuestionCooldownMigrationTests(TransactionTestCase):
    def tearDown(self):
        MigrationExecutor(connection).migrate([("games", "0007_alter_questionuse_fingerprint_and_more")])
        super().tearDown()

    def test_existing_assignments_keep_actual_timestamps_and_latest_use(self):
        previous = ("games", "0006_expand_starter_bank")
        executor = MigrationExecutor(connection)
        executor.migrate([previous])
        apps = executor.loader.project_state([previous]).apps
        user = get_user_model().objects.create_user(username="legacy-player")
        question = apps.get_model("games", "Question").objects.create(
            text="Legacy question", options=["A", "B", "C"], correct=0, difficulty=1)
        Run = apps.get_model("games", "TriviaRun")
        Use = apps.get_model("games", "QuestionUse")
        now = timezone.now()
        snapshot = [{"id": question.pk, "text": question.text, "options": question.options, "correct": 0, "difficulty": 1}]
        old_run = Run.objects.create(user_id=user.pk, questions=snapshot, source="daily", finished_at=now)
        recent_run = Run.objects.create(user_id=user.pk, questions=snapshot, source="extra", finished_at=now)
        Run.objects.filter(pk=old_run.pk).update(created_at=now - timedelta(days=2))
        Run.objects.filter(pk=recent_run.pk).update(created_at=now - timedelta(hours=1))
        Use.objects.create(question=question, run=old_run, fingerprint=services.question_fingerprint(question.text))
        MigrationExecutor(connection).migrate([("games", "0007_alter_questionuse_fingerprint_and_more")])
        self.assertEqual(QuestionUse.objects.filter(question_id=question.pk).count(), 2)
        self.assertEqual(QuestionUse.objects.get(run_id=recent_run.pk).created_at, now - timedelta(hours=1))
        self.assertNotIn(question.pk, [q["id"] for q in services.new_questions(1)])
        with patch("domain.games.services.timezone.now", return_value=now + timedelta(hours=23)):
            self.assertIn(question.pk, [q["id"] for q in services.new_questions(1)])
