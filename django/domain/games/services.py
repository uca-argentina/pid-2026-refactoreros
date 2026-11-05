"""Game mutations serialize on an account write, including on SQLite.

Lock order: account -> wheel configuration -> Candy products. All rewards and
their audit events commit together. Caller-provided UUIDs make retries safe.
"""
import secrets
import uuid
import hashlib
import unicodedata
from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Count, F
from django.utils import timezone

from domain.candy.models import CandyOrder, CandyProduct
from domain.users.roles import staff_role
from .models import GameAccount, GameEvent, PrizeCoupon, Question, QuestionUse, TriviaAnswer, TriviaRun, WheelConfig, WheelSlot, WheelSpin


def request_key(value):
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        raise ValidationError("La clave de la operación debe ser un UUID válido.")


def lock_account(user):
    if not user.is_authenticated or not user.is_active:
        raise PermissionDenied
    account, _ = GameAccount.objects.get_or_create(user=user)
    GameAccount.objects.filter(pk=account.pk).update(revision=F("revision") + 1)
    return GameAccount.objects.get(pk=account.pk)


def lock_wheel():
    config, _ = WheelConfig.objects.get_or_create(pk=1)
    WheelConfig.objects.filter(pk=config.pk).update(revision=F("revision") + 1)


def audit(user, kind, data=None, actor=None, key=None):
    return GameEvent.objects.create(user=user, actor=actor or user, kind=kind, data=data or {}, key=key)


def require_manager(actor):
    if staff_role(actor) != "manager":
        raise PermissionDenied


def public_run(run):
    result = {"id": run.pk, "step": run.step, "total": len(run.questions), "finished": bool(run.finished_at), "source": run.source}
    if not run.finished_at:
        q = run.questions[run.step]
        result["question"] = {k: q[k] for k in ("text", "options", "difficulty")}
        result["deadline"] = (run.question_started_at + timedelta(seconds=run.question_seconds)).isoformat()
        result["question_seconds"] = run.question_seconds
    return result


