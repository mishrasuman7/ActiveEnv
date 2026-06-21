"""URL routes for the api app."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r"runs", views.RunViewSet, basename="run")

urlpatterns = [
    path("health/", views.health, name="health"),
    path("", include(router.urls)),
]
