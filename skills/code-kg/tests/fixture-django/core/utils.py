"""Small pure helpers shared across the service and selector layers."""
from decimal import ROUND_HALF_UP, Decimal

CENTS = Decimal("0.01")


def money(value):
    """Coerce any numeric-ish value into a 2-place Decimal."""
    if isinstance(value, Decimal):
        amount = value
    else:
        amount = Decimal(str(value))
    return amount.quantize(CENTS, rounding=ROUND_HALF_UP)


def percent(part, whole):
    """Return part/whole as a rounded percentage, tolerating a zero whole."""
    whole = Decimal(str(whole))
    if whole == 0:
        return Decimal("0.00")
    return money(Decimal(str(part)) / whole * 100)


def clamp(value, low, high):
    return max(low, min(value, high))


def slugify_number(prefix, org_pk, seq):
    return f"{prefix}-{org_pk:04d}-{seq:05d}"


def summarize_amounts(amounts):
    """Return count, total and average for an iterable of amounts."""
    values = [money(a) for a in amounts]
    total = sum(values, Decimal("0.00"))
    count = len(values)
    average = money(total / count) if count else Decimal("0.00")
    return {"count": count, "total": total, "average": average}
