from django.contrib import admin
from django.urls import path, include
from django.http import HttpResponse

def ok(_):
    return HttpResponse("OK")

def success(_):
    return HttpResponse("Payment success.")

def cancel(_):
    return HttpResponse("Payment canceled.")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("catalog.urls")),
    path("healthz/", ok, name="healthz"),
    path("success/", success, name="success"),
    path("cancel/", cancel, name="cancel"),
]