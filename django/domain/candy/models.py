from collections import Counter
from decimal import Decimal
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import IntegrityError, models, transaction
from django.db.models.functions import Cast
from django.utils import timezone

from domain.screenings.models import Screening
from domain.cinema.models import CinemaSettings
from domain.tickets.models import (
    UndoWindowMixin,
    generate_ticket_token,
    reservation_code_digest,
    reservation_code_for_token,
)

CANDY_QR_PREFIX = "BCC:"
LOW_STOCK_THRESHOLD = 10
INVALID_SELECTION_MESSAGE = "La selección de candy no es válida."
UNAVAILABLE_ITEM_MESSAGE = "Algún producto de candy ya no está a la venta. Revisá tu selección."


class CandyProduct(models.Model):
    class Category(models.TextChoices):
        POPCORN = "pochoclos", "Pochoclos"
        SNACKS = "snacks", "Snacks"
        SWEETS = "golosinas", "Golosinas"
        DRINKS = "bebidas", "Bebidas"

    CATEGORY_ICONS = {
        Category.POPCORN: "popcorn",
        Category.DRINKS: "cup-soda",
        Category.SNACKS: "sandwich",
        Category.SWEETS: "candy",
    }

    name = models.CharField(max_length=100, unique=True, db_column="nombre")
    category = models.CharField(
        max_length=20,
        choices=Category.choices,
        default=Category.POPCORN,
        db_column="categoria",
    )
    price = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        db_column="precio",
    )
    stock = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True, db_column="activo")
    image = models.ImageField(upload_to="candy/", blank=True, db_column="imagen")

    class Meta:
        verbose_name = "producto de candy"
        verbose_name_plural = "productos de candy"
        db_table = "candy_producto"
        ordering = ("category", "name")

    def __str__(self):
        return self.name

    @classmethod
    def in_menu_order(cls, products):
        category_order = list(cls.Category.values)
        return sorted(products, key=lambda product: (category_order.index(product.category), product.name))

    @property
    def icon(self):
        return self.CATEGORY_ICONS.get(self.category, "popcorn")

    @property
    def available_stock(self):
        return self.stock if self.is_active else 0

    @property
    def max_quantity(self):
        limit = getattr(self, "_purchase_quantity_limit", None)
        return min(self.available_stock, limit if limit is not None else CinemaSettings.current().candy_max_item_quantity)

    @property
    def is_low_stock(self):
        return 0 < self.stock <= LOW_STOCK_THRESHOLD


class CandyCombo(models.Model):
    icon = "popcorn"

    name = models.CharField(max_length=100, unique=True, db_column="nombre")
    price = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        db_column="precio",
    )
    is_active = models.BooleanField(default=True, db_column="activo")
    image = models.ImageField(upload_to="candy/", blank=True, db_column="imagen")
    products = models.ManyToManyField(
        CandyProduct,
        through="CandyComboItem",
        related_name="combos",
    )

    class Meta:
        verbose_name = "combo de candy"
        verbose_name_plural = "combos de candy"
        db_table = "candy_combo"
        ordering = ("name",)

    def __str__(self):
        return self.name

    @property
    def available_stock(self):
        items = list(self.items.all())
        if not self.is_active or not items:
            return 0
        return min(item.product.stock // item.quantity for item in items)

    @property
    def max_quantity(self):
        limit = getattr(self, "_purchase_quantity_limit", None)
        return min(self.available_stock, limit if limit is not None else CinemaSettings.current().candy_max_item_quantity)

    @property
    def contents_label(self):
        return " + ".join(item.label for item in self.items.all())

    @property
    def components_price(self):
        return sum(
            (item.product.price * item.quantity for item in self.items.all()),
            Decimal("0"),
        )

    @property
    def saving(self):
        return max(self.components_price - self.price, Decimal("0"))


class CandyComboItem(models.Model):
    combo = models.ForeignKey(
        CandyCombo,
        on_delete=models.CASCADE,
        related_name="items",
        db_column="combo_id",
    )
    product = models.ForeignKey(
        CandyProduct,
        on_delete=models.PROTECT,
        related_name="combo_items",
        db_column="producto_id",
    )
    quantity = models.PositiveSmallIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
        db_column="cantidad",
    )

    class Meta:
        verbose_name = "producto del combo"
        verbose_name_plural = "productos del combo"
        db_table = "candy_combo_producto"
        ordering = ("pk",)
        constraints = [
            models.UniqueConstraint(fields=["combo", "product"], name="unique_product_per_combo"),
        ]

    def __str__(self):
        return self.label

    @property
    def label(self):
        return f"{self.quantity} × {self.product.name}" if self.quantity > 1 else self.product.name


