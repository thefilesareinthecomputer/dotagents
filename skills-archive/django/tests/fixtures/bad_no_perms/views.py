"""Fixture (dir): DRF is used here, and NO file in this dir configures permissions.
DRF defaults to AllowAny, so this whole API is public. The run-level rule catches it.
"""

from rest_framework import viewsets

from .models import Widget
from .serializers import WidgetSerializer


class WidgetViewSet(viewsets.ModelViewSet):
    serializer_class = WidgetSerializer
    queryset = Widget.objects.select_related("owner").all()
    # No permission_classes here, and no DEFAULT_PERMISSION_CLASSES in settings.py.
