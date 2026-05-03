"""Install Claude Code live cost tracking hook + auto-checkpoint + resume hook."""

from __future__ import annotations

import json
import os
from pathlib import Path

from tokenxray import __version__ as _PKG_VERSION
from tokenxray.colors import C
from tokenxray.config import (
    DATA_DIR,
    HOOK_SCRIPT,
    STATUSLINE_SCRIPT,
    SETTINGS_FILE,
    PRICING,
    DEFAULT_PRICING,
    PRICING_LAST_UPDATED,
)

RESUME_HOOK_SCRIPT = DATA_DIR / "resume_hook.py"
SUBAGENT_HOOK_SCRIPT = DATA_DIR / "subagent_hook.py"


def _read_deployed_version() -> str | None:
    """Return TOKENXRAY_HOOK_VERSION from the deployed cost hook, or None."""
    try:
        for line in HOOK_SCRIPT.read_text().splitlines():
            if line.startswith("TOKENXRAY_HOOK_VERSION"):
                return line.split('"')[1]
    except Exception:
        pass
    return None


def check_hook_skew() -> tuple[str | None, str | None]:
    """Return (deployed_version, package_version) if skew detected, else (None, None)."""
    deployed = _read_deployed_version()
    if deployed and deployed != _PKG_VERSION:
        return deployed, _PKG_VERSION
    return None, None


def _write_scripts():
    """Write all hook and statusline scripts to ~/.tokenxray/."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    _scripts = Path(__file__).parent.parent / "_hook_scripts"
    versioned_hook = (
        (_scripts / "cost_hook.py")
        .read_text()
        .replace("%%TOKENXRAY_VERSION%%", _PKG_VERSION)
    )

    for path, code in [
        (HOOK_SCRIPT, versioned_hook),
        (RESUME_HOOK_SCRIPT, (_scripts / "resume_hook.py").read_text()),
        (SUBAGENT_HOOK_SCRIPT, (_scripts / "subagent_hook.py").read_text()),
        (STATUSLINE_SCRIPT, (_scripts / "statusline.py").read_text()),
    ]:
        with open(path, "w") as f:
            f.write(code)
        os.chmod(path, 0o755)

    import json as _json

    pricing_file = DATA_DIR / "pricing.json"
    with open(pricing_file, "w") as f:
        _json.dump(
            {
                "pricing": PRICING,
                "default": DEFAULT_PRICING,
                "last_updated": PRICING_LAST_UPDATED,
            },
            f,
            indent=2,
        )


def _load_settings():
    """Load ~/.claude/settings.json."""
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE) as f:
                return json.load(f)
        except json.JSONDecodeError:
            pass
    return {}


def _is_installed(entries, script_path):
    """Check if a hook script is already registered."""
    return any(
        str(script_path) in str(h.get("hooks", []))
        for h in entries
        if isinstance(h, dict)
    )


def _statusline_installed(settings):
    """Check if statusline is already registered."""
    sl = settings.get("statusLine", {})
    return str(STATUSLINE_SCRIPT) in str(sl.get("command", ""))


def run(args):
    old_ver = _read_deployed_version()
    _write_scripts()

    if old_ver and old_ver != _PKG_VERSION:
        print(
            f"{C.YELLOW}Hook scripts updated: v{old_ver} → v{_PKG_VERSION} "
            f"(were stale after package upgrade){C.RESET}"
        )

    settings = _load_settings()
    hooks = settings.get("hooks", {})
    post_tool = hooks.get("PostToolUse", [])
    user_prompt = hooks.get("UserPromptSubmit", [])
    pre_tool = hooks.get("PreToolUse", [])

    cost_ok = _is_installed(post_tool, HOOK_SCRIPT)
    resume_ok = _is_installed(user_prompt, RESUME_HOOK_SCRIPT)
    subagent_ok = _is_installed(pre_tool, SUBAGENT_HOOK_SCRIPT)
    statusline_ok = _statusline_installed(settings)

    all_installed = cost_ok and resume_ok and subagent_ok and statusline_ok

    if all_installed:
        print(
            f"{C.GREEN}All hooks + status line already installed! Scripts updated at {DATA_DIR}{C.RESET}"
        )
        return

    print()
    print(f"{C.BOLD}{C.CYAN}TokenXRay — Install Hooks + Status Line{C.RESET}")
    print(f"{C.DIM}{'─' * 70}{C.RESET}")
    print(f"  Cost hook:     {HOOK_SCRIPT}")
    print(f"  Resume hook:   {RESUME_HOOK_SCRIPT}")
    print(f"  Subagent hook: {SUBAGENT_HOOK_SCRIPT}")
    print(f"  Status line:   {STATUSLINE_SCRIPT}")
    print()
    print("  Hooks track cost, auto-checkpoint, and warn on Agent calls.")
    print("  Status line shows live session health at the bottom of Claude Code.")
    print()

    if getattr(args, "confirm", False):
        if not cost_ok:
            hook_entry = {
                "matcher": ".*",
                "hooks": [{"type": "command", "command": f"python3 {HOOK_SCRIPT}"}],
            }
            if not isinstance(post_tool, list):
                post_tool = []
            post_tool.append(hook_entry)
            hooks["PostToolUse"] = post_tool

        if not resume_ok:
            resume_entry = {
                "matcher": "",
                "hooks": [
                    {"type": "command", "command": f"python3 {RESUME_HOOK_SCRIPT}"}
                ],
            }
            if not isinstance(user_prompt, list):
                user_prompt = []
            user_prompt.append(resume_entry)
            hooks["UserPromptSubmit"] = user_prompt

        if not subagent_ok:
            subagent_entry = {
                "matcher": "Agent",
                "hooks": [
                    {"type": "command", "command": f"python3 {SUBAGENT_HOOK_SCRIPT}"}
                ],
            }
            if not isinstance(pre_tool, list):
                pre_tool = []
            pre_tool.append(subagent_entry)
            hooks["PreToolUse"] = pre_tool

        settings["hooks"] = hooks

        if not statusline_ok:
            settings["statusLine"] = {
                "type": "command",
                "command": f"python3 {STATUSLINE_SCRIPT}",
                "padding": 2,
            }

        tmp = SETTINGS_FILE.with_suffix(".json.tmp")
        try:
            with open(tmp, "w") as f:
                json.dump(settings, f, indent=2)
            os.replace(tmp, SETTINGS_FILE)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise

        print(
            f"  {C.GREEN}{C.BOLD}Hooks + status line installed! Restart Claude Code to activate.{C.RESET}"
        )
    else:
        print(
            f"  Run: {C.BOLD}tokenxray --install-hook --confirm{C.RESET} to auto-install"
        )

    print()
