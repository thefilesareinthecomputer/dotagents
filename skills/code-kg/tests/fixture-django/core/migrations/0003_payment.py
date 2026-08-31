"""Add the Payment table and invoice due date."""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0002_customer_invoice"),
    ]

    operations = [
        migrations.AddField(
            model_name="invoice",
            name="due_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name="Payment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12)),
                ("reference", models.CharField(blank=True, max_length=64)),
                ("invoice", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="payments", to="core.invoice")),
            ],
            options={"ordering": ["-id"]},
        ),
    ]
