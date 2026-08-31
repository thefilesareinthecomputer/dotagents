"""Billing operations: invoice creation, line editing, payment recording."""
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from core.models import Invoice, LineItem, Payment
from core.selectors import next_invoice_number
from core.services.notifications import notify_invoice_sent


class BillingError(Exception):
    """Raised when a billing operation violates an invariant."""


@transaction.atomic
def create_invoice(*, org, customer, lines, due_at=None):
    if customer.org_id != org.id:
        raise BillingError("customer does not belong to this org")
    invoice = Invoice.objects.create(
        org=org,
        customer=customer,
        number=next_invoice_number(org),
        due_at=due_at,
    )
    for line in lines:
        LineItem.objects.create(
            invoice=invoice,
            description=line["description"],
            quantity=Decimal(str(line.get("quantity", "1"))),
            unit_price=Decimal(str(line["unit_price"])),
        )
    return invoice


@transaction.atomic
def send_invoice(invoice):
    if invoice.status != Invoice.DRAFT:
        raise BillingError("only draft invoices can be sent")
    invoice.status = Invoice.SENT
    invoice.issued_at = timezone.now()
    invoice.save(update_fields=["status", "issued_at"])
    notify_invoice_sent(invoice)
    return invoice


@transaction.atomic
def record_payment(invoice, amount, reference=""):
    amount = Decimal(str(amount))
    if amount <= 0:
        raise BillingError("payment amount must be positive")
    payment = Payment.objects.create(
        invoice=invoice,
        amount=amount,
        reference=reference,
    )
    paid = sum((p.amount for p in invoice.payments.all()), Decimal("0.00"))
    if paid >= invoice.total:
        invoice.mark_paid()
    return payment


@transaction.atomic
def void_invoice(invoice, reason=""):
    if invoice.status == Invoice.PAID:
        raise BillingError("paid invoices cannot be voided")
    invoice.status = Invoice.VOID
    if reason:
        invoice.notes = (invoice.notes + "\n" + reason).strip()
    invoice.save(update_fields=["status", "notes"])
    return invoice


@transaction.atomic
def add_line(invoice, description, unit_price, quantity="1"):
    if invoice.status != Invoice.DRAFT:
        raise BillingError("lines can only be added to draft invoices")
    return LineItem.objects.create(
        invoice=invoice,
        description=description,
        quantity=Decimal(str(quantity)),
        unit_price=Decimal(str(unit_price)),
    )


def outstanding_balance(invoice):
    paid = sum((p.amount for p in invoice.payments.all()), Decimal("0.00"))
    balance = invoice.total - paid
    return balance if balance > 0 else Decimal("0.00")
