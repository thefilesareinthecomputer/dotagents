# Scaffolding a Django + DRF project

Patterns that already pass `scripts/django_check.py`. The defaults below are
chosen because Django and DRF's own defaults fail *open* or fail *slow*.

## Contents

- [Layout](#layout)
- [Settings: split, never branch](#settings-split-never-branch)
- [DRF: the config that matters](#drf-the-config-that-matters)
- [Serializers](#serializers)
- [ViewSets](#viewsets)
- [Models](#models)
- [Auth](#auth)

## Layout

```
config/                  # the project package - settings, urls, wsgi/asgi
  settings/
    base.py              # everything shared
    dev.py               # from .base import *  + local overrides
    prod.py              # from .base import *  + hardening
  urls.py
apps/
  users/
    models.py  serializers.py  views.py  urls.py  permissions.py
    tests/
  billing/
    ...
manage.py
pyproject.toml
```

One app per bounded concern, not per model. `apps/users/` holds the user model,
its serializers, its views, its permissions - a change to how users work touches
one directory.

## Settings: split, never branch

`if DEBUG:` inside one settings file is how production ends up with a dev
setting. Split the files; make the unsafe one impossible to load by accident.

```python
# config/settings/base.py
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]      # KeyError at boot beats a default
DEBUG = False                                      # the safe default; dev.py opts in
ALLOWED_HOSTS: list[str] = []

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "apps.users",
]

AUTH_USER_MODEL = "users.User"     # set this on day one; migrating later is genuinely painful
```

```python
# config/settings/prod.py
from .base import *  # noqa: F403

ALLOWED_HOSTS = os.environ["DJANGO_ALLOWED_HOSTS"].split(",")

SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31_536_000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
```

`SECRET_KEY = os.environ[...]` with **no default** is deliberate: a missing key
should crash the boot, not silently fall back to a value that is in git.

## DRF: the config that matters

**DRF's default permission is `AllowAny`.** Not "authenticated", not "denied" -
open. A view that forgets `permission_classes` is a public endpoint, with no
error and no warning. Invert that on day one:

```python
# config/settings/base.py
REST_FRAMEWORK = {
    # Default DENY. Public endpoints then opt in, visibly, one at a time.
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    # Without this, a list endpoint serializes the whole table.
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.LimitOffsetPagination",
    "PAGE_SIZE": 50,
    # AnonRateThrottle/UserRateThrottle apply GLOBALLY. (ScopedRateThrottle alone
    # does nothing until a view sets throttle_scope - see the login view below.)
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.ScopedRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {"anon": "60/min", "user": "600/min", "login": "5/min"},
}
```

The login endpoint opts into the tighter scope explicitly - that `throttle_scope`
is what activates the `"login": "5/min"` rate; without it the rate is inert:

```python
class LoginView(APIView):
    permission_classes = [permissions.AllowAny]   # login must be public
    throttle_scope = "login"                        # -> the 5/min rate applies here
```

## Serializers

```python
class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        # Enumerate. NEVER fields = "__all__".
        fields = ["id", "email", "display_name", "is_staff", "created_at"]
        # Anything privilege-bearing or server-owned is read-only, or a user
        # PATCHes themselves into staff.
        read_only_fields = ["id", "is_staff", "created_at"]
```

`fields = "__all__"` is the single worst DRF habit: it is a *promise to expose
every column you ever add*. The `internal_notes` field you add next quarter
ships to the public API the moment it exists. The linter FAILs on it.

Nested reads without the N+1 (declare the nesting, then prefetch it):

```python
class OrderSerializer(serializers.ModelSerializer):
    customer = CustomerSerializer(read_only=True)      # explicit, not Meta.depth
    items = ItemSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = ["id", "customer", "items", "total", "created_at"]
```

`Meta.depth = 2` looks like a shortcut and is a per-row query generator. Use
explicit nested serializers, and pair them with the queryset below.

## ViewSets

```python
class OrderViewSet(viewsets.ModelViewSet):
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated, IsOrderOwner]

    def get_queryset(self):
        return (
            Order.objects
            .filter(customer=self.request.user)      # scope to the caller, ALWAYS
            .select_related("customer")              # FK -> JOIN (one query)
            .prefetch_related("items")               # reverse/M2M -> second query
        )
```

Three things in that method, all load-bearing:

- **`filter(customer=self.request.user)`** - object-level scoping. A permission
  class that checks "is authenticated" does not stop user A reading user B's
  order by id. Scope the queryset, do not rely on the detail-view permission.
- **`select_related`** for forward FKs (SQL JOIN, one query).
- **`prefetch_related`** for reverse FKs and M2M (a second query, then joined in
  Python). Using the wrong one silently does nothing.

## Models

```python
class Order(models.Model):
    customer = models.ForeignKey(
        "users.User",
        on_delete=models.PROTECT,       # think about this; CASCADE deletes silently
        related_name="orders",
    )
    total = models.DecimalField(max_digits=10, decimal_places=2)   # never FloatField for money
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # An index for every field you filter or order by in a hot path.
        indexes = [models.Index(fields=["customer", "-created_at"])]
        constraints = [
            models.CheckConstraint(condition=models.Q(total__gte=0), name="total_non_negative"),
        ]
```

`on_delete` has no safe default - Django makes you choose because the choices
differ enormously. `CASCADE` on a user FK means deleting one user silently
deletes their orders. `PROTECT` refuses and makes you decide.

Money is `DecimalField`, never `FloatField`. `0.1 + 0.2 != 0.3` is not a rounding
curiosity when it is someone's invoice.

## Auth

Session auth for a browser client (and the CSRF protection comes with it). Token
or JWT for a mobile/service client - and if JWT, know that you have chosen
"cannot revoke until expiry" unless you also build a denylist.

Throttle the login endpoint specifically (`"login": "5/min"` above). The default
throttles do not cover credential stuffing, which is the attack that actually
happens.
