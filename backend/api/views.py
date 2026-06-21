"""API views.

- health: liveness + config sanity for the dashboard status strip.
- RunViewSet: submit a config + codebase (POST) and read back the parsed,
  secret-masked inventory with usage sites (GET list/detail).
"""

from django.conf import settings
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.response import Response

from .models import Finding, Run
from .serializers import (
    FindingSerializer,
    FixApproveSerializer,
    RunCreateSerializer,
    RunDetailSerializer,
    RunSerializer,
)
from .services.fixer import apply_fix, undo_fix
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

    def retrieve(self, request, *args, **kwargs):
        run = self.get_object()
        return Response(RunDetailSerializer(run).data)

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
        return Response(RunDetailSerializer(run).data)

    @action(detail=True, methods=["post"])
    def probe(self, request, pk=None):
        """Probe every probeable key (read-only) and classify intent vs reality."""
        run = self.get_object()
        run_probes(run)
        run.refresh_from_db()
        return Response(RunDetailSerializer(run).data)


class FindingViewSet(viewsets.GenericViewSet):
    """Human-in-the-loop actions on a finding: approve a fix, or undo it."""

    queryset = Finding.objects.select_related("config_key", "run")
    serializer_class = FindingSerializer

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        """Apply a human-approved corrected value, then re-probe to confirm green."""
        finding = self.get_object()
        payload = FixApproveSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        finding = apply_fix(finding, payload.validated_data["corrected_value"])
        return Response(FindingSerializer(finding).data)

    @action(detail=True, methods=["post"])
    def undo(self, request, pk=None):
        """Revert the most recent applied fix on this finding and re-probe."""
        finding = self.get_object()
        fix = finding.fixes.filter(undone=False).order_by("-created_at").first()
        if fix is None:
            return Response(
                {"detail": "no applied fix to undo"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        finding = undo_fix(fix)
        return Response(FindingSerializer(finding).data)
