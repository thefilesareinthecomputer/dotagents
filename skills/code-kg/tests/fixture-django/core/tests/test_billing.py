"""Behavior tests for the billing service layer."""
from decimal import Decimal

from django.test import TestCase

from core.models import Invoice
from core.services.billing import (
    BillingError,
    add_line,
    create_invoice,
    outstanding_balance,
    record_payment,
    send_invoice,
    void_invoice,
)
from core.tests.factories import make_customer, make_org


class CreateInvoiceTests(TestCase):
    def setUp(self):
        self.org = make_org()
        self.customer = make_customer(self.org)

    def test_create_invoice_sets_number_and_lines(self):
        invoice = create_invoice(
            org=self.org,
            customer=self.customer,
            lines=[{"description": "Setup", "unit_price": "100.00", "quantity": "2"}],
        )
        self.assertEqual(invoice.status, Invoice.DRAFT)
        self.assertEqual(invoice.lines.count(), 1)
        self.assertEqual(invoice.total, Decimal("200.00"))

    def test_create_invoice_rejects_foreign_customer(self):
        other = make_org(slug="other")
        stranger = make_customer(other, contact="x@example.test")
        with self.assertRaises(BillingError):
            create_invoice(org=self.org, customer=stranger, lines=[])


class PaymentTests(TestCase):
    def setUp(self):
        self.org = make_org()
        self.customer = make_customer(self.org)
        self.invoice = create_invoice(
            org=self.org,
            customer=self.customer,
            lines=[{"description": "Work", "unit_price": "40.00", "quantity": "1"}],
        )

    def test_full_payment_marks_paid(self):
        send_invoice(self.invoice)
        record_payment(self.invoice, "40.00", reference="wire-1")
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.PAID)

    def test_negative_payment_rejected(self):
        with self.assertRaises(BillingError):
            record_payment(self.invoice, "-1.00")

    def test_send_requires_draft(self):
        send_invoice(self.invoice)
        with self.assertRaises(BillingError):
            send_invoice(self.invoice)

    def test_partial_payment_leaves_balance(self):
        record_payment(self.invoice, "10.00")
        self.assertEqual(outstanding_balance(self.invoice), Decimal("30.00"))

    def test_void_draft_invoice(self):
        voided = void_invoice(self.invoice, reason="duplicate")
        self.assertEqual(voided.status, Invoice.VOID)
        self.assertIn("duplicate", voided.notes)

    def test_void_paid_invoice_rejected(self):
        send_invoice(self.invoice)
        record_payment(self.invoice, "40.00")
        with self.assertRaises(BillingError):
            void_invoice(self.invoice)

    def test_add_line_only_on_draft(self):
        add_line(self.invoice, "Extra", "5.00", quantity="2")
        self.assertEqual(self.invoice.lines.count(), 2)
        send_invoice(self.invoice)
        with self.assertRaises(BillingError):
            add_line(self.invoice, "Late", "1.00")
