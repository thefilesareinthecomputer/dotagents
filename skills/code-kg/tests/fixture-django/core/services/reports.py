"""Reporting service: aggregate figures for dashboards and the revenue API."""
from decimal import Decimal

from core.models import Invoice
from core.selectors import outstanding_invoices, overdue_invoices, revenue_by_customer
from core.utils import money, percent, summarize_amounts


def collection_summary(org):
    """Headline numbers: outstanding, overdue and the collection rate."""
    outstanding = list(outstanding_invoices(org))
    overdue = list(overdue_invoices(org))
    outstanding_total = sum((i.total for i in outstanding), Decimal("0.00"))
    overdue_total = sum((i.total for i in overdue), Decimal("0.00"))
    return {
        "outstanding_count": len(outstanding),
        "outstanding_total": money(outstanding_total),
        "overdue_count": len(overdue),
        "overdue_total": money(overdue_total),
        "overdue_rate": percent(overdue_total, outstanding_total),
    }


def paid_invoice_stats(org):
    paid = Invoice.objects.filter(org=org, status=Invoice.PAID)
    return summarize_amounts(inv.total for inv in paid)


def top_customers(org, limit=5):
    rows = revenue_by_customer(org)[:limit]
    return [
        {"customer": r.name, "invoiced": money(r.invoiced or 0)}
        for r in rows
    ]
