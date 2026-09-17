"""Fixture: the legitimate write_only password pattern must lint CLEAN (review finding).
The old rule FAILed any writable `password`; that mutes the tool on the single
most common correct registration serializer.
"""

from rest_framework import serializers

from .models import User


class RegistrationSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email", "password"]
        read_only_fields = ["id"]
        extra_kwargs = {"password": {"write_only": True}}


class ChangePasswordSerializer(serializers.ModelSerializer):
    # declared on the body, also write_only
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ["id", "password"]
        read_only_fields = ["id"]
