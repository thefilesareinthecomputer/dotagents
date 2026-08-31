"""Run a single pass of the background task queue for one org or all orgs."""
from django.core.management.base import BaseCommand, CommandError

from core.models import Org
from core.tasks import acknowledge_payments, dispatch_pending_invoices, remind_overdue


class Command(BaseCommand):
    help = "Process pending invoices, reminders and payment acknowledgements."

    def add_arguments(self, parser):
        parser.add_argument("--org", type=str, help="Limit to one org slug.")
        parser.add_argument(
            "--skip-reminders",
            action="store_true",
            help="Do not send overdue reminders.",
        )

    def handle(self, *args, **options):
        orgs = Org.objects.all()
        if options["org"]:
            orgs = orgs.filter(slug=options["org"])
            if not orgs.exists():
                raise CommandError(f"no org with slug {options['org']}")
        for org in orgs:
            sent = dispatch_pending_invoices(org)
            acknowledge_payments(org)
            if not options["skip_reminders"]:
                remind_overdue(org)
            self.stdout.write(f"{org.slug}: dispatched {sent}")
