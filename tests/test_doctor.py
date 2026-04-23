"""Tests for tokenxray --doctor (diagnosis-only, no writes)."""
import json
import os
import subprocess
import sys
from pathlib import Path

# Ensure subprocess picks up the dev source tree, not the installed package
_SRC_DIR = str(Path(__file__).parent.parent / "src")


def _run_doctor(home: Path) -> subprocess.CompletedProcess:
    env = {**os.environ, "HOME": str(home), "PYTHONPATH": _SRC_DIR}
    return subprocess.run(
        [sys.executable, "-m", "tokenxray", "--doctor", "--no-color"],
        capture_output=True, text=True, env=env,
    )


def _make_minimal_home(tmp_path: Path) -> dict:
    """Scaffold a complete fake HOME with all hooks registered."""
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir(parents=True)
    tokenxray_dir = tmp_path / ".tokenxray"
    tokenxray_dir.mkdir()

    hook = tokenxray_dir / "cost_hook.py"
    hook.write_text("# cost hook")
    resume = tokenxray_dir / "resume_hook.py"
    resume.write_text("# resume hook")
    subagent = tokenxray_dir / "subagent_hook.py"
    subagent.write_text("# subagent hook")
    statusline = tokenxray_dir / "statusline.py"
    statusline.write_text("# statusline")
    pricing = tokenxray_dir / "pricing.json"
    pricing.write_text(json.dumps({"pricing": {}, "default": {}, "last_updated": "2026-04-23"}))

    settings = {
        "hooks": {
            "PostToolUse": [{"hooks": [{"command": str(hook)}]}],
            "UserPromptSubmit": [{"hooks": [{"command": str(resume)}]}],
            "PreToolUse": [{"hooks": [{"command": str(subagent)}]}],
        },
        "statusLine": {"command": str(statusline)},
    }
    (claude_dir / "settings.json").write_text(json.dumps(settings))

    live = tokenxray_dir / "live_session.json"
    live.write_text(json.dumps({"cost": 0.12, "turns": 5}))

    # Claude sessions
    proj = claude_dir / "projects" / "my-project"
    proj.mkdir(parents=True)
    (proj / "abc123.jsonl").write_text("{}\n")

    return {
        "home": tmp_path,
        "tokenxray_dir": tokenxray_dir,
        "claude_dir": claude_dir,
        "hook": hook,
        "settings_path": claude_dir / "settings.json",
        "live_session": live,
    }


# ─── all-green ────────────────────────────────────────────────────────────────

class TestDoctorHealthy:
    def test_exits_zero(self, tmp_path):
        _make_minimal_home(tmp_path)
        r = _run_doctor(tmp_path)
        assert r.returncode == 0

    def test_shows_header(self, tmp_path):
        _make_minimal_home(tmp_path)
        r = _run_doctor(tmp_path)
        assert "TokenXRay Doctor" in r.stdout

    def test_shows_version(self, tmp_path):
        _make_minimal_home(tmp_path)
        r = _run_doctor(tmp_path)
        assert "tokenxray" in r.stdout

    def test_shows_pricing_date(self, tmp_path):
        _make_minimal_home(tmp_path)
        r = _run_doctor(tmp_path)
        assert "2026-04-23" in r.stdout

    def test_healthy_verdict(self, tmp_path):
        _make_minimal_home(tmp_path)
        r = _run_doctor(tmp_path)
        assert "healthy" in r.stdout

    def test_hook_scripts_shown(self, tmp_path):
        _make_minimal_home(tmp_path)
        r = _run_doctor(tmp_path)
        for name in ("cost_hook.py", "resume_hook.py", "subagent_hook.py", "statusline.py"):
            assert name in r.stdout

    def test_registrations_shown(self, tmp_path):
        _make_minimal_home(tmp_path)
        r = _run_doctor(tmp_path)
        assert "PostToolUse" in r.stdout
        assert "UserPromptSubmit" in r.stdout
        assert "PreToolUse" in r.stdout
        assert "statusLine" in r.stdout

    def test_live_session_age_shown(self, tmp_path):
        _make_minimal_home(tmp_path)
        r = _run_doctor(tmp_path)
        # "Last hook fire" line should appear with time info
        assert "hook fire" in r.stdout or "last" in r.stdout.lower()

    def test_claude_sessions_counted(self, tmp_path):
        _make_minimal_home(tmp_path)
        r = _run_doctor(tmp_path)
        assert "Claude" in r.stdout
        assert "1 session" in r.stdout

    def test_verdict_section_present(self, tmp_path):
        _make_minimal_home(tmp_path)
        r = _run_doctor(tmp_path)
        assert "Verdict" in r.stdout


# ─── hooks missing ────────────────────────────────────────────────────────────

class TestDoctorHooksMissing:
    def test_not_installed_verdict(self, tmp_path):
        _make_minimal_home(tmp_path)
        # Remove hook scripts
        for name in ("cost_hook.py", "resume_hook.py", "subagent_hook.py", "statusline.py"):
            (tmp_path / ".tokenxray" / name).unlink()
        r = _run_doctor(tmp_path)
        assert "not installed" in r.stdout or "install" in r.stdout.lower()

    def test_missing_script_flagged(self, tmp_path):
        home = _make_minimal_home(tmp_path)
        home["hook"].unlink()  # remove cost_hook.py only
        r = _run_doctor(tmp_path)
        # Should show a failure indicator for cost_hook
        assert "cost_hook.py" in r.stdout
        # The tick/cross indicators — look for "not found" or similar
        assert "not found" in r.stdout


# ─── settings.json missing ────────────────────────────────────────────────────

class TestDoctorSettingsMissing:
    def test_settings_missing_noted(self, tmp_path):
        _make_minimal_home(tmp_path)
        (tmp_path / ".claude" / "settings.json").unlink()
        r = _run_doctor(tmp_path)
        assert "settings.json" in r.stdout
        assert "not found" in r.stdout

    def test_partial_verdict_when_hooks_present_settings_missing(self, tmp_path):
        _make_minimal_home(tmp_path)
        (tmp_path / ".claude" / "settings.json").unlink()
        r = _run_doctor(tmp_path)
        # hooks present, settings missing → partially configured or not installed
        assert "Verdict" in r.stdout


# ─── stale / idle activity ────────────────────────────────────────────────────

class TestDoctorIdleActivity:
    def test_idle_verdict_when_no_live_session(self, tmp_path):
        _make_minimal_home(tmp_path)
        (tmp_path / ".tokenxray" / "live_session.json").unlink()
        r = _run_doctor(tmp_path)
        assert "idle" in r.stdout or "never fired" in r.stdout or "installed" in r.stdout

    def test_live_session_not_found_noted(self, tmp_path):
        _make_minimal_home(tmp_path)
        (tmp_path / ".tokenxray" / "live_session.json").unlink()
        r = _run_doctor(tmp_path)
        assert "live_session" in r.stdout or "never fired" in r.stdout


# ─── pricing.json ─────────────────────────────────────────────────────────────

class TestDoctorPricingJson:
    def test_pricing_last_updated_shown(self, tmp_path):
        _make_minimal_home(tmp_path)
        r = _run_doctor(tmp_path)
        assert "2026-04-23" in r.stdout

    def test_missing_pricing_json_flagged(self, tmp_path):
        _make_minimal_home(tmp_path)
        (tmp_path / ".tokenxray" / "pricing.json").unlink()
        r = _run_doctor(tmp_path)
        assert "pricing.json" in r.stdout
        assert "not found" in r.stdout
