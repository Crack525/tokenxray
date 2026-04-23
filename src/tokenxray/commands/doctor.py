"""Diagnose TokenXRay installation health — read-only, no writes."""

import json
import platform
import sys
import time
from pathlib import Path

from tokenxray import __version__
from tokenxray.colors import C
from tokenxray.config import (
    CLAUDE_PROJECTS_DIR,
    GEMINI_SESSIONS_DIR,
    COPILOT_WORKSPACE_DIR,
    SETTINGS_FILE,
    DATA_DIR,
    HOOK_SCRIPT,
    STATUSLINE_SCRIPT,
    PRICING_LAST_UPDATED,
)

RESUME_HOOK_SCRIPT = DATA_DIR / "resume_hook.py"
SUBAGENT_HOOK_SCRIPT = DATA_DIR / "subagent_hook.py"
PRICING_JSON = DATA_DIR / "pricing.json"
LIVE_SESSION_FILE = DATA_DIR / "live_session.json"
DEBUG_LOG = DATA_DIR / "debug.log"


def _age_str(mtime: float) -> str:
    """Human-readable age string for a file mtime."""
    secs = time.time() - mtime
    if secs < 120:
        return f"{int(secs)}s ago"
    if secs < 3600:
        return f"{int(secs / 60)}m ago"
    if secs < 86400:
        return f"{int(secs / 3600)}h ago"
    return f"{int(secs / 86400)}d ago"


def _size_str(path: Path) -> str:
    size = path.stat().st_size
    if size < 1024:
        return f"{size} B"
    return f"{size / 1024:.1f} KB"


def _ok(msg: str) -> str:
    return f"{C.GREEN}✓{C.RESET} {msg}"


def _warn(msg: str) -> str:
    return f"{C.YELLOW}✗{C.RESET} {msg}"


def _check_hook_script(label: str, path: Path) -> tuple[bool, str]:
    if path.exists() and path.stat().st_size > 0:
        stat = path.stat()
        detail = f"{_size_str(path)} · modified {_age_str(stat.st_mtime)}"
        return True, _ok(f"{label:<22} {detail}")
    return False, _warn(f"{label:<22} not found ({path})")


def _check_settings() -> dict[str, tuple[bool, str]]:
    """Return dict of registration name → (ok, line)."""
    results = {}
    if not SETTINGS_FILE.exists():
        missing = _warn(f"settings.json not found ({SETTINGS_FILE})")
        for key in ("PostToolUse", "UserPromptSubmit", "PreToolUse", "statusLine"):
            results[key] = (False, missing)
        return results

    try:
        settings = json.loads(SETTINGS_FILE.read_text())
    except json.JSONDecodeError:
        err = _warn("settings.json is not valid JSON")
        for key in ("PostToolUse", "UserPromptSubmit", "PreToolUse", "statusLine"):
            results[key] = (False, err)
        return results

    hooks = settings.get("hooks", {})

    def _hook_registered(hook_type: str, script_path: Path) -> bool:
        entries = hooks.get(hook_type, [])
        script_str = str(script_path)
        for entry in entries:
            if isinstance(entry, dict):
                for h in entry.get("hooks", []):
                    if script_str in str(h.get("command", "")):
                        return True
        return False

    for hook_type, script, label in [
        ("PostToolUse", HOOK_SCRIPT, "PostToolUse → cost_hook.py"),
        ("UserPromptSubmit", RESUME_HOOK_SCRIPT, "UserPromptSubmit → resume_hook.py"),
        ("PreToolUse", SUBAGENT_HOOK_SCRIPT, "PreToolUse → subagent_hook.py"),
    ]:
        ok = _hook_registered(hook_type, script)
        results[hook_type] = (ok, _ok(label) if ok else _warn(f"{label}  (not registered)"))

    sl_cmd = settings.get("statusLine", {}).get("command", "")
    sl_ok = str(STATUSLINE_SCRIPT) in sl_cmd
    results["statusLine"] = (
        sl_ok,
        _ok("statusLine → statusline.py") if sl_ok else _warn("statusLine → statusline.py  (not registered)"),
    )
    return results


def _check_pricing_json() -> tuple[bool, str]:
    if not PRICING_JSON.exists():
        return False, _warn(f"pricing.json not found ({PRICING_JSON})")
    try:
        data = json.loads(PRICING_JSON.read_text())
        last = data.get("last_updated", "unknown")
        return True, _ok(f"{'pricing.json':<22} last_updated: {last}")
    except json.JSONDecodeError:
        return False, _warn("pricing.json is not valid JSON")


