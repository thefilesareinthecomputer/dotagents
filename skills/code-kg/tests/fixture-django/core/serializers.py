"""DRF serializers for the billing API surface."""
from rest_framework import serializers

from core.models import Customer, Invoice, LineItem, Org, Payment
from core.validators import validate_positive_amount, validate_quantity


class OrgSerializer(serializers.ModelSerializer):
    active_customers = serializers.IntegerField(
        source="active_customer_count", read_only=True
    )

    class Meta:
        model = Org
        fields = ["id", "name", "slug", "billing_contact", "active_customers"]


class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = ["id", "name", "contact", "is_archived", "created_at"]
        read_only_fields = ["created_at"]


class LineItemSerializer(serializers.ModelSerializer):
    amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )
    unit_price = serializers.DecimalField(
        max_digits=10, decimal_places=2, validators=[validate_positive_amount]
    )
    quantity = serializers.DecimalField(
        max_digits=8, decimal_places=2, validators=[validate_quantity]
    )

    class Meta:
        model = LineItem
        fields = ["id", "description", "quantity", "unit_price", "amount"]


class InvoiceSerializer(serializers.ModelSerializer):
    lines = LineItemSerializer(many=True, read_only=True)
    total = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True
    )

    class Meta:
        model = Invoice
        fields = [
            "id", "number", "status", "customer", "issued_at",
            "due_at", "notes", "lines", "total",
        ]
        read_only_fields = ["number", "status", "issued_at"]


class InvoiceCreateSerializer(serializers.Serializer):
    customer = serializers.IntegerField()
    due_at = serializers.DateTimeField(required=False, allow_null=True)
    lines = LineItemSerializer(many=True)

    def validate_lines(self, value):
        if not value:
            raise serializers.ValidationError("an invoice needs at least one line")
        for line in value:
            if line["unit_price"] < 0:
                raise serializers.ValidationError("unit price cannot be negative")
        return value

    def validate_customer(self, value):
        if value <= 0:
            raise serializers.ValidationError("invalid customer id")
        return value


class InvoiceSummarySerializer(serializers.ModelSerializer):
    balance = serializers.DecimalField(
        max_digits=14, decimal_places=2, source="balance", read_only=True
    )
    paid = serializers.DecimalField(
        max_digits=14, decimal_places=2, source="amount_paid", read_only=True
    )
    line_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Invoice
        fields = ["id", "number", "status", "total", "paid", "balance", "line_count"]


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ["id", "amount", "reference", "received_at"]
        read_only_fields = ["received_at"]
