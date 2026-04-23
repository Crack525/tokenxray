"""Tests for display formatting helpers."""

from datetime import datetime, timezone

from tokenxray.display import fmt_tokens, fmt_cost, bar, duration_str, display_project_name, display_models


class TestFmtTokens:
    def test_millions(self):
        assert fmt_tokens(1_500_000) == "1.5M"

    def test_thousands(self):
        assert fmt_tokens(42_000) == "42.0K"

    def test_small(self):
        assert fmt_tokens(500) == "500"

    def test_zero(self):
        assert fmt_tokens(0) == "0"


class TestFmtCost:
    def test_large(self):
        assert fmt_cost(150.5) == "$150"

    def test_medium(self):
        assert fmt_cost(12.345) == "$12.35"

    def test_small(self):
        assert fmt_cost(0.123) == "$0.123"

    def test_zero(self):
        assert fmt_cost(0) == "$0.000"


class TestBar:
    def test_full(self):
        result = bar(100, 100, 10)
        assert result == "\u2588" * 10

    def test_empty(self):
        result = bar(0, 100, 10)
        assert result == "\u2591" * 10

    def test_half(self):
        result = bar(50, 100, 10)
        assert "\u2588" in result
        assert "\u2591" in result
        assert len(result) == 10

    def test_zero_max(self):
        result = bar(50, 0, 10)
        assert result == "\u2591" * 10


class TestDurationStr:
    def test_hours(self):
        start = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 1, 1, 2, 30, tzinfo=timezone.utc)
        assert duration_str(start, end) == "2.5hrs"

    def test_minutes(self):
        start = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 1, 1, 0, 45, tzinfo=timezone.utc)
        assert duration_str(start, end) == "45min"

    def test_none(self):
        assert duration_str(None, None) == "unknown"
        assert duration_str(datetime.now(), None) == "unknown"


class TestDisplayProjectName:
    def test_claude_slug_after_documents(self):
        project = "-Users-mdniajul-hasan-Documents-DS-WORKSPACE-implant-planning"
        assert display_project_name(project) == "DS/WORKSPACE/implant/planning"

    def test_truncates_when_max_len_set(self):
        project = "-Users-mdniajul-hasan-Documents-DS-WORKSPACE-very-long-project-name"
        display = display_project_name(project, 20)
        assert display.startswith("...")
        assert len(display) == 20


class TestDisplayModels:
    def test_skips_synthetic_and_formats_label(self):
        models = ["<synthetic>", "claude-opus-4-6"]
        assert display_models(models) == "Opus 4.6"

    def test_multiple_models_are_deduplicated_and_sorted(self):
        models = ["claude-sonnet-4-6", "claude-opus-4-6", "claude-sonnet-4-6"]
        assert display_models(models) == "Opus 4.6, Sonnet 4.6"
