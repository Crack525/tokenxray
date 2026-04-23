"""Tests for session parsing and cost calculation."""

import json
import os
import tempfile
from pathlib import Path

import pytest

from tokenxray.parser import (
    parse_session,
    parse_gemini_session,
    parse_copilot_session,
    calc_cost,
    _pick_model,
)
from tokenxray.config import get_pricing, get_model_label


# ─── Fixtures ────────────────────────────────────────────────────────────────


def _write_jsonl(path, entries):
    with open(path, "w") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")


def _make_claude_session(tmpdir, model="claude-opus-4-6", turns=3):
    """Create a minimal Claude Code JSONL session file."""
    entries = []
    for i in range(turns):
        entries.append({
            "type": "user",
            "timestamp": f"2026-01-01T00:{i:02d}:00Z",
            "message": {"content": f"Question {i}" * 10},
        })
        entries.append({
            "type": "assistant",
            "timestamp": f"2026-01-01T00:{i:02d}:30Z",
            "message": {
                "model": model,
                "usage": {
                    "input_tokens": 1000 * (i + 1),
                    "output_tokens": 200,
                    "cache_read_input_tokens": 500 * i,
                    "cache_creation_input_tokens": 300,
                },
                "content": [
                    {"type": "text", "text": "Response " * 50},
                ],
            },
        })
    filepath = os.path.join(tmpdir, "test-session.jsonl")
    _write_jsonl(filepath, entries)
    return filepath


def _make_gemini_session(tmpdir, model="gemini-2.5-pro", turns=3):
    """Create a minimal Gemini CLI session JSON file."""
    messages = []
    for i in range(turns):
        messages.append({
            "id": f"user-{i}",
            "timestamp": f"2026-01-01T00:{i:02d}:00Z",
            "type": "user",
            "content": f"Question {i}" * 10,
        })
        messages.append({
            "id": f"gemini-{i}",
            "timestamp": f"2026-01-01T00:{i:02d}:30Z",
            "type": "gemini",
            "content": "Response " * 50,
            "model": model,
            "tokens": {
                "input": 2000 * (i + 1),
                "output": 150,
                "cached": 800 * i,
                "thoughts": 50,
                "tool": 0,
                "total": 2000 * (i + 1) + 150 + 50,
            },
        })
    data = {
        "sessionId": "test-gemini-session-id",
        "projectHash": "abc123def456",
        "startTime": "2026-01-01T00:00:00Z",
        "lastUpdated": "2026-01-01T00:10:00Z",
        "messages": messages,
    }
    filepath = os.path.join(tmpdir, "session-test.json")
    with open(filepath, "w") as f:
        json.dump(data, f)
    return filepath


def _make_copilot_session(tmpdir, turns=2):
    """Create a minimal Copilot transcript JSONL file."""
    entries = [
        {
            "type": "session.start",
            "data": {"sessionId": "test-copilot-id", "producer": "copilot-agent"},
            "id": "start-1",
            "timestamp": "2026-01-01T00:00:00Z",
            "parentId": None,
        },
    ]
    for i in range(turns):
        entries.extend([
            {
                "type": "user.message",
                "data": {"content": "Hello world " * 20},
                "id": f"user-{i}",
                "timestamp": f"2026-01-01T00:{i:02d}:10Z",
                "parentId": None,
            },
            {
                "type": "assistant.turn_start",
                "data": {"turnId": f"{i}.0"},
                "id": f"turn-start-{i}",
                "timestamp": f"2026-01-01T00:{i:02d}:15Z",
                "parentId": f"user-{i}",
            },
            {
                "type": "assistant.message",
                "data": {"messageId": f"msg-{i}", "content": "Here is the answer " * 30},
                "id": f"msg-{i}",
                "timestamp": f"2026-01-01T00:{i:02d}:20Z",
                "parentId": f"turn-start-{i}",
            },
            {
                "type": "assistant.turn_end",
                "data": {"turnId": f"{i}.0"},
                "id": f"turn-end-{i}",
                "timestamp": f"2026-01-01T00:{i:02d}:25Z",
                "parentId": f"msg-{i}",
            },
        ])
    filepath = os.path.join(tmpdir, "test-copilot.jsonl")
    _write_jsonl(filepath, entries)
    return filepath


