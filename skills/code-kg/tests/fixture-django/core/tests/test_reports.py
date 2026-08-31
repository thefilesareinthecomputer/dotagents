"""Tests for the reporting service."""
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from core.services.reports import collection_summary, paid_invoice_stats, top_customers
from core.tests.factories import make_customer, make_invoice, make_org


class CollectionSummaryTests(TestCase):
    def setUp(self):
        self.org = make_org()
        self.customer = make_customer(self.org)

    def test_summary_counts_outstanding(self):
        make_invoice(self.org, self.customer)
        summary = collection_summary(self.org)
        self.assertEqual(summary["outstanding_count"], 1)
        self.assertEqual(summary["outstanding_total"], Decimal("100.00"))

    def test_overdue_rate_handles_empty(self):
        summary = collection_summary(self.org)
        self.assertEqual(summary["overdue_rate"], Decimal("0.00"))

    def test_overdue_counted(self):
        invoice = make_invoice(self.org, self.customer)
        invoice.due_at = timezone.now() - timezone.timedelta(days=2)
        invoice.save(update_fields=["due_at"])
        summary = collection_summary(self.org)
        self.assertEqual(summary["overdue_count"], 1)


class StatsTests(TestCase):
    def setUp(self):
        self.org = make_org()
        self.customer = make_customer(self.org)

    def test_paid_stats_empty(self):
        stats = paid_invoice_stats(self.org)
        self.assertEqual(stats["count"], 0)
        self.assertEqual(stats["average"], Decimal("0.00"))

    def test_top_customers_limit(self):
        make_invoice(self.org, self.customer)
        rows = top_customers(self.org, limit=3)
        self.assertLessEqual(len(rows), 3)
