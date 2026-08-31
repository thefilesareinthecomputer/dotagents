"""Reusable field validators for the billing serializers and forms."""
from decimal import Decimal

from django.core.exceptions import ValidationError


def validate_positive_amount(value):
    if Decimal(str(value)) <= 0:
        raise ValidationError("amount must be greater than zero")


def validate_slug_charset(value):
    allowed = set("abcdefghijklmnopqrstuvwxyz0123456789-")
    if not value or set(value) - allowed:
        raise ValidationError("slug may contain lowercase letters, digits and hyphens")


def validate_quantity(value):
    quantity = Decimal(str(value))
    if quantity <= 0:
        raise ValidationError("quantity must be positive")
    if quantity != quantity.to_integral_value() and quantity.as_tuple().exponent < -2:
        raise ValidationError("quantity is limited to two decimal places")