class CandyOrder(models.Model):
    purchase = models.OneToOneField(
        "tickets.TicketPurchase",
        on_delete=models.CASCADE,
        related_name="candy_order",
        db_column="compra_id",
        null=True,
        blank=True,
    )
    reward_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="reward_candy_orders")
    reward_key = models.UUIDField(null=True, blank=True)
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="candy_orders")
    checkout_key = models.UUIDField(null=True, blank=True)
    items = models.JSONField(default=list, blank=True)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True, db_column="creado_en")
    pickup_token = models.CharField(max_length=32, unique=True, default=generate_ticket_token, editable=False)
    pickup_code_digest = models.CharField(max_length=64, unique=True, editable=False)
    delivered_at = models.DateTimeField(null=True, blank=True, editable=False, db_column="entregado_en")
    delivered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="delivered_candy_orders",
        editable=False,
    )
    restocked_at = models.DateTimeField(null=True, blank=True, editable=False, db_column="repuesto_en")

    class Meta:
        verbose_name = "pedido de candy"
        verbose_name_plural = "pedidos de candy"
        db_table = "candy_pedido"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(condition=(models.Q(purchase__isnull=False, reward_user__isnull=True, reward_key__isnull=True, customer__isnull=True, checkout_key__isnull=True) | models.Q(purchase__isnull=True, reward_user__isnull=False, reward_key__isnull=False, customer__isnull=True, checkout_key__isnull=True) | models.Q(purchase__isnull=True, reward_user__isnull=True, reward_key__isnull=True, customer__isnull=False, checkout_key__isnull=False)), name="candy_order_single_origin"),
            models.UniqueConstraint(fields=["reward_user", "reward_key"], name="candy_reward_order_idempotency"),
            models.UniqueConstraint(fields=["customer", "checkout_key"], name="candy_checkout_idempotency"),
        ]

    def __str__(self):
        if self.is_reward_order:
            return f"Premios · Pedido #{self.pk}"
        if self.is_standalone_order:
            return f"Candy · Pedido #{self.pk}"
        return f"Candy · Compra #{self.purchase_id}"

    @classmethod
    def for_user(cls, user):
        if not user.is_authenticated:
            return cls.objects.none()
        now = timezone.now()
        available = models.Q(delivered_at__isnull=True, restocked_at__isnull=True) & (
            models.Q(purchase__isnull=True) | models.Q(
                purchase__screening__status__in=(Screening.Status.PUBLISHED, Screening.Status.IN_PROGRESS),
                purchase__refund__isnull=True, _pickup_ends_at__gt=now,
            )
        )
        return cls.objects.filter(models.Q(customer=user) | models.Q(reward_user=user) | models.Q(purchase__user=user)).select_related(
            "purchase__screening__movie", "purchase__screening__room", "purchase__refund",
        ).annotate(
            _pickup_ends_at=models.ExpressionWrapper(
                models.F("purchase__screening__starts_at") + models.ExpressionWrapper(
                    Cast("purchase__screening__movie__duration_minutes", models.IntegerField()) * models.Value(timedelta(minutes=1)),
                    output_field=models.DurationField(),
                ),
                output_field=models.DateTimeField(),
            ),
        ).annotate(_pickup_priority=models.Case(models.When(available, then=0), default=1, output_field=models.IntegerField())).order_by("_pickup_priority", "-created_at", "-pk")

    @property
    def is_reward_order(self):
        return self.reward_user_id is not None

    @property
    def is_standalone_order(self):
        return self.customer_id is not None

    @property
    def user_id(self):
        return self.customer_id if self.is_standalone_order else self.reward_user_id if self.is_reward_order else self.purchase.user_id

    @property
    def pickup_code(self):
        return reservation_code_for_token(self.pickup_token)

    @property
    def qr_payload(self):
        return f"{CANDY_QR_PREFIX}{self.pickup_code}"

    @property
    def lines(self):
        return [
            {
                **line,
                "unit_price": Decimal(line["unit_price"]),
                "subtotal": Decimal(line["subtotal"]),
                "is_combo": line["kind"] == "combo",
                "contents": " + ".join(
                    f"{component['quantity']} × {component['name']}"
                    if component["quantity"] > 1 else component["name"]
                    for component in line["components"]
                ),
            }
            for line in self.items or []
        ]

    @property
    def summary(self):
        return ", ".join(f"{line['quantity']} × {line['name']}" for line in self.items or [])

    @property
    def item_count(self):
        return sum(line["quantity"] for line in self.items or [])

    @property
    def is_refunded(self):
        if self.is_reward_order or self.is_standalone_order:
            return self.restocked_at is not None
        return (
            self.purchase.screening.status == Screening.Status.CANCELED
            or hasattr(self.purchase, "refund")
        )

    @property
    def is_expired(self):
        if self.is_reward_order or self.is_standalone_order:
            return False
        screening = self.purchase.screening
        return (
            screening.status not in (Screening.Status.PUBLISHED, Screening.Status.IN_PROGRESS)
            or screening.ends_at <= timezone.now()
        )

    @property
    def pickup_open(self):
        return self.delivered_at is None and not self.is_refunded and not self.is_expired

    def stock_requirements(self):
        required = Counter()
        for line in self.items or []:
            for component in line["components"]:
                required[component["product_id"]] += line["quantity"] * component["quantity"]
        return required

    def restock(self):
        if self.is_reward_order:
            return  # Reward units remain reserved by their coupons, independent of screenings.
        if self.delivered_at is not None or self.restocked_at is not None:
            return
        required = self.stock_requirements()
        products = CandyProduct.objects.select_for_update().filter(pk__in=required).order_by("pk")
        for product in products:
            product.stock += required[product.pk]
            product.save(update_fields=["stock"])
        self.restocked_at = timezone.now()
        self.save(update_fields=["restocked_at"])

    @staticmethod
    def parse_selection(requested_items, *, enforce_limit=True):
        if not isinstance(requested_items, list):
            raise ValidationError(INVALID_SELECTION_MESSAGE)
        quantities = {}
        limit = CinemaSettings.current().candy_max_item_quantity if enforce_limit else None
        for item in requested_items:
            if not isinstance(item, dict) or item.get("kind") not in {"product", "combo"}:
                raise ValidationError(INVALID_SELECTION_MESSAGE)
            try:
                item_id = int(item.get("id"))
                quantity = int(item.get("quantity"))
            except (TypeError, ValueError):
                raise ValidationError(INVALID_SELECTION_MESSAGE)
            if quantity < 0:
                raise ValidationError(INVALID_SELECTION_MESSAGE)
            if quantity == 0:
                continue
            key = (item["kind"], item_id)
            quantities[key] = quantities.get(key, 0) + quantity
            if limit is not None and quantities[key] > limit:
                raise ValidationError(
                    f"Podés llevar hasta {limit} {'unidad' if limit == 1 else 'unidades'} de cada producto o combo."
                )
        return quantities

    @classmethod
    def create_for(cls, purchase, requested_items, *, customer=None, checkout_key=None):
        quantities = cls.parse_selection(requested_items)
        if not quantities:
            return None
        combo_ids = [item_id for kind, item_id in quantities if kind == "combo"]
        combos = {
            combo.pk: combo
            for combo in CandyCombo.objects.filter(pk__in=combo_ids, is_active=True)
            .prefetch_related("items__product")
        }
        lines = []
        for (kind, item_id), quantity in quantities.items():
            if kind == "combo":
                combo = combos.get(item_id)
                if combo is None or not combo.items.all():
                    raise ValidationError(UNAVAILABLE_ITEM_MESSAGE)
                components = [
                    {"product_id": item.product_id, "name": item.product.name, "quantity": item.quantity}
                    for item in combo.items.all()
                ]
                lines.append({"kind": kind, "id": item_id, "name": combo.name, "price": combo.price,
                              "quantity": quantity, "components": components})
            else:
                lines.append({"kind": kind, "id": item_id, "quantity": quantity,
                              "components": [{"product_id": item_id, "quantity": 1}]})

        with transaction.atomic():
            required = Counter()
            for line in lines:
                for component in line["components"]:
                    required[component["product_id"]] += line["quantity"] * component["quantity"]
            products = {
                product.pk: product
                for product in CandyProduct.objects.select_for_update()
                .filter(pk__in=required).order_by("pk")
            }
            for line in lines:
                if line["kind"] != "product":
                    continue
                product = products.get(line["id"])
                if product is None or not product.is_active:
                    raise ValidationError(UNAVAILABLE_ITEM_MESSAGE)
                line["name"] = product.name
                line["price"] = product.price
                line["components"][0]["name"] = product.name
            for product_id, quantity in required.items():
                product = products.get(product_id)
                if product is None:
                    raise ValidationError(UNAVAILABLE_ITEM_MESSAGE)
                if product.stock < quantity:
                    raise ValidationError(f"No queda stock suficiente de {product.name}.")
            for product_id, quantity in required.items():
                product = products[product_id]
                if not CandyProduct.objects.filter(pk=product.pk, stock__gte=quantity).update(stock=models.F("stock") - quantity):
                    raise ValidationError(f"No queda stock suficiente de {product.name}.")

            items = []
            for line in lines:
                price = line.pop("price")
                items.append({
                    **line,
                    "unit_price": str(price),
                    "subtotal": str(price * line["quantity"]),
                })
            order = cls(
                purchase=purchase,
                customer=customer,
                checkout_key=checkout_key,
                items=items,
                total=sum((Decimal(item["subtotal"]) for item in items), Decimal("0")),
            )
            order.save()
            return order

    def save(self, *args, **kwargs):
        creating = self._state.adding
        for attempt in range(32 if creating else 1):
            if not self.pickup_token or (creating and attempt):
                self.pickup_token = generate_ticket_token()
            self.pickup_code_digest = reservation_code_digest(self.pickup_code)
            try:
                with transaction.atomic():
                    super().save(*args, **kwargs)
                return
            except IntegrityError:
                if not creating:
                    raise
                collision = CandyOrder.objects.filter(
                    models.Q(pickup_token=self.pickup_token)
                    | models.Q(pickup_code_digest=self.pickup_code_digest)
                ).exists()
                if not collision:
                    raise
                self.pk = None
                self._state.adding = True
        raise RuntimeError("No se pudo generar un código de retiro único.")


class CandyPickup(UndoWindowMixin, models.Model):
    order = models.ForeignKey(CandyOrder, on_delete=models.CASCADE, related_name="pickups")
    operator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="candy_pickups",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    reverted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["operator", "-created_at"], name="candy_pickup_recent_idx"),
        ]
        verbose_name = "Entrega de candy"
        verbose_name_plural = "Entregas de candy"

    def __str__(self):
        return f"Entrega · {self.order}"
