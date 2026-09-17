"""Fixture: the DRF footguns that actually ship. Every block trips a rule.
Used by tests/test_django_check.py. Do not "fix" this file.
"""

from django.db import connection
from rest_framework import serializers, viewsets

from .models import User

SECRET_KEY = "django-insecure-8f3k2j4h5g6f7d8s9a0"
DEBUG = True
ALLOWED_HOSTS = ["*"]
CORS_ALLOW_ALL_ORIGINS = True

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
}


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = "__all__"
        depth = 2


class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email", "is_staff", "password"]


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer


def search(term):
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT * FROM users WHERE name = '{term}'")
        return cursor.fetchall()
