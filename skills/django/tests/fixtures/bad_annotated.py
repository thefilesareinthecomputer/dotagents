"""Fixture: annotated settings must NOT bypass the rules (review finding).
Every one of these is type-annotated - the old visit_Assign-only checker saw none.
"""

from typing import Any

SECRET_KEY: str = "django-insecure-annotated-bypass"
ALLOWED_HOSTS: list[str] = ["*"]
CORS_ORIGIN_ALLOW_ALL: bool = True          # the legacy alias, also caught
REST_FRAMEWORK: dict[str, Any] = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
}
