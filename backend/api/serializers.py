"""DRF serializers for the run inventory API."""

from rest_framework import serializers

from .models import ConfigKey, Run, UsageSite


class UsageSiteSerializer(serializers.ModelSerializer):
    class Meta:
        model = UsageSite
        fields = ["file_path", "line_number", "usage_kind", "snippet"]


class ConfigKeySerializer(serializers.ModelSerializer):
    usage_sites = UsageSiteSerializer(many=True, read_only=True)
    usage_count = serializers.IntegerField(source="usage_sites.count", read_only=True)

    class Meta:
        model = ConfigKey
        fields = [
            "id",
            "name",
            "masked_value",
            "value_hint",
            "kind",
            "is_secret",
            "is_probeable",
            "usage_count",
            "usage_sites",
        ]


class RunSerializer(serializers.ModelSerializer):
    keys = ConfigKeySerializer(many=True, read_only=True)
    key_count = serializers.IntegerField(source="keys.count", read_only=True)

    class Meta:
        model = Run
        fields = [
            "id",
            "created_at",
            "updated_at",
            "status",
            "source_type",
            "target_environment",
            "config_format",
            "key_count",
            "keys",
        ]


class RunCreateSerializer(serializers.Serializer):
    """Input for submitting a new run."""

    config_text = serializers.CharField(trim_whitespace=False)
    config_format = serializers.CharField(required=False, allow_blank=True, default="")
    config_filename = serializers.CharField(required=False, allow_blank=True, default="")
    target_environment = serializers.CharField(required=False, default="production")
    source_type = serializers.ChoiceField(
        choices=Run.SourceType.choices, required=False, default=Run.SourceType.PASTE
    )
    # Codebase as a {relative_path: file_text} map.
    files = serializers.DictField(
        child=serializers.CharField(allow_blank=True, trim_whitespace=False),
        required=False,
        default=dict,
    )
