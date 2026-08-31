"""Outbound notifications: render and deliver messages for billing events."""
from django.core.mail import send_mail
from django.template.loader import render_to_string

from core.services.pdf import render_invoice_pdf

DEFAULT_FROM = "billing@example.test"


def notify_invoice_sent(invoice):
    body = render_to_string("emails/invoice_sent.html", {"invoice": invoice})
    attachment = render_invoice_pdf(invoice)
    _deliver(
        subject=f"Invoice {invoice.number}",
        body=body,
        recipient=invoice.customer.contact,
        attachment=attachment,
    )


def notify_payment_received(payment):
    body = render_to_string(
        "emails/payment_received.html",
        {"payment": payment, "invoice": payment.invoice},
    )
    _deliver(
        subject=f"Payment received for {payment.invoice.number}",
        body=body,
        recipient=payment.invoice.customer.contact,
        attachment=None,
    )


def _deliver(*, subject, body, recipient, attachment=None):
    send_mail(
        subject,
        body,
        DEFAULT_FROM,
        [recipient],
        html_message=body,
        fail_silently=False,
    )
    return True
