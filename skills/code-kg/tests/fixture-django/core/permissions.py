"""DRF permission classes enforcing org isolation and billing-admin gates."""
from rest_framework.permissions import BasePermission, SAFE_METHODS


class IsOrgMember(BasePermission):
    """Only authenticated users may touch org-scoped resources."""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        org_id = getattr(obj, "org_id", None)
        return org_id == getattr(request.user, "org_id", None)


class IsBillingAdminOrReadOnly(BasePermission):
    """Mutations require a billing admin; reads are open to org members."""

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return bool(request.user and request.user.is_authenticated)
        return bool(request.user and getattr(request.user, "is_billing_admin", False))
