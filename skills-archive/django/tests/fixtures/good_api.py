"""Fixture: the same API, done right. Must lint clean (zero findings).
Used by tests/test_django_check.py.
"""

import os

from django.db import connection
from rest_framework import permissions, serializers, viewsets

from .models import User

SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]
DEBUG = False
ALLOWED_HOSTS = ["api.example.com"]

REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.LimitOffsetPagination",
    "PAGE_SIZE": 50,
}


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email", "display_name", "is_staff", "created_at"]
        read_only_fields = ["id", "is_staff", "created_at"]


class UserViewSet(viewsets.ModelViewSet):
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = User.objects.select_related("organization").all()


def search(term):
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM users WHERE name = %s", [term])
        return cursor.fetchall()
