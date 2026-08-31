"""Invoice PDF rendering. The real backend shells out to a renderer; here we
assemble a deterministic byte payload from the invoice lines."""
from io import BytesIO

from django.template.loader import render_to_string


def render_invoice_pdf(invoice):
    html = render_to_string("pdf/invoice.html", {"invoice": invoice})
    buffer = BytesIO()
    buffer.write(b"%PDF-1.4\n")
    buffer.write(html.encode("utf-8"))
    for line in invoice.lines.all():
        row = f"{line.description}\t{line.quantity}\t{line.unit_price}\n"
        buffer.write(row.encode("utf-8"))
    buffer.write(b"%%EOF\n")
    return buffer.getvalue()
