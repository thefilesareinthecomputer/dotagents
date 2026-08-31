"""Print a collection summary for one org or every org."""
import json

from django.core.management.base import BaseCommand

from core.models import Org
from core.services.reports import collection_summary, top_customers


class Command(BaseCommand):
    help = "Emit collection figures as JSON for reporting pipelines."

    def add_arguments(self, parser):
        parser.add_argument("--org", type=str, default=None)
        parser.add_argument(
            "--with-customers",
            action="store_true",
            help="Include the top customers block.",
        )

    def handle(self, *args, **options):
        orgs = Org.objects.all()
        if options["org"]:
            orgs = orgs.filter(slug=options["org"])
        report = {}
        for org in orgs:
            figures = collection_summary(org)
            if options["with_customers"]:
                figures["top_customers"] = top_customers(org)
            report[org.slug] = _jsonable(figures)
        self.stdout.write(json.dumps(report, indent=2))


def _jsonable(figures):
    return {k: str(v) if hasattr(v, "quantize") else v for k, v in figures.items()}
