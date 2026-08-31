"""Seed the database with a demo org and user."""
from django.core.management.base import BaseCommand

from core.models import Org, User


class Command(BaseCommand):
    help = "Create demo records."

    def handle(self, *args, **options):
        org, _ = Org.objects.get_or_create(name="Demo", slug="demo")
        User.objects.get_or_create(username="admin", org=org)
        self.stdout.write("seeded")