def _session_counts() -> dict[str, tuple[int, float | None]]:
    """Return {source: (count, newest_mtime_or_None)}."""
    results = {}

    def _count(root: Path, pattern: str) -> tuple[int, float | None]:
        if not root.exists():
            return 0, None
        files = list(root.rglob(pattern))
        if not files:
            return 0, None
        newest = max(f.stat().st_mtime for f in files)
        return len(files), newest

    results["Claude"] = _count(CLAUDE_PROJECTS_DIR, "*.jsonl")
    results["Gemini"] = _count(GEMINI_SESSIONS_DIR, "*.json")
    results["Copilot"] = _count(COPILOT_WORKSPACE_DIR, "*.json")
    return results


def run(_args=None) -> None:
    sep = "─" * 44

    print(f"\n{C.BOLD}{C.CYAN}TokenXRay Doctor{C.RESET}")
    print(sep)

    # ── Version + platform ────────────────────────────────────────────────────
    install_path = Path(sys.modules["tokenxray"].__file__).parent
    arch = platform.machine()
    print(f"  {'Version':<20} tokenxray {__version__}")
    print(f"  {'Pricing date':<20} {PRICING_LAST_UPDATED}")
    print(f"  {'Python':<20} {sys.version.split()[0]} on {sys.platform}/{arch}")
    print(f"  {'Install path':<20} {install_path}")
    print()

    # ── Hook scripts ─────────────────────────────────────────────────────────
    print(f"{C.BOLD}Hook scripts at {DATA_DIR}/{C.RESET}")
    script_results = []
    for label, path in [
        ("cost_hook.py", HOOK_SCRIPT),
        ("resume_hook.py", RESUME_HOOK_SCRIPT),
        ("subagent_hook.py", SUBAGENT_HOOK_SCRIPT),
        ("statusline.py", STATUSLINE_SCRIPT),
    ]:
        ok, line = _check_hook_script(label, path)
        script_results.append(ok)
        print(f"  {line}")

    pricing_ok, pricing_line = _check_pricing_json()
    script_results.append(pricing_ok)
    print(f"  {pricing_line}")
    print()

    # ── Settings registrations ─────────────────────────────────────────────
    print(f"{C.BOLD}Claude Code registration at {SETTINGS_FILE}{C.RESET}")
    reg = _check_settings()
    reg_results = []
    for key in ("PostToolUse", "UserPromptSubmit", "PreToolUse", "statusLine"):
        ok, line = reg[key]
        reg_results.append(ok)
        print(f"  {line}")
    print()

    # ── Hook activity ─────────────────────────────────────────────────────
    print(f"{C.BOLD}Hook activity{C.RESET}")
    if LIVE_SESSION_FILE.exists():
        stat = LIVE_SESSION_FILE.stat()
        age = _age_str(stat.st_mtime)
        try:
            data = json.loads(LIVE_SESSION_FILE.read_text())
            cost = data.get("total_cost", data.get("cost", 0.0))
            turns = data.get("turns", data.get("turn_count", 0))
            print(f"  {_ok(f'Last hook fire   {age}  (${cost:.4f} · {turns} turns)')}")
        except (json.JSONDecodeError, KeyError):
            print(f"  {_ok(f'Last hook fire   {age}')}")
        activity_ok = True
    else:
        print(f"  {_warn('live_session.json not found — hook has never fired')}")
        activity_ok = False

    debug_enabled = DEBUG_LOG.exists() and DEBUG_LOG.stat().st_size > 0
    print(f"  {'Debug log':<20} {'enabled (' + str(DEBUG_LOG) + ')' if debug_enabled else 'disabled'}")
    print()

    # ── Data sources ──────────────────────────────────────────────────────
    print(f"{C.BOLD}Data sources{C.RESET}")
    src_results = []
    for source, (count, newest) in _session_counts().items():
        if count > 0:
            age_info = f", newest {_age_str(newest)}" if newest else ""
            print(f"  {_ok(f'{source:<8} {count} session{'' if count == 1 else 's'}{age_info}')}")
            src_results.append(True)
        else:
            print(f"  {_warn(f'{source:<8} no sessions found')}")
            src_results.append(False)
    print()

    # ── Verdict ───────────────────────────────────────────────────────────
    hooks_ok = all(script_results)
    regs_ok = all(reg_results)

    if hooks_ok and regs_ok and activity_ok:
        verdict = f"{C.GREEN}{C.BOLD}healthy{C.RESET} — all hooks installed and firing"
    elif hooks_ok and regs_ok:
        verdict = f"{C.YELLOW}{C.BOLD}installed but idle{C.RESET} — hooks present but haven't fired yet"
    elif not hooks_ok:
        verdict = f"{C.RED}{C.BOLD}not installed{C.RESET} — run: tokenxray --install-hook --confirm"
    else:
        verdict = f"{C.YELLOW}{C.BOLD}partially configured{C.RESET} — some registrations missing"

    print(f"Verdict: {verdict}")
    print()
