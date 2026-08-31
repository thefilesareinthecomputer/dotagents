"""API router wiring the billing viewsets under /api/."""
from rest_framework.routers import DefaultRouter

from core.api.views import CustomerViewSet, InvoiceViewSet, OrgViewSet

router = DefaultRouter()
router.register("orgs", OrgViewSet, basename="org")
router.register("customers", CustomerViewSet, basename="customer")
router.register("invoices", InvoiceViewSet, basename="invoice")

urlpatterns = router.urls
