import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


class GameAccount(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="games")
    extra_attempts = models.PositiveIntegerField(default=0)
    spins = models.PositiveIntegerField(default=0)
    next_daily_at = models.DateTimeField(null=True, blank=True)
    revision = models.PositiveBigIntegerField(default=0)


class Question(models.Model):
    class Difficulty(models.IntegerChoices):
        EASY = 1, "Fácil"
        MEDIUM = 2, "Media"
        HARD = 3, "Difícil"

    text = models.CharField("Pregunta", max_length=500)
    options = models.JSONField("Tres respuestas")
    correct = models.PositiveSmallIntegerField("Índice correcto (0, 1 o 2)", validators=[MaxValueValidator(2)])
    difficulty = models.PositiveSmallIntegerField("Dificultad", choices=Difficulty.choices)
    active = models.BooleanField("Activa", default=True)

    def clean(self):
        if (not isinstance(self.options, list) or len(self.options) != 3
                or any(not isinstance(x, str) or not x.strip() or len(x) > 250 for x in self.options)
                or len(set(self.options)) != 3):
            raise ValidationError({"options": "Ingresá tres textos distintos, de hasta 250 caracteres."})

    def __str__(self):
        return self.text


class WheelConfig(models.Model):
    # Single serialization point for wheel configuration and prize inventory allocation.
    revision = models.PositiveBigIntegerField(default=0)
    question_seconds = models.PositiveSmallIntegerField("Segundos por pregunta", default=10, validators=[MinValueValidator(1), MaxValueValidator(300)])


class WheelSlot(models.Model):
    class Kind(models.TextChoices):
        OVER = "over", "Game Over"
        SPIN = "spin", "Una tirada más"
        ATTEMPT = "attempt", "Otra oportunidad de trivia"
        PRIZE = "prize", "Premio Candy"

    kind = models.CharField("Resultado", max_length=10, choices=Kind.choices)
    label = models.CharField("Nombre visible", max_length=80)
    count = models.PositiveSmallIntegerField("Cantidad de casillas", default=1, validators=[MinValueValidator(1), MaxValueValidator(24)])
    position = models.PositiveSmallIntegerField("Orden", default=0)
    product = models.ForeignKey("candy.CandyProduct", verbose_name="Producto", null=True, blank=True, on_delete=models.PROTECT)
    active = models.BooleanField("Activa", default=True)

    class Meta:
        ordering = ["position", "pk"]

    def clean(self):
        if (self.kind == self.Kind.PRIZE) != bool(self.product_id):
            raise ValidationError("Solo las casillas de premio requieren un producto de Candy.")

    def __str__(self):
        return self.label


class TriviaRun(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    key = models.UUIDField(default=uuid.uuid4)
    questions = models.JSONField()  # Immutable private snapshot, never serialized to clients.
    step = models.PositiveSmallIntegerField(default=0)
    source = models.CharField(max_length=10)
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True)
    question_started_at = models.DateTimeField(default=timezone.now)
    question_seconds = models.PositiveSmallIntegerField(default=10)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "key"], name="game_start_idempotency"),
            models.UniqueConstraint(fields=["user"], condition=models.Q(finished_at__isnull=True), name="game_one_active_run"),
        ]
        ordering = ["-pk"]


class TriviaAnswer(models.Model):
    run = models.ForeignKey(TriviaRun, on_delete=models.CASCADE, related_name="answers")
    key = models.UUIDField()
    step = models.PositiveSmallIntegerField()
    choice = models.PositiveSmallIntegerField(null=True)
    correct = models.BooleanField()
    timed_out = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["run", "step"], name="game_one_answer_per_step"),
                       models.UniqueConstraint(fields=["run", "key"], name="game_answer_idempotency")]


class QuestionUse(models.Model):
    """Assignment history used to enforce a rolling global 24-hour cooldown."""
    question = models.ForeignKey(Question, null=True, on_delete=models.SET_NULL, related_name="allocations")
    fingerprint = models.CharField(max_length=64)
    run = models.ForeignKey(TriviaRun, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["created_at", "fingerprint"], name="game_question_cooldown_idx")]
        constraints = [models.UniqueConstraint(fields=["run", "fingerprint"], name="game_no_repeat_in_run")]


class WheelSpin(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    key = models.UUIDField()
    slot = models.ForeignKey(WheelSlot, on_delete=models.PROTECT)
    label = models.CharField(max_length=80)
    kind = models.CharField(max_length=10)
    layout = models.JSONField()
    index = models.PositiveSmallIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-pk"]
        constraints = [models.UniqueConstraint(fields=["user", "key"], name="game_spin_idempotency")]


class PrizeCoupon(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = "available", "Disponible"
        REQUESTED = "requested", "En pedido de retiro"
        REDEEMED = "redeemed", "Canjeado"

    spin = models.OneToOneField(WheelSpin, on_delete=models.PROTECT, related_name="coupon")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    product = models.ForeignKey("candy.CandyProduct", on_delete=models.PROTECT)
    label = models.CharField(max_length=100)
    pickup_order = models.ForeignKey("candy.CandyOrder", null=True, blank=True, on_delete=models.PROTECT, related_name="prize_coupons")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.AVAILABLE)
    created_at = models.DateTimeField(auto_now_add=True)
    redeemed_at = models.DateTimeField(null=True)
    redeemed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="redeemed_game_coupons")

    class Meta:
        ordering = ["-pk"]

class GameEvent(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="game_events")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="game_actions")
    kind = models.CharField(max_length=40)
    data = models.JSONField(default=dict)
    key = models.UUIDField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-pk"]
        constraints = [models.UniqueConstraint(fields=["user", "kind", "key"], name="game_event_idempotency")]
