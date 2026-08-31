"""Add Customer, Invoice and LineItem tables."""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="org",
            name="billing_contact",
            field=models.EmailField(blank=True, max_length=254),
        ),
        migrations.AddField(
            model_name="user",
            name="is_billing_admin",
            field=models.BooleanField(default=False),
        ),
        migrations.CreateModel(
            name="Customer",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True)),
                ("name", models.CharField(max_length=200)),
                ("contact", models.EmailField(max_length=254)),
                ("is_archived", models.BooleanField(default=False)),
                ("org", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="customers", to="core.org")),
            ],
            options={"ordering": ["name"], "unique_together": {("org", "contact")}},
        ),
        migrations.CreateModel(
            name="Invoice",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True)),
                ("number", models.CharField(max_length=32)),
                ("status", models.CharField(default="draft", max_length=8)),
                ("notes", models.TextField(blank=True)),
                ("customer", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="invoices", to="core.customer")),
                ("org", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="invoices", to="core.org")),
            ],
            options={"ordering": ["-id"], "unique_together": {("org", "number")}},
        ),
        migrations.CreateModel(
            name="LineItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True)),
                ("description", models.CharField(max_length=255)),
                ("quantity", models.DecimalField(decimal_places=2, max_digits=8)),
                ("unit_price", models.DecimalField(decimal_places=2, max_digits=10)),
                ("invoice", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="lines", to="core.invoice")),
            ],
            options={"ordering": ["id"]},
        ),
    ]
