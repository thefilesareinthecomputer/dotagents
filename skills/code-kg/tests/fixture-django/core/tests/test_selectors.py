"""Tests for read-side selectors."""
from django.test import TestCase
from django.utils import timezone

from core.models import Invoice
from core.selectors import (
    invoices_for_customer,
    next_invoice_number,
    outstanding_invoices,
    overdue_invoices,
    recent_invoices,
    status_breakdown,
)
from core.tests.factories import make_customer, make_invoice, make_org


class SelectorTests(TestCase):
    def setUp(self):
        self.org = make_org()
        self.customer = make_customer(self.org)

    def test_next_invoice_number_increments(self):
        first = next_invoice_number(self.org)
        make_invoice(self.org, self.customer, number=first)
        second = next_invoice_number(self.org)
        self.assertNotEqual(first, second)
        self.assertTrue(second.startswith("INV-"))

    def test_outstanding_excludes_paid(self):
        invoice = make_invoice(self.org, self.customer)
        self.assertIn(invoice, outstanding_invoices(self.org))
        invoice.status = Invoice.PAID
        invoice.save(update_fields=["status"])
        self.assertNotIn(invoice, outstanding_invoices(self.org))

    def test_overdue_filters_by_due_date(self):
        invoice = make_invoice(self.org, self.customer)
        invoice.due_at = timezone.now() - timezone.timedelta(days=3)
        invoice.save(update_fields=["due_at"])
        self.assertIn(invoice, overdue_invoices(self.org))

    def test_invoices_for_customer(self):
        invoice = make_invoice(self.org, self.customer)
        self.assertIn(invoice, invoices_for_customer(self.customer))

    def test_status_breakdown_counts(self):
        make_invoice(self.org, self.customer)
        breakdown = status_breakdown(self.org)
        self.assertEqual(breakdown.get(Invoice.DRAFT), 1)

    def test_recent_invoices_limit(self):
        make_invoice(self.org, self.customer)
        rows = recent_invoices(self.org, limit=5)
        self.assertLessEqual(len(rows), 5)
        self.assertTrue(rows)
