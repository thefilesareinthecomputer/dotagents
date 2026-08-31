"""Read-side query helpers. Selectors never mutate; they shape querysets for
views, services and tasks."""
from django.db.models import Count, Q, Sum
from django.utils import timezone

from core.models import Customer, Invoice
from core.utils import slugify_number


def next_invoice_number(org):
    count = Invoice.objects.filter(org=org).count()
    return slugify_number("INV", org.pk, count + 1)


def outstanding_invoices(org):
    return (
        Invoice.objects.filter(org=org)
        .exclude(status__in=[Invoice.PAID, Invoice.VOID])
        .select_related("customer")
    )


def overdue_invoices(org):
    now = timezone.now()
    return outstanding_invoices(org).filter(due_at__lt=now)


def revenue_by_customer(org):
    return (
        Customer.objects.filter(org=org)
        .annotate(
            invoiced=Sum("invoices__lines__unit_price"),
            invoice_count=Count("invoices", filter=Q(invoices__status=Invoice.PAID)),
        )
        .order_by("-invoiced")
    )


def customers_for(org):
    return Customer.objects.filter(org=org, is_archived=False)


def invoices_for_customer(customer):
    return Invoice.objects.filter(customer=customer).order_by("-issued_at")


def paid_total(org):
    row = (
        Invoice.objects.filter(org=org, status=Invoice.PAID)
        .aggregate(total=Sum("lines__unit_price"))
    )
    return row["total"] or 0


def status_breakdown(org):
    rows = (
        Invoice.objects.filter(org=org)
        .values("status")
        .annotate(count=Count("id"))
        .order_by("status")
    )
    return {row["status"]: row["count"] for row in rows}


def recent_invoices(org, limit=10):
    return list(
        Invoice.objects.filter(org=org)
        .select_related("customer")
        .order_by("-issued_at")[:limit]
    )
