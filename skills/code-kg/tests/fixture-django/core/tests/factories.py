"""Lightweight object builders shared across the test modules."""
from decimal import Decimal

from core.models import Customer, Invoice, LineItem, Org, User


def make_org(slug="acme"):
    return Org.objects.create(name=slug.title(), slug=slug)


def make_user(org, username="worker", billing_admin=False):
    return User.objects.create(
        username=username, org=org, is_billing_admin=billing_admin
    )


def make_customer(org, contact="buyer@example.test"):
    return Customer.objects.create(org=org, name="Buyer", contact=contact)


def make_invoice(org, customer, number="INV-0001-00001"):
    invoice = Invoice.objects.create(org=org, customer=customer, number=number)
    LineItem.objects.create(
        invoice=invoice,
        description="Service",
        quantity=Decimal("2"),
        unit_price=Decimal("50.00"),
    )
    return invoice
