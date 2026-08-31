"""Unit tests for model methods and properties."""
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from core.models import LineItem
from core.tests.factories import make_customer, make_invoice, make_org


class ModelTests(TestCase):
    def setUp(self):
        self.org = make_org()
        self.customer = make_customer(self.org)
        self.invoice = make_invoice(self.org, self.customer)

    def test_line_amount(self):
        line = self.invoice.lines.first()
        self.assertEqual(line.amount, line.quantity * line.unit_price)

    def test_invoice_total_sums_lines(self):
        LineItem.objects.create(
            invoice=self.invoice,
            description="Extra",
            quantity=Decimal("1"),
            unit_price=Decimal("10.00"),
        )
        self.assertEqual(self.invoice.total, Decimal("110.00"))

    def test_is_overdue_false_when_no_due_date(self):
        self.assertFalse(self.invoice.is_overdue())

    def test_is_overdue_true_when_past_due(self):
        self.invoice.due_at = timezone.now() - timezone.timedelta(days=1)
        self.invoice.save(update_fields=["due_at"])
        self.assertTrue(self.invoice.is_overdue())

    def test_active_customer_count(self):
        self.assertEqual(self.org.active_customer_count(), 1)

    def test_line_count(self):
        self.assertEqual(self.invoice.line_count(), 1)

    def test_balance_before_payment(self):
        self.assertEqual(self.invoice.balance(), self.invoice.total)

    def test_amount_paid_starts_zero(self):
        self.assertEqual(self.invoice.amount_paid(), Decimal("0.00"))


class QuerySetTests(TestCase):
    def setUp(self):
        from core.models import Invoice
        self.Invoice = Invoice
        self.org = make_org()
        self.customer = make_customer(self.org)

    def test_open_excludes_paid(self):
        invoice = make_invoice(self.org, self.customer)
        self.assertIn(invoice, self.Invoice.objects.for_org(self.org).open())
        invoice.mark_paid()
        self.assertNotIn(invoice, self.Invoice.objects.for_org(self.org).open())

    def test_paid_filter(self):
        invoice = make_invoice(self.org, self.customer)
        invoice.mark_paid()
        self.assertIn(invoice, self.Invoice.objects.paid())
