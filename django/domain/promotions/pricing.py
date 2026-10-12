from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal

from .models import Promotion


class SeatPriceComponent(ABC):
    """Component in the seat-price decorator chain."""

    @property
    @abstractmethod
    def amount(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def base_amount(self):
        raise NotImplementedError

    @property
    def promotion(self):
        return None


class BaseSeatPrice(SeatPriceComponent):
    def __init__(self, amount):
        self._amount = Decimal(str(amount))

    @property
    def amount(self):
        return self._amount

    @property
    def base_amount(self):
        return self._amount


class PromotionDiscountDecorator(SeatPriceComponent):
    """Decorator that applies exactly one eligible promotion to a base price."""

    def __init__(self, wrapped, promotion):
        self.wrapped = wrapped
        self._promotion = promotion

    @property
    def amount(self):
        return self._promotion.discounted_price(self.wrapped.amount)

    @property
    def base_amount(self):
        return self.wrapped.base_amount

    @property
    def promotion(self):
        return self._promotion


@dataclass(frozen=True)
class SeatPriceQuote:
    base_price: Decimal
    final_price: Decimal
    promotion: Promotion | None = None

    @property
    def discount(self):
        return self.base_price - self.final_price


class PromotionPriceCalculator:
    """Select the best single promotion for each seat without stacking offers."""

    def __init__(self, promotions):
        self.promotions = list(promotions)

    @classmethod
    def current(cls):
        promotions = Promotion.objects.filter(is_active=True).prefetch_related("seat_types")
        return cls(promotions)

    def quote(self, base_price, seat_type_id, screening_starts_at):
        base_component = BaseSeatPrice(base_price)
        candidates = [base_component]
        for promotion in self.promotions:
            if promotion.applies_to(seat_type_id, screening_starts_at):
                candidates.append(PromotionDiscountDecorator(base_component, promotion))

        # Keep the regular price in a tie so a no-op promotion is never reported.
        selected = min(candidates, key=lambda component: component.amount)
        return SeatPriceQuote(
            base_price=selected.base_amount,
            final_price=selected.amount,
            promotion=selected.promotion,
        )
