"""Fixture (dir): the settings file - note there is NO REST_FRAMEWORK block at all.
That absence is the footgun: DRF falls back to AllowAny globally.
"""

import os

SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]
DEBUG = False
ALLOWED_HOSTS = ["api.example.com"]

INSTALLED_APPS = ["rest_framework", "apps.widgets"]
