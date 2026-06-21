"""API views.

- health: liveness + config sanity for the dashboard status strip.
- RunViewSet: submit a config + codebase (POST) and read back the parsed,
  secret-masked inventory with usage sites (GET list/detail).
"""

from django.conf import settings
from rest_framework import viewsets
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Run
from .serializers import RunCreateSerializer, RunSerializer
from .services.ingest import ingest_run


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


class RunViewSet(viewsets.ModelViewSet):
    """List/retrieve runs and create a new one (which triggers ingestion)."""

    queryset = Run.objects.prefetch_related("keys__usage_sites")
    serializer_class = RunSerializer
    http_method_names = ["get", "post"]

    def create(self, request, *args, **kwargs):
        payload = RunCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data

        run = Run.objects.create(
            source_type=data["source_type"],
            target_environment=data["target_environment"],
        )
        ingest_run(
            run,
            config_text=data["config_text"],
            files=data["files"],
            config_format=data["config_format"],
            config_filename=data["config_filename"],
        )
        run.refresh_from_db()
        return Response(RunSerializer(run).data, status=201)
