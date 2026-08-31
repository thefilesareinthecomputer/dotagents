"""Admin registrations."""
from django.contrib import admin

from core.models import Customer, Invoice, LineItem, Org, Payment, User


class LineItemInline(admin.TabularInline):
    model = LineItem
    extra = 1


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("number", "org", "customer", "status", "issued_at")
    list_filter = ("status",)
    search_fields = ("number",)
    inlines = [LineItemInline]


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("name", "org", "contact", "is_archived")
    search_fields = ("name", "contact")


admin.site.register(Org)
admin.site.register(User)
admin.site.register(Payment)
