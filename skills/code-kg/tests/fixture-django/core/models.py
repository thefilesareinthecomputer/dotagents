"""Domain models for the invoicing backend."""
from decimal import Decimal

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class Org(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    billing_contact = models.EmailField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["name"]
        verbose_name = "organization"

    def __str__(self):
        return self.name

    def active_customer_count(self):
        return self.customers.filter(is_archived=False).count()


class User(AbstractUser):
    """Custom user, bound to exactly one org."""

    org = models.ForeignKey("core.Org", on_delete=models.CASCADE, related_name="members")
    is_billing_admin = models.BooleanField(default=False)

    class Meta:
        ordering = ["username"]

    def __str__(self):
        return self.username


class Customer(models.Model):
    org = models.ForeignKey(Org, on_delete=models.CASCADE, related_name="customers")
    name = models.CharField(max_length=200)
    contact = models.EmailField()
    is_archived = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["name"]
        unique_together = ("org", "contact")

    def __str__(self):
        return self.name


class InvoiceQuerySet(models.QuerySet):
    def open(self):
        return self.exclude(status__in=[Invoice.PAID, Invoice.VOID])

    def paid(self):
        return self.filter(status=Invoice.PAID)

    def for_org(self, org):
        return self.filter(org=org)


class Invoice(models.Model):
    DRAFT = "draft"
    SENT = "sent"
    PAID = "paid"
    VOID = "void"
    STATUS_CHOICES = [
        (DRAFT, "Draft"),
        (SENT, "Sent"),
        (PAID, "Paid"),
        (VOID, "Void"),
    ]

    objects = InvoiceQuerySet.as_manager()

    org = models.ForeignKey(Org, on_delete=models.CASCADE, related_name="invoices")
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="invoices")
    number = models.CharField(max_length=32)
    status = models.CharField(max_length=8, choices=STATUS_CHOICES, default=DRAFT)
    issued_at = models.DateTimeField(default=timezone.now)
    due_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-issued_at"]
        unique_together = ("org", "number")

    def __str__(self):
        return self.number

    @property
    def total(self):
        return sum((line.amount for line in self.lines.all()), Decimal("0.00"))

    def mark_paid(self):
        self.status = self.PAID
        self.save(update_fields=["status"])

    def is_overdue(self):
        if self.status == self.PAID or self.due_at is None:
            return False
        return self.due_at < timezone.now()

    def amount_paid(self):
        return sum((p.amount for p in self.payments.all()), Decimal("0.00"))

    def balance(self):
        remaining = self.total - self.amount_paid()
        return remaining if remaining > 0 else Decimal("0.00")

    def line_count(self):
        return self.lines.count()


class LineItem(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="lines")
    description = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("1.00"))
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return self.description

    @property
    def amount(self):
        return self.quantity * self.unit_price


class Payment(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="payments")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reference = models.CharField(max_length=64, blank=True)
    received_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-received_at"]

    def __str__(self):
        return self.reference or f"payment {self.pk}"
