"""Background jobs. Registered by dotted path in the scheduler config and
invoked by the runworker management command."""
from core.selectors import overdue_invoices
from core.services.billing import send_invoice, void_invoice
from core.services.notifications import notify_payment_received
from core.services.reports import collection_summary


def dispatch_pending_invoices(org):
    from core.models import Invoice

    sent = 0
    for invoice in Invoice.objects.filter(org=org, status=Invoice.DRAFT):
        send_invoice(invoice)
        sent += 1
    return sent


def remind_overdue(org):
    reminded = []
    for invoice in overdue_invoices(org):
        reminded.append(invoice.number)
    return reminded


def acknowledge_payments(org):
    from core.models import Payment

    for payment in Payment.objects.filter(invoice__org=org):
        notify_payment_received(payment)


def expire_stale_drafts(org, older_than_days=90):
    from django.utils import timezone

    from core.models import Invoice

    cutoff = timezone.now() - timezone.timedelta(days=older_than_days)
    voided = 0
    for invoice in Invoice.objects.filter(
        org=org, status=Invoice.DRAFT, issued_at__lt=cutoff
    ):
        void_invoice(invoice, reason="expired draft")
        voided += 1
    return voided


def nightly_digest(org):
    """Assemble the numbers a scheduled digest job would send to owners."""
    summary = collection_summary(org)
    summary["reminded"] = remind_overdue(org)
    return summary