def question_fingerprint(text):
    normalized = " ".join(unicodedata.normalize("NFKC", text).casefold().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def new_questions(difficulty):
    recent = QuestionUse.objects.filter(created_at__gt=timezone.now() - timedelta(hours=24))
    used = set(recent.values_list("fingerprint", flat=True))
    return [q for q in Question.objects.filter(active=True, difficulty=difficulty).exclude(pk__in=recent.values("question_id")).values(
        "id", "text", "options", "correct", "difficulty") if question_fingerprint(q["text"]) not in used]


def expire_run(run):
    if not run.finished_at and timezone.now() >= run.question_started_at + timedelta(seconds=run.question_seconds):
        TriviaAnswer.objects.create(run=run, key=uuid.uuid5(run.key, f"timeout:{run.step}"),
                                    step=run.step, choice=None, correct=False, timed_out=True)
        run.finished_at = timezone.now()
        run.save(update_fields=["finished_at"])
        audit(run.user, "trivia_timed_out", {"run": run.pk, "step": run.step})
        return True
    return False


@transaction.atomic
def state(user):
    account = lock_account(user)
    run = TriviaRun.objects.filter(user=user, finished_at__isnull=True).first()
    if run and expire_run(run):
        run = None
    bank_ready = bool(new_questions(1))
    daily_ready = account.next_daily_at is None or account.next_daily_at <= timezone.now()
    return {"spins": account.spins, "extra_attempts": account.extra_attempts,
            "daily_ready": daily_ready, "bank_ready": bank_ready,
            "can_start": bank_ready and (daily_ready or account.extra_attempts > 0),
            "next_daily_at": account.next_daily_at.isoformat() if account.next_daily_at else None,
            "run": public_run(run) if run else None,
            "server_now": timezone.now().isoformat(), "layout": wheel_layout(user)}


@transaction.atomic
def start(user, key):
    key = request_key(key)
    account = lock_account(user)
    previous = TriviaRun.objects.filter(user=user, key=key).first()
    if previous:
        return public_run(previous)
    alias = GameEvent.objects.filter(user=user, kind="start_reused", key=key).first()
    if alias:
        return public_run(TriviaRun.objects.get(pk=alias.data["run"], user=user))
    active = TriviaRun.objects.filter(user=user, finished_at__isnull=True).first()
    if active and expire_run(active):
        active = None
    if active:
        audit(user, "start_reused", {"run": active.pk}, key=key)
        return public_run(active)
    now = timezone.now()
    daily = account.next_daily_at is None or account.next_daily_at <= now
    if not daily and account.extra_attempts == 0:
        raise ValidationError("Tu próxima oportunidad todavía no está disponible.")
    lock_wheel()  # Serializes global allocation across different users.
    config = WheelConfig.objects.get(pk=1)
    questions = []
    levels = Question.Difficulty.values if daily else [Question.Difficulty.EASY]
    for difficulty in levels:
        assigned = {question_fingerprint(q["text"]) for q in questions}
        candidates = [q for q in new_questions(difficulty) if question_fingerprint(q["text"]) not in assigned]
        if not candidates:
            break
        questions.append(secrets.choice(candidates))
    if not questions:
        raise ValidationError("No hay preguntas disponibles en este momento. Conservás tu oportunidad; volvé más tarde.")
    if daily:
        account.next_daily_at = now + timedelta(hours=24)
    else:
        account.extra_attempts -= 1
    account.save(update_fields=["next_daily_at", "extra_attempts"])
    run = TriviaRun.objects.create(user=user, key=key, questions=questions, source="daily" if daily else "extra", question_seconds=config.question_seconds)
    QuestionUse.objects.bulk_create([QuestionUse(question_id=q["id"], fingerprint=question_fingerprint(q["text"]), run=run) for q in questions])
    audit(user, "trivia_started", {"run": run.pk, "source": run.source})
    return public_run(run)


@transaction.atomic
def answer(user, run_id, step, choice, key):
    key = request_key(key)
    account = lock_account(user)
    run = TriviaRun.objects.filter(pk=run_id, user=user).first()
    if run is None:
        raise ValidationError("No encontramos esa partida.")
    if type(step) is not int or (choice is not None and (type(choice) is not int or choice not in (0, 1, 2))):
        raise ValidationError("La respuesta no es válida.")
    previous = run.answers.filter(key=key).first()
    if previous:
        if previous.step != step or (not previous.timed_out and previous.choice != choice):
            raise ValidationError("La clave ya fue usada con otra respuesta.")
        return {"correct": previous.correct, "timed_out": previous.timed_out, "run": public_run(run)}
    timeout = run.answers.filter(step=step, timed_out=True).first()
    if timeout:
        return {"correct": False, "timed_out": True, "run": public_run(run)}
    if run.finished_at or step != run.step:
        raise ValidationError("Esta pregunta ya fue respondida o la partida terminó.")
    timed_out = timezone.now() >= run.question_started_at + timedelta(seconds=run.question_seconds)
    if choice is None and not timed_out:
        raise ValidationError("El tiempo de la pregunta todavía no terminó.")
    correct = not timed_out and run.questions[step]["correct"] == choice
    TriviaAnswer.objects.create(run=run, key=key, step=step, choice=None if timed_out else choice, correct=correct, timed_out=timed_out)
    if correct:
        account.spins += 1
        account.save(update_fields=["spins"])
        run.step += 1
        run.question_started_at = timezone.now()
    if not correct or run.step == len(run.questions):
        run.finished_at = timezone.now()
    run.save(update_fields=["step", "finished_at", "question_started_at"])
    audit(user, "trivia_answered", {"run": run.pk, "step": step, "choice": None if timed_out else choice, "correct": correct, "timed_out": timed_out, "spins_awarded": int(correct)})
    return {"correct": correct, "timed_out": timed_out, "run": public_run(run)}


def consumed_slots(user):
    if user is None or not user.is_authenticated:
        return {}
    return dict(WheelSpin.objects.filter(user=user, kind="spin").values("slot_id").annotate(n=Count("pk")).values_list("slot_id", "n"))


def slot_count(slot, consumed):
    return max(0, slot.count - consumed.get(slot.pk, 0)) if slot.kind == "spin" else slot.count


def wheel_layout(user=None):
    consumed = consumed_slots(user)
    return [{"id": slot.pk, "label": slot.label, "kind": slot.kind}
            for slot in WheelSlot.objects.filter(active=True).select_related("product")
            if slot.kind != "prize" or (slot.product.is_active and slot.product.stock > 0)
            for _ in range(slot_count(slot, consumed))]


def public_spin(spin):
    result = {"id": spin.pk, "index": spin.index, "layout": spin.layout, "label": spin.label, "kind": spin.kind}
    if hasattr(spin, "coupon"):
        coupon = spin.coupon
        if coupon.status == "available":
            result["coupon"] = {"id": coupon.pk, "label": coupon.label}
    return result


@transaction.atomic
def spin(user, key):
    key = request_key(key)
    account = lock_account(user)
    previous = WheelSpin.objects.filter(user=user, key=key).first()
    if previous:
        return public_spin(previous)
    if account.spins < 1:
        raise ValidationError("Necesitás una tirada para jugar.")
    lock_wheel()
    slots = list(WheelSlot.objects.filter(active=True).select_related("product"))
    # Exhausted prizes are removed before drawing, never substituted after drawing.
    products = {p.pk: p for p in CandyProduct.objects.select_for_update().filter(
        pk__in=[s.product_id for s in slots if s.product_id]).order_by("pk")}
    slots = [s for s in slots if s.kind != "prize" or (
        s.product_id in products and products[s.product_id].is_active and products[s.product_id].stock > 0)]
    consumed = consumed_slots(user)
    expanded = [s for s in slots for _ in range(slot_count(s, consumed))]
    if not expanded:
        raise ValidationError("La ruleta no tiene casillas disponibles. Conservás tu tirada.")
    layout = [{"id": s.pk, "label": s.label, "kind": s.kind} for s in expanded]
    index = secrets.randbelow(len(expanded))
    slot = expanded[index]
    account.spins -= 1
    if slot.kind == "spin":
        account.spins += 1
    elif slot.kind == "attempt":
        account.extra_attempts += 1
    account.save(update_fields=["spins", "extra_attempts"])
    result = WheelSpin.objects.create(user=user, key=key, slot=slot, label=slot.label, kind=slot.kind, layout=layout, index=index)
    if slot.kind == "prize":
        product = products[slot.product_id]
        # Conditional update also prevents overselling on engines without row locks.
        if not CandyProduct.objects.filter(pk=product.pk, stock__gt=0, is_active=True).update(stock=F("stock") - 1):
            raise ValidationError("El premio ya no está disponible. Conservás tu tirada.")
        PrizeCoupon.objects.create(spin=result, user=user, product=product, label=product.name)
    audit(user, "wheel_spun", {"spin": result.pk, "kind": slot.kind, "slot": slot.pk, "index": index})
    return public_spin(result)


@transaction.atomic
def grant(actor, user, amount, reason, key, *, reward="attempt"):
    require_manager(actor)
    key = request_key(key)
    if reward not in {"attempt", "spin"}:
        raise ValidationError("El tipo de recompensa no es válido.")
    if type(amount) is not int or not 1 <= amount <= 100 or not isinstance(reason, str) or not reason.strip() or len(reason) > 500:
        raise ValidationError("Ingresá una cantidad entre 1 y 100 y un motivo de hasta 500 caracteres.")
    kind = "spins_granted" if reward == "spin" else "attempts_granted"
    account = lock_account(user)
    previous = GameEvent.objects.filter(user=user, kind__in=["attempts_granted", "spins_granted"], key=key).first()
    if previous:
        if previous.kind != kind or previous.data != {"amount": amount, "reason": reason.strip()} or previous.actor_id != actor.pk:
            raise ValidationError("La clave ya fue usada para otro otorgamiento.")
        return
    field = "spins" if reward == "spin" else "extra_attempts"
    setattr(account, field, getattr(account, field) + amount)
    account.save(update_fields=[field])
    audit(user, kind, {"amount": amount, "reason": reason.strip()}, actor, key)


@transaction.atomic
def request_pickup(user, coupon_ids, key):
    key = request_key(key)
    lock_account(user)
    if (not isinstance(coupon_ids, list) or not 1 <= len(coupon_ids) <= 100
            or any(type(pk) is not int or pk < 1 for pk in coupon_ids) or len(set(coupon_ids)) != len(coupon_ids)):
        raise ValidationError("Seleccioná entre 1 y 100 cupones diferentes.")
    previous = CandyOrder.objects.filter(reward_user=user, reward_key=key).first()
    if previous:
        if set(previous.prize_coupons.values_list("pk", flat=True)) != set(coupon_ids):
            raise ValidationError("La clave ya fue usada para otra selección.")
        return previous
    coupons = list(PrizeCoupon.objects.select_for_update().filter(pk__in=coupon_ids, user=user).order_by("pk"))
    if len(coupons) != len(coupon_ids) or any(c.status != "available" or c.pickup_order_id for c in coupons):
        raise ValidationError("Algún cupón no está disponible o ya pertenece a un pedido de retiro.")
    # Stock was reserved when winning. Reuse Candy's order and credential lifecycle,
    # without charging or decrementing stock again.
    items = [{"kind": "product", "id": c.product_id, "name": c.label, "quantity": 1,
              "unit_price": "0.00", "subtotal": "0.00",
              "components": [{"product_id": c.product_id, "name": c.label, "quantity": 1}]} for c in coupons]
    order = CandyOrder.objects.create(reward_user=user, reward_key=key, items=items, total=0)
    PrizeCoupon.objects.filter(pk__in=coupon_ids).update(status="requested", pickup_order=order)
    audit(user, "pickup_requested", {"order": order.pk, "coupons": coupon_ids}, key=key)
    return order
