"""DRF viewsets. This module is the API hub: it wires serializers,
permissions, the service layer and selectors into HTTP handlers."""
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from core.models import Customer, Invoice, Org
from core.permissions import IsBillingAdminOrReadOnly, IsOrgMember
from core.selectors import outstanding_invoices, revenue_by_customer
from core.serializers import (
    CustomerSerializer,
    InvoiceCreateSerializer,
    InvoiceSerializer,
    InvoiceSummarySerializer,
    OrgSerializer,
    PaymentSerializer,
)
from core.services.billing import create_invoice, record_payment, send_invoice
from core.services.reports import collection_summary, top_customers


class OrgViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OrgSerializer
    permission_classes = [IsOrgMember]

    def get_queryset(self):
        return Org.objects.filter(pk=self.request.user.org_id)

    @action(detail=True, methods=["get"])
    def revenue(self, request, pk=None):
        rows = revenue_by_customer(self.get_object())
        data = [{"customer": r.name, "invoiced": r.invoiced} for r in rows]
        return Response(data)

    @action(detail=True, methods=["get"])
    def summary(self, request, pk=None):
        org = self.get_object()
        payload = collection_summary(org)
        payload["top_customers"] = top_customers(org)
        return Response(payload)


class CustomerViewSet(viewsets.ModelViewSet):
    serializer_class = CustomerSerializer
    permission_classes = [IsOrgMember]

    def get_queryset(self):
        return Customer.objects.filter(org_id=self.request.user.org_id)

    def perform_create(self, serializer):
        serializer.save(org_id=self.request.user.org_id)


class InvoiceViewSet(viewsets.ModelViewSet):
    permission_classes = [IsBillingAdminOrReadOnly]

    def get_queryset(self):
        return Invoice.objects.filter(org_id=self.request.user.org_id)

    def get_serializer_class(self):
        if self.action == "create":
            return InvoiceCreateSerializer
        return InvoiceSerializer

    def perform_create(self, serializer):
        org = self.request.user.org
        customer = Customer.objects.get(
            pk=serializer.validated_data["customer"], org=org
        )
        self.instance = create_invoice(
            org=org,
            customer=customer,
            lines=serializer.validated_data["lines"],
            due_at=serializer.validated_data.get("due_at"),
        )

    @action(detail=True, methods=["post"])
    def send(self, request, pk=None):
        invoice = send_invoice(self.get_object())
        return Response(InvoiceSerializer(invoice).data)

    @action(detail=True, methods=["get"])
    def outstanding(self, request, pk=None):
        rows = outstanding_invoices(self.request.user.org)
        return Response(InvoiceSerializer(rows, many=True).data)

    @action(detail=True, methods=["get"])
    def digest(self, request, pk=None):
        invoice = self.get_object()
        return Response(InvoiceSummarySerializer(invoice).data)

    @action(detail=True, methods=["post"])
    def pay(self, request, pk=None):
        payment = record_payment(
            self.get_object(),
            amount=request.data["amount"],
            reference=request.data.get("reference", ""),
        )
        return Response(PaymentSerializer(payment).data)
