"""Tests for the subagent hook (PreToolUse on Agent calls)."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from tokenxray.commands.hook import SUBAGENT_HOOK_CODE

SESSION_ID = "test-subagent-00000000"


def _state(session_id=SESSION_ID, turns=10, total_cost=1.20, model="Sonnet", extra=None):
    s = {
        "session_id": session_id,
        "turns": turns,
        "total_cost": total_cost,
        "model": model,
        "alerts": [],
    }
    if extra:
        s.update(extra)
    return s


def _run_hook(tmp_path, payload, state=None, config=None):
    """Write hook to tmp, seed live_session.json, run hook, return CompletedProcess."""
    hook = tmp_path / "subagent_hook.py"
    hook.write_text(SUBAGENT_HOOK_CODE)

    tokenxray_dir = tmp_path / ".tokenxray"
    tokenxray_dir.mkdir(parents=True, exist_ok=True)

    if state is not None:
        (tokenxray_dir / "live_session.json").write_text(json.dumps(state))

    if config is not None:
        (tokenxray_dir / "config.json").write_text(json.dumps(config))

    env = {"HOME": str(tmp_path), "PATH": "/usr/bin:/bin"}
    result = subprocess.run(
        [sys.executable, str(hook)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
    )
    return result


# ── Test 1: first Agent call shows full warning ───────────────────────────────

def test_first_call_shows_full_warning(tmp_path):
    state = _state()
    payload = {"tool_name": "Agent", "session_id": SESSION_ID}
    result = _run_hook(tmp_path, payload, state=state)

    assert result.returncode == 0
    assert "Agent call" in result.stdout
    assert "subagent_warn=false" in result.stdout
    # Should NOT be the brief reminder format
    assert "Agent call #1" not in result.stdout


# ── Test 2: interval reminder fires at correct call count ─────────────────────

def test_interval_reminder_fires(tmp_path):
    # Simulate 4 previous calls, so next (5th) triggers interval (default 5)
    state = _state(extra={"subagent_calls": 4})
    payload = {"tool_name": "Agent", "session_id": SESSION_ID}
    result = _run_hook(tmp_path, payload, state=state)

    assert result.returncode == 0
    assert "Agent call #5" in result.stdout


def test_calls_between_intervals_are_silent(tmp_path):
    # 2nd call — not first, not at interval → silent
    state = _state(extra={"subagent_calls": 1})
    payload = {"tool_name": "Agent", "session_id": SESSION_ID}
    result = _run_hook(tmp_path, payload, state=state)

    assert result.returncode == 0
    assert result.stdout.strip() == ""


# ── Test 3: subagent_warn=false disables all output ──────────────────────────

def test_disable_config_suppresses_output(tmp_path):
    state = _state()
    payload = {"tool_name": "Agent", "session_id": SESSION_ID}
    result = _run_hook(tmp_path, payload, state=state, config={"subagent_warn": False})

    assert result.returncode == 0
    assert result.stdout.strip() == ""


# ── Test 4: stale/missing session → minimal first-call warning ───────────────

def test_stale_session_id_shows_warning(tmp_path):
    # live_session.json has a different session_id → state is None → show first-call warning
    state = _state(session_id="different-session-id")
    payload = {"tool_name": "Agent", "session_id": SESSION_ID}
    result = _run_hook(tmp_path, payload, state=state)

    assert result.returncode == 0
    assert "Agent call" in result.stdout


def test_missing_live_session_shows_warning(tmp_path):
    # No live_session.json written → state is None → show first-call warning
    payload = {"tool_name": "Agent", "session_id": SESSION_ID}
    result = _run_hook(tmp_path, payload, state=None)

    assert result.returncode == 0
    assert "Agent call" in result.stdout


# ── Test 5: flexible tool_name matching ──────────────────────────────────────

def test_lowercase_agent_tool_name_matches(tmp_path):
    state = _state()
    payload = {"tool_name": "agent", "session_id": SESSION_ID}
    result = _run_hook(tmp_path, payload, state=state)

    assert result.returncode == 0
    assert "Agent call" in result.stdout


def test_non_agent_tool_name_is_noop(tmp_path):
    state = _state()
    payload = {"tool_name": "Bash", "session_id": SESSION_ID}
    result = _run_hook(tmp_path, payload, state=state)

    assert result.returncode == 0
    assert result.stdout.strip() == ""


# ── Test 6: missing session_id → silent no-op ────────────────────────────────

def test_missing_session_id_is_noop(tmp_path):
    state = _state()
    payload = {"tool_name": "Agent"}  # no session_id
    result = _run_hook(tmp_path, payload, state=state)

    assert result.returncode == 0
    assert result.stdout.strip() == ""


# ── Test 7: subagent_calls counter is persisted ──────────────────────────────

def test_call_counter_increments(tmp_path):
    state = _state()
    payload = {"tool_name": "Agent", "session_id": SESSION_ID}
    _run_hook(tmp_path, payload, state=state)

    updated = json.loads((tmp_path / ".tokenxray" / "live_session.json").read_text())
    assert updated["subagent_calls"] == 1


def test_call_counter_preserves_other_keys(tmp_path):
    state = _state(extra={"alerts": [1, 3], "split_warned": True})
    payload = {"tool_name": "Agent", "session_id": SESSION_ID}
    _run_hook(tmp_path, payload, state=state)

    updated = json.loads((tmp_path / ".tokenxray" / "live_session.json").read_text())
    assert updated["alerts"] == [1, 3]
    assert updated["split_warned"] is True
    assert updated["subagent_calls"] == 1
