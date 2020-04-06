from decimal import Decimal
from logging import getLogger


logger = getLogger('django')


def to_cents(amount: Decimal, divisibility: int) -> int:
    return int(amount * Decimal('10')**divisibility)


def from_cents(amount: int, divisibility: int) -> Decimal:
    return Decimal(amount) / Decimal('10')**divisibility
