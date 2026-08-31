"""Send every draft invoice for an org, optionally filtering by customer."""
from django.core.management.base import BaseCommand, CommandError

from core.models import Invoice, Org
from core.services.billing import BillingError, send_invoice


class Command(BaseCommand):
    help = "Transition draft invoices to sent and deliver notifications."

    def add_arguments(self, parser):
        parser.add_argument("org_slug", type=str)
        parser.add_argument("--customer", type=int, default=None)
        parser.add_argument("--limit", type=int, default=0)

    def handle(self, *args, **options):
        try:
            org = Org.objects.get(slug=options["org_slug"])
        except Org.DoesNotExist as exc:
            raise CommandError("unknown org") from exc
        qs = Invoice.objects.filter(org=org, status=Invoice.DRAFT)
        if options["customer"]:
            qs = qs.filter(customer_id=options["customer"])
        if options["limit"]:
            qs = qs[: options["limit"]]
        for invoice in qs:
            try:
                send_invoice(invoice)
            except BillingError as exc:
                self.stderr.write(str(exc))
                continue
            self.stdout.write(f"sent {invoice.number}")
