"""Tests for the reusable field validators."""
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from core.validators import validate_positive_amount, validate_quantity, validate_slug_charset


class ValidatorTests(SimpleTestCase):
    def test_positive_amount_accepts(self):
        validate_positive_amount("10.00")

    def test_positive_amount_rejects_zero(self):
        with self.assertRaises(ValidationError):
            validate_positive_amount("0")

    def test_slug_charset_accepts(self):
        validate_slug_charset("acme-corp")

    def test_slug_charset_rejects_upper(self):
        with self.assertRaises(ValidationError):
            validate_slug_charset("Acme")

    def test_quantity_rejects_negative(self):
        with self.assertRaises(ValidationError):
            validate_quantity("-1")

    def test_quantity_accepts_two_places(self):
        validate_quantity("2.50")
