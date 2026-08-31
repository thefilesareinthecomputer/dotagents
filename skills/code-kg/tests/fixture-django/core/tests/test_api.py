"""Integration tests for the DRF viewsets."""
from django.test import TestCase
from rest_framework.test import APIClient

from core.tests.factories import make_customer, make_org, make_user


class InvoiceApiTests(TestCase):
    def setUp(self):
        self.org = make_org()
        self.admin = make_user(self.org, username="boss", billing_admin=True)
        self.customer = make_customer(self.org)
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def test_create_invoice_via_api(self):
        response = self.client.post(
            "/api/invoices/",
            {
                "customer": self.customer.id,
                "lines": [{"description": "Job", "unit_price": "10.00", "quantity": "1"}],
            },
            format="json",
        )
        self.assertIn(response.status_code, (200, 201))

    def test_non_admin_cannot_create(self):
        member = make_user(self.org, username="member")
        self.client.force_authenticate(member)
        response = self.client.post("/api/invoices/", {}, format="json")
        self.assertEqual(response.status_code, 403)


class PermissionTests(TestCase):
    def test_anonymous_denied(self):
        client = APIClient()
        response = client.get("/api/customers/")
        self.assertIn(response.status_code, (401, 403))
