"""Tests for the hard-stop feature in the live cost hook."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from tokenxray.commands.hook import HOOK_CODE
from tokenxray.config import PRICING, DEFAULT_PRICING

SESSION_ID = "test-hard-stop-00000000"


def _make_jsonl(n_turns, model="claude-sonnet-4-5", input_tokens=100, output_tokens=50):
    """Return JSONL text with n_turns assistant entries."""
    lines = []
    for _ in range(n_turns):
        lines.append(json.dumps({
            "type": "assistant",
            "message": {
                "model": model,
                "usage": {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "cache_read_input_tokens": 0,
                    "cache_creation_input_tokens": 0,
                },
            },
        }))
    return "\n".join(lines) + "\n"


@pytest.fixture()
def fake_home(tmp_path):
    """Minimal fake HOME with the cost hook script and session JSONL."""
    # ~/.claude/projects/test-project/<session>.jsonl
    project_dir = tmp_path / ".claude" / "projects" / "test-project"
    project_dir.mkdir(parents=True)
    session_jsonl = project_dir / f"{SESSION_ID}.jsonl"

    # ~/.claude/settings.json — needed by get_current_model()
    (tmp_path / ".claude" / "settings.json").write_text(
        json.dumps({"model": "claude-sonnet-4-5"})
    )

    # ~/.tokenxray/
    tokenxray_dir = tmp_path / ".tokenxray"
    tokenxray_dir.mkdir()
    config_file = tokenxray_dir / "config.json"
    (tokenxray_dir / "pricing.json").write_text(
        json.dumps({"pricing": PRICING, "default": DEFAULT_PRICING})
    )

    # Write the hook script itself
    hook_script = tmp_path / "cost_hook.py"
    hook_script.write_text(HOOK_CODE)

    return {
        "home": tmp_path,
        "hook_script": hook_script,
        "session_jsonl": session_jsonl,
        "config_file": config_file,
    }


def _run_hook(fake_home):
    """Run cost_hook.py with the fake HOME and return CompletedProcess."""
    env = {**os.environ, "HOME": str(fake_home["home"])}
    return subprocess.run(
        [sys.executable, str(fake_home["hook_script"])],
        input=json.dumps({"session_id": SESSION_ID}),
        capture_output=True,
        text=True,
        env=env,
    )


# ─── hard_stop disabled (default) ─────────────────────────────────────────────

class TestHardStopDisabled:
    def test_exits_zero_without_config(self, fake_home):
        """Default config has hard_stop=false — no blocking even at many turns."""
        fake_home["session_jsonl"].write_text(_make_jsonl(130))
        result = _run_hook(fake_home)
        assert result.returncode == 0
        assert "HARD STOP" not in result.stdout

    def test_exits_zero_when_explicitly_disabled(self, fake_home):
        """Explicit hard_stop=false never blocks."""
        fake_home["config_file"].write_text(json.dumps({
            "hard_stop": False,
            "hard_stop_turns": 5,
            "hard_stop_cost": 0.01,
        }))
        fake_home["session_jsonl"].write_text(_make_jsonl(100))
        result = _run_hook(fake_home)
        assert result.returncode == 0
        assert "HARD STOP" not in result.stdout


# ─── hard_stop enabled ────────────────────────────────────────────────────────

class TestHardStopEnabled:
    def test_turn_limit_triggers_exit_2(self, fake_home):
        """Exceeding hard_stop_turns exits with code 2."""
        fake_home["config_file"].write_text(json.dumps({
            "hard_stop": True,
            "hard_stop_turns": 120,
            "hard_stop_cost": 9999,
        }))
        fake_home["session_jsonl"].write_text(_make_jsonl(130))
        result = _run_hook(fake_home)
        assert result.returncode == 2

    def test_turn_limit_message_on_stdout(self, fake_home):
        """Hard-stop message must go to stdout so Claude sees it."""
        fake_home["config_file"].write_text(json.dumps({
            "hard_stop": True,
            "hard_stop_turns": 120,
            "hard_stop_cost": 9999,
        }))
        fake_home["session_jsonl"].write_text(_make_jsonl(130))
        result = _run_hook(fake_home)
        assert "HARD STOP" in result.stdout
        assert "HARD STOP" not in result.stderr

    def test_turn_limit_message_contains_counts(self, fake_home):
        """Message shows actual/limit turn counts."""
        fake_home["config_file"].write_text(json.dumps({
            "hard_stop": True,
            "hard_stop_turns": 120,
            "hard_stop_cost": 9999,
        }))
        fake_home["session_jsonl"].write_text(_make_jsonl(130))
        result = _run_hook(fake_home)
        assert "130" in result.stdout  # actual turns
        assert "120" in result.stdout  # limit

    def test_cost_limit_triggers_exit_2(self, fake_home):
        """Exceeding hard_stop_cost exits with code 2."""
        fake_home["config_file"].write_text(json.dumps({
            "hard_stop": True,
            "hard_stop_turns": 9999,
            "hard_stop_cost": 0.40,
        }))
        # 3 Opus turns × (10 000 input + 5 000 output) ≈ $0.53 (Opus 4.6 @ $5/$25)
        fake_home["session_jsonl"].write_text(
            _make_jsonl(3, model="claude-opus-4-6", input_tokens=10_000, output_tokens=5_000)
        )
        result = _run_hook(fake_home)
        assert result.returncode == 2

    def test_cost_limit_message_on_stdout(self, fake_home):
        """Cost hard-stop message goes to stdout."""
        fake_home["config_file"].write_text(json.dumps({
            "hard_stop": True,
            "hard_stop_turns": 9999,
            "hard_stop_cost": 0.40,
        }))
        fake_home["session_jsonl"].write_text(
            _make_jsonl(3, model="claude-opus-4-6", input_tokens=10_000, output_tokens=5_000)
        )
        result = _run_hook(fake_home)
        assert "HARD STOP" in result.stdout
        assert "cost limit" in result.stdout

    def test_below_both_ceilings_exits_zero(self, fake_home):
        """Enabled hard-stop but below both ceilings — no block."""
        fake_home["config_file"].write_text(json.dumps({
            "hard_stop": True,
            "hard_stop_turns": 120,
            "hard_stop_cost": 50.0,
        }))
        fake_home["session_jsonl"].write_text(_make_jsonl(10))
        result = _run_hook(fake_home)
        assert result.returncode == 0
        assert "HARD STOP" not in result.stdout

    def test_at_exact_turn_ceiling_triggers(self, fake_home):
        """Turn count equal to hard_stop_turns triggers the stop (>=)."""
        fake_home["config_file"].write_text(json.dumps({
            "hard_stop": True,
            "hard_stop_turns": 10,
            "hard_stop_cost": 9999,
        }))
        fake_home["session_jsonl"].write_text(_make_jsonl(10))
        result = _run_hook(fake_home)
        assert result.returncode == 2

    def test_wrap_up_instruction_in_message(self, fake_home):
        """Message instructs user to start a fresh session."""
        fake_home["config_file"].write_text(json.dumps({
            "hard_stop": True,
            "hard_stop_turns": 5,
            "hard_stop_cost": 9999,
        }))
        fake_home["session_jsonl"].write_text(_make_jsonl(10))
        result = _run_hook(fake_home)
        assert "fresh session" in result.stdout.lower() or "wrap up" in result.stdout.lower()
