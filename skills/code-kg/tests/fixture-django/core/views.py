"""Request handlers."""
from django.shortcuts import render

from core.models import Org, User


def welcome(request):
    return render(request, "emails/welcome.html", {"user_count": User.objects.count()})


def org_list(request):
    return render(request, "emails/welcome.html", {"orgs": Org.objects.all()})
