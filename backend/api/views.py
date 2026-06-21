"""API views.

For Phase 0 this is just a health check that confirms the service is up and
reports whether the Qwen key is configured (without ever exposing it).
"""

from django.conf import settings
from rest_framework.decorators import api_view
from rest_framework.response import Response


@api_view(["GET"])
def health(_request):
    """Liveness probe + config sanity for the dashboard's status strip."""
    return Response(
        {
            "service": "activeenv-api",
            "status": "ok",
            "qwen_configured": bool(settings.QWEN_API_KEY),
            "qwen_model": settings.QWEN_MODEL,
        }
    )
