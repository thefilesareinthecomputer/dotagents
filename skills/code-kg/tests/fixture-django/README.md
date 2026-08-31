# Invoicing backend

A Django 5 plus DRF backend for a small invoicing SaaS. The `core` app owns the
billing domain; `config` holds settings, routing and the WSGI/ASGI entry points.

## Layout

- `core/models.py` - Org, User, Customer, Invoice, LineItem, Payment.
- `core/serializers.py` - DRF serializers for the API surface.
- `core/api/` - viewsets and the router mounted under `/api/`.
- `core/services/` - write-side operations: billing, notifications, pdf.
- `core/selectors.py` - read-side query helpers.
- `core/tasks.py` - background jobs run by the `runworker` command.
- `core/permissions.py` - org-isolation and billing-admin gates.

## Running

```
docker compose up --build
python3 manage.py migrate
python3 manage.py seed
python3 manage.py runworker --org demo
```

Tests live under `core/tests/` and run with `python3 manage.py test core`.
