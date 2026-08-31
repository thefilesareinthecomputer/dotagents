"""Project settings. Dotted-string values wire the executable graph."""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = "fixture-not-a-secret"
DEBUG = True
ALLOWED_HOSTS = ["*"]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "rest_framework",
    "core",
]

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "core.permissions.IsOrgMember",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
}

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "core.middleware.TenantMiddleware",
]

AUTH_USER_MODEL = "core.User"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "app",
        "USER": "app",
        "PASSWORD": "app",
        "HOST": "db",
        "PORT": "5432",
    }
}

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {},
    }
]

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": "redis://cache:6379",
    }
}
