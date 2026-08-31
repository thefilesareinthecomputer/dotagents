"""Unit tests for the pure helper functions."""
from decimal import Decimal

from django.test import SimpleTestCase

from core.utils import clamp, money, percent, slugify_number, summarize_amounts


class MoneyTests(SimpleTestCase):
    def test_money_rounds_half_up(self):
        self.assertEqual(money("1.005"), Decimal("1.01"))

    def test_money_passes_through_decimal(self):
        self.assertEqual(money(Decimal("2.5")), Decimal("2.50"))

    def test_percent_of_zero_is_zero(self):
        self.assertEqual(percent(5, 0), Decimal("0.00"))

    def test_percent_computes(self):
        self.assertEqual(percent(25, 100), Decimal("25.00"))


class MiscTests(SimpleTestCase):
    def test_clamp_bounds(self):
        self.assertEqual(clamp(5, 0, 3), 3)
        self.assertEqual(clamp(-1, 0, 3), 0)
        self.assertEqual(clamp(2, 0, 3), 2)

    def test_slugify_number_pads(self):
        self.assertEqual(slugify_number("INV", 7, 42), "INV-0007-00042")

    def test_summarize_amounts(self):
        result = summarize_amounts(["10.00", "20.00", "30.00"])
        self.assertEqual(result["count"], 3)
        self.assertEqual(result["total"], Decimal("60.00"))
        self.assertEqual(result["average"], Decimal("20.00"))
