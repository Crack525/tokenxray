"""Tests for the session history feed in the resume hook."""

import json
import os
import subprocess
import sys

import pytest

from tokenxray.commands.hook import RESUME_HOOK_CODE


@pytest.fixture()
def fake_home(tmp_path):
    tokenxray_dir = tmp_path / ".tokenxray"
    tokenxray_dir.mkdir()
    hook_script = tmp_path / "resume_hook.py"
    hook_script.write_text(RESUME_HOOK_CODE)
    return {"home": tmp_path, "hook_script": hook_script, "tokenxray_dir": tokenxray_dir}


def _run_hook(fake_home, cwd=None):
    env = {**os.environ, "HOME": str(fake_home["home"])}
    return subprocess.run(
        [sys.executable, str(fake_home["hook_script"])],
        capture_output=True,
        text=True,
        env=env,
        cwd=cwd or str(fake_home["home"]),
    )


def _write_live_session(fake_home, session_id, turns=10, cost=0.50):
    (fake_home["tokenxray_dir"] / "live_session.json").write_text(
        json.dumps(
            {
                "session_id": session_id,
                "turns": turns,
                "total_cost": cost,
                "model": "claude-sonnet-4-6",
                "context_size": 50000,
            }
        )
    )


class TestArchiveSessionToHistory:
    def test_history_written_after_summary(self, fake_home, tmp_path):
        """history.jsonl is created after a session transition is shown."""
        project_dir = tmp_path / "myproject"
        project_dir.mkdir()
        _write_live_session(fake_home, "sess-aaa", turns=12, cost=0.75)
        _run_hook(fake_home, cwd=str(project_dir))

        history_file = fake_home["tokenxray_dir"] / "history.jsonl"
        assert history_file.exists()
        entry = json.loads(history_file.read_text().strip())
        assert entry["project"] == "myproject"
        assert entry["turns"] == 12
        assert abs(entry["cost"] - 0.75) < 0.001
        assert entry["session_id"] == "sess-aaa"

    def test_history_not_duplicated_on_repeat_run(self, fake_home, tmp_path):
        """Second run with same session_id (already shown) does not append again."""
        project_dir = tmp_path / "myproject"
        project_dir.mkdir()
        _write_live_session(fake_home, "sess-bbb", turns=5, cost=0.10)
        # First run — archives
        _run_hook(fake_home, cwd=str(project_dir))
        # Second run — SUMMARY_SHOWN matches, so show_last_session_summary returns early
        _run_hook(fake_home, cwd=str(project_dir))

        history_file = fake_home["tokenxray_dir"] / "history.jsonl"
        lines = [l for l in history_file.read_text().splitlines() if l.strip()]
        assert len(lines) == 1


class TestShowSessionHistory:
    def test_history_displayed_on_subsequent_session(self, fake_home, tmp_path):
        """Project history lines appear at next session start."""
        project_dir = tmp_path / "coolproject"
        project_dir.mkdir()

        # Pre-populate history with two past entries
        history_file = fake_home["tokenxray_dir"] / "history.jsonl"
        history_file.write_text(
            json.dumps(
                {
                    "ts": "2026-05-01T10:00:00Z",
                    "session_id": "old-1",
                    "project": "coolproject",
                    "turns": 8,
                    "cost": 0.30,
                    "model": "claude-sonnet-4-6",
                    "context_size": 40000,
                }
            )
            + "\n"
            + json.dumps(
                {
                    "ts": "2026-05-02T10:00:00Z",
                    "session_id": "old-2",
                    "project": "otherproject",
                    "turns": 5,
                    "cost": 0.20,
                    "model": "claude-sonnet-4-6",
                    "context_size": 30000,
                }
            )
            + "\n"
        )

        # No live_session.json — no summary, but history should still display
        result = _run_hook(fake_home, cwd=str(project_dir))
        assert "Project history (coolproject)" in result.stdout
        assert "2026-05-01" in result.stdout
        # other project's entry must NOT appear
        assert "otherproject" not in result.stdout

    def test_no_output_when_no_history(self, fake_home, tmp_path):
        """No history section printed if history.jsonl does not exist."""
        project_dir = tmp_path / "brandnew"
        project_dir.mkdir()
        result = _run_hook(fake_home, cwd=str(project_dir))
        assert "Project history" not in result.stdout