# ─── Claude parser tests ─────────────────────────────────────────────────────


class TestClaudeParser:
    def test_parse_session_basic(self, tmp_path):
        filepath = _make_claude_session(str(tmp_path))
        s = parse_session(filepath)

        assert len(s["turns"]) == 3
        assert s["models_used"] == ["claude-opus-4-6"]
        assert s["total_output"] == 600  # 200 * 3
        assert s["total_cache_create"] == 900  # 300 * 3
        assert s["start_time"] is not None
        assert s["end_time"] is not None

    def test_parse_session_token_accumulation(self, tmp_path):
        filepath = _make_claude_session(str(tmp_path))
        s = parse_session(filepath)

        # Turn 1: input=1000, cache_read=0, Turn 2: input=2000, cache_read=500
        assert s["total_input"] == 1000 + 2000 + 3000  # 6000
        assert s["total_cache_read"] == 0 + 500 + 1000  # 1500

    def test_parse_empty_file(self, tmp_path):
        filepath = os.path.join(str(tmp_path), "empty.jsonl")
        with open(filepath, "w") as f:
            f.write("")
        s = parse_session(filepath)
        assert len(s["turns"]) == 0

    def test_parse_malformed_json(self, tmp_path):
        filepath = os.path.join(str(tmp_path), "bad.jsonl")
        with open(filepath, "w") as f:
            f.write("not json\n")
            f.write('{"type": "user", "message": {"content": "ok"}}\n')
        s = parse_session(filepath)
        # Should skip bad line, parse good line
        assert len(s["user_messages"]) == 0  # "ok" is too short (<10 chars)

    def test_user_messages_filtered_by_length(self, tmp_path):
        entries = [
            {"type": "user", "message": {"content": "short"}},  # < 10, skip
            {"type": "user", "message": {"content": "x" * 100}},  # ok
            {"type": "user", "message": {"content": "x" * 6000}},  # > 5000, skip
        ]
        filepath = os.path.join(str(tmp_path), "test.jsonl")
        _write_jsonl(filepath, entries)
        s = parse_session(filepath)
        assert len(s["user_messages"]) == 1
        assert s["user_messages"][0] == 100

    def test_tool_calls_counted(self, tmp_path):
        entries = [
            {
                "type": "assistant",
                "message": {
                    "model": "claude-opus-4-6",
                    "usage": {"input_tokens": 100, "output_tokens": 50,
                              "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
                    "content": [
                        {"type": "tool_use", "name": "Read"},
                        {"type": "tool_use", "name": "Read"},
                        {"type": "tool_use", "name": "Bash"},
                    ],
                },
            },
        ]
        filepath = os.path.join(str(tmp_path), "test.jsonl")
        _write_jsonl(filepath, entries)
        s = parse_session(filepath)
        assert s["tool_calls"]["Read"] == 2
        assert s["tool_calls"]["Bash"] == 1


# ─── Cost calculation tests ─────────────────────────────────────────────────


class TestCalcCost:
    def test_opus_pricing(self, tmp_path):
        filepath = _make_claude_session(str(tmp_path), model="claude-opus-4-6", turns=1)
        s = parse_session(filepath)
        cost = calc_cost(s)

        # Turn 1: input=1000, output=200, cache_read=0, cache_create=300
        pricing = get_pricing("claude-opus-4-6")
        expected_input = (1000 / 1e6) * pricing["input"]
        expected_output = (200 / 1e6) * pricing["output"]
        expected_cc = (300 / 1e6) * pricing["cache_create"]

        assert abs(cost["input"] - expected_input) < 0.0001
        assert abs(cost["output"] - expected_output) < 0.0001
        assert abs(cost["cache_create"] - expected_cc) < 0.0001
        assert cost["total"] > 0
        # 1-turn session with cache_create but no cache_read: savings can be negative
        assert cost["total_no_cache"] is not None

    def test_cache_savings_positive(self, tmp_path):
        filepath = _make_claude_session(str(tmp_path), turns=5)
        s = parse_session(filepath)
        cost = calc_cost(s)
        # With cache reads, total should be less than no-cache
        assert cost["total_no_cache"] >= cost["total"]
        assert cost["cache_savings"] >= 0

    def test_gemini_no_cache_create(self, tmp_path):
        filepath = _make_gemini_session(str(tmp_path))
        s = parse_gemini_session(filepath)
        cost = calc_cost(s)
        assert cost["cache_create"] == 0

    def test_zero_token_session(self, tmp_path):
        filepath = os.path.join(str(tmp_path), "zero.jsonl")
        _write_jsonl(filepath, [])
        s = parse_session(filepath)
        s["models_used"] = ["claude-opus-4-6"]
        cost = calc_cost(s)
        assert cost["total"] == 0


# ─── Model selection tests ───────────────────────────────────────────────────


class TestPickModel:
    def test_skips_synthetic(self):
        assert _pick_model(["<synthetic>", "claude-opus-4-6"]) == "claude-opus-4-6"

    def test_pure_synthetic_defaults_opus(self):
        assert _pick_model(["<synthetic>"]) == "claude-opus-4-6"

    def test_real_model_first(self):
        assert _pick_model(["claude-sonnet-4-6"]) == "claude-sonnet-4-6"

    def test_empty_defaults_opus(self):
        assert _pick_model([]) == "claude-opus-4-6"


# ─── Pricing tests ───────────────────────────────────────────────────────────


class TestPricing:
    def test_exact_match(self):
        p = get_pricing("claude-opus-4-6")
        assert p["input"] == 5.0
        assert p["output"] == 25.0

    def test_prefix_match(self):
        p = get_pricing("claude-sonnet-4-5-20250514")
        assert p["label"] == "Sonnet 4.5"

    def test_gemini_match(self):
        p = get_pricing("gemini-2.5-pro")
        assert p["input"] == 1.25

    def test_unknown_model_defaults(self):
        p = get_pricing("some-unknown-model")
        assert p["label"] == "Unknown (Sonnet pricing)"

    def test_model_label(self):
        assert get_model_label("claude-opus-4-6") == "Opus 4.6"
        assert get_model_label("gemini-2.5-flash") == "Gemini 2.5 Flash"
        assert get_model_label("copilot-agent") == "Copilot"


# ─── Gemini parser tests ─────────────────────────────────────────────────────


class TestGeminiParser:
    def test_parse_basic(self, tmp_path):
        filepath = _make_gemini_session(str(tmp_path))
        s = parse_gemini_session(filepath)

        assert s["source"] == "gemini"
        assert len(s["turns"]) == 3
        assert s["models_used"] == ["gemini-2.5-pro"]
        assert s["full_id"] == "test-gemini-session-id"

    def test_token_mapping(self, tmp_path):
        filepath = _make_gemini_session(str(tmp_path), turns=1)
        s = parse_gemini_session(filepath)

        # Turn 1: input=2000, cached=0, output=150, thoughts=50
        assert s["total_input"] == 2000  # fresh = input - cached
        assert s["total_cache_read"] == 0
        assert s["total_output"] == 200  # output + thoughts
        assert s["total_cache_create"] == 0  # Gemini has no cache create

    def test_cached_tokens_separated(self, tmp_path):
        filepath = _make_gemini_session(str(tmp_path), turns=3)
        s = parse_gemini_session(filepath)

        # Turn 2: input=4000, cached=800 → fresh=3200
        # Turn 3: input=6000, cached=1600 → fresh=4400
        assert s["total_cache_read"] == 0 + 800 + 1600  # 2400

    def test_project_from_hash(self, tmp_path):
        filepath = _make_gemini_session(str(tmp_path))
        s = parse_gemini_session(filepath)
        assert s["project"].startswith("gemini/")


# ─── Copilot parser tests ────────────────────────────────────────────────────


class TestCopilotParser:
    def test_parse_basic(self, tmp_path):
        filepath = _make_copilot_session(str(tmp_path))
        s = parse_copilot_session(filepath)

        assert s["source"] == "copilot"
        assert len(s["turns"]) == 2
        assert "copilot-agent" in s["models_used"]

    def test_token_estimation(self, tmp_path):
        filepath = _make_copilot_session(str(tmp_path), turns=1)
        s = parse_copilot_session(filepath)

        # "Hello world " * 20 = 240 chars → ~60 tokens input
        # "Here is the answer " * 30 = 570 chars → ~142 tokens output
        assert s["total_input"] > 0
        assert s["total_output"] > 0
        assert s["total_cache_read"] == 0
        assert s["total_cache_create"] == 0

    def test_project_from_path(self, tmp_path):
        filepath = _make_copilot_session(str(tmp_path))
        s = parse_copilot_session(filepath)
        assert s["project"].startswith("copilot/")


# ─── Mixed-model pricing regression ──────────────────────────────────────────


class TestMixedModelPricing:
    """Regression tests for non-deterministic cost in mixed-model sessions.

    Root cause: models_used was a set converted to list; _pick_model took
    real[0], which was hash-ordered, so Opus vs Sonnet flipped across runs
    (5x cost difference). Fix: price per-turn using each turn's own model.
    """

    def _make_mixed_session(self, tmp_path):
        """Session with 2 Sonnet turns then 2 Opus turns."""
        entries = []
        for i, (model, inp, out) in enumerate([
            ("claude-sonnet-4-6", 1000, 200),
            ("claude-sonnet-4-6", 1000, 200),
            ("claude-opus-4-6",   1000, 200),
            ("claude-opus-4-6",   1000, 200),
        ]):
            entries.append({
                "type": "user",
                "timestamp": f"2026-01-01T00:{i:02d}:00Z",
                "message": {"content": "x" * 50},
            })
            entries.append({
                "type": "assistant",
                "timestamp": f"2026-01-01T00:{i:02d}:30Z",
                "message": {
                    "model": model,
                    "usage": {"input_tokens": inp, "output_tokens": out,
                               "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
                    "content": [{"type": "text", "text": "answer"}],
                },
            })
        path = str(tmp_path / "mixed.jsonl")
        _write_jsonl(path, entries)
        return path

    def test_mixed_model_cost_is_deterministic(self, tmp_path):
        path = self._make_mixed_session(tmp_path)
        costs = [calc_cost(parse_session(path))["total"] for _ in range(10)]
        assert len(set(round(c, 8) for c in costs)) == 1, (
            f"Cost non-deterministic across runs: {set(costs)}"
        )

    def test_mixed_model_cost_is_accurate(self, tmp_path):
        from tokenxray.config import get_pricing
        path = self._make_mixed_session(tmp_path)
        cost = calc_cost(parse_session(path))["total"]

        sonnet = get_pricing("claude-sonnet-4-6")
        opus = get_pricing("claude-opus-4-6")
        expected = (
            2 * ((1000 / 1e6) * sonnet["input"] + (200 / 1e6) * sonnet["output"])
            + 2 * ((1000 / 1e6) * opus["input"] + (200 / 1e6) * opus["output"])
        )
        assert abs(cost - expected) < 1e-9, (
            f"Expected {expected:.8f}, got {cost:.8f}"
        )

    def test_single_model_session_unchanged(self, tmp_path):
        """Single-model sessions should produce the same cost as before."""
        path = str(tmp_path / "single.jsonl")
        entries = []
        for i in range(3):
            entries.append({
                "type": "user",
                "timestamp": f"2026-01-01T00:{i:02d}:00Z",
                "message": {"content": "x" * 50},
            })
            entries.append({
                "type": "assistant",
                "timestamp": f"2026-01-01T00:{i:02d}:30Z",
                "message": {
                    "model": "claude-sonnet-4-6",
                    "usage": {"input_tokens": 500, "output_tokens": 100,
                               "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
                    "content": [{"type": "text", "text": "ok"}],
                },
            })
        _write_jsonl(path, entries)
        s = parse_session(path)
        cost = calc_cost(s)["total"]

        pricing = get_pricing("claude-sonnet-4-6")
        expected = 3 * ((500 / 1e6) * pricing["input"] + (100 / 1e6) * pricing["output"])
        assert abs(cost - expected) < 1e-9
