"""URL routing."""
from django.contrib import admin
from django.urls import include, path

from core.views import welcome, org_list

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", welcome, name="welcome"),
    path("orgs/", org_list, name="org-list"),
    path("api/", include("core.api.urls")),
]
