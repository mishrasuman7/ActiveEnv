"""API views.

- health: liveness + config sanity for the dashboard status strip.
- RunViewSet: submit a config + codebase (POST) and read back the parsed,
  secret-masked inventory with usage sites (GET list/detail).
"""

from django.conf import settings
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.response import Response

from .models import Run
from .serializers import RunCreateSerializer, RunSerializer
from .services.ingest import ingest_run
from .services.intent import infer_run_intents
from .services.orchestrator import run_probes
from .services.qwen_client import QwenNotConfigured


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

    @action(detail=True, methods=["post"])
    def infer(self, request, pk=None):
        """Run Qwen intent inference over every key on this run."""
        run = self.get_object()
        try:
            infer_run_intents(run)
        except QwenNotConfigured as exc:
            return Response(
                {"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        run.refresh_from_db()
        return Response(RunSerializer(run).data)

    @action(detail=True, methods=["post"])
    def probe(self, request, pk=None):
        """Probe every probeable key (read-only) and classify intent vs reality."""
        run = self.get_object()
        run_probes(run)
        run.refresh_from_db()
        return Response(RunSerializer(run).data)
