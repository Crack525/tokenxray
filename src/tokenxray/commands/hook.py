"""Install Claude Code live cost tracking hook."""

import json
import os

from tokenxray.colors import C
from tokenxray.config import DATA_DIR, HOOK_SCRIPT, SETTINGS_FILE, LIVE_SESSION_FILE

HOOK_CODE = '''#!/usr/bin/env python3
"""TokenXRay live cost hook — reads session JSONL to track running cost."""
import json
import sys
import glob
from pathlib import Path

COST_LOG = Path.home() / ".tokenxray" / "live_session.json"
PROJECTS_DIR = Path.home() / ".claude" / "projects"

PRICING = {
    "claude-opus-4-6": {"input": 15.0, "output": 75.0, "cache_read": 1.50, "cache_create": 18.75},
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0, "cache_read": 0.30, "cache_create": 3.75},
    "claude-sonnet-4-5": {"input": 3.0, "output": 15.0, "cache_read": 0.30, "cache_create": 3.75},
    "claude-haiku-4-5": {"input": 0.80, "output": 4.0, "cache_read": 0.08, "cache_create": 1.0},
}
DEFAULT = {"input": 3.0, "output": 15.0, "cache_read": 0.30, "cache_create": 3.75}

def get_pricing(model):
    for key, p in PRICING.items():
        if key in model:
            return p
    return DEFAULT

def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        return

    session_id = data.get("session_id", "unknown")
    jsonl_files = glob.glob(str(PROJECTS_DIR / "**" / f"{session_id}.jsonl"), recursive=True)
    if not jsonl_files:
        return

    total_cost = 0.0
    turn_count = 0
    last_ctx = 0

    try:
        with open(jsonl_files[0]) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if entry.get("type") != "assistant":
                    continue
                msg = entry.get("message", {})
                usage = msg.get("usage", {})
                if not usage:
                    continue
                p = get_pricing(msg.get("model", "unknown"))
                inp = usage.get("input_tokens", 0)
                out = usage.get("output_tokens", 0)
                cr = usage.get("cache_read_input_tokens", 0)
                cc = usage.get("cache_creation_input_tokens", 0)
                total_cost += (inp/1e6)*p["input"] + (out/1e6)*p["output"] + (cr/1e6)*p["cache_read"] + (cc/1e6)*p["cache_create"]
                turn_count += 1
                last_ctx = inp + cr + cc
    except Exception:
        return

    if turn_count == 0:
        return

    prev_turns = 0
    prev_alerts = []
    if COST_LOG.exists():
        try:
            with open(COST_LOG) as f:
                prev = json.load(f)
            if prev.get("session_id") == session_id:
                prev_turns = prev.get("turns", 0)
                prev_alerts = prev.get("alerts", [])
        except (json.JSONDecodeError, KeyError):
            pass

    tracker = {"session_id": session_id, "total_cost": total_cost, "turns": turn_count, "alerts": prev_alerts, "context_size": last_ctx}
    COST_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(COST_LOG, "w") as f:
        json.dump(tracker, f)

    if turn_count <= prev_turns:
        return

    for t in [10, 25, 50, 100, 200, 500]:
        if total_cost >= t and t not in prev_alerts:
            tracker["alerts"].append(t)
            with open(COST_LOG, "w") as f:
                json.dump(tracker, f)
            ctx_str = f"{last_ctx/1000:.0f}K" if last_ctx < 1e6 else f"{last_ctx/1e6:.1f}M"
            print(f"\\n\\033[1m\\033[33m[TokenXRay] Session cost: ${total_cost:.2f} (crossed ${t}, {turn_count} turns, ctx {ctx_str})\\033[0m", file=sys.stderr)
            return

    if turn_count % 20 == 0:
        ctx_str = f"{last_ctx/1000:.0f}K" if last_ctx < 1e6 else f"{last_ctx/1e6:.1f}M"
        print(f"\\033[2m[TokenXRay] Turn {turn_count}: ${total_cost:.2f}, ctx {ctx_str}\\033[0m", file=sys.stderr)

if __name__ == "__main__":
    main()
'''


def run(args):
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Write the hook script
    with open(HOOK_SCRIPT, "w") as f:
        f.write(HOOK_CODE)
    os.chmod(HOOK_SCRIPT, 0o755)

    # Check if already installed
    settings = {}
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE) as f:
                settings = json.load(f)
        except json.JSONDecodeError:
            pass

    hooks = settings.get("hooks", {})
    post_tool = hooks.get("PostToolUse", [])

    already = any(
        str(HOOK_SCRIPT) in str(h.get("hooks", []))
        for h in post_tool if isinstance(h, dict)
    )

    if already:
        print(f"{C.GREEN}Hook already installed! Script updated at {HOOK_SCRIPT}{C.RESET}")
        return

    print()
    print(f"{C.BOLD}{C.CYAN}TokenXRay — Install Live Cost Hook{C.RESET}")
    print(f"{C.DIM}{'─' * 70}{C.RESET}")
    print(f"  Hook script: {HOOK_SCRIPT}")
    print(f"  Tracks cost, alerts at $10/$25/$50/$100/$200, updates every 20 turns")
    print()

    if getattr(args, "confirm", False):
        hook_entry = {
            "matcher": ".*",
            "hooks": [{"type": "command", "command": f"python3 {HOOK_SCRIPT}"}],
        }
        if not isinstance(post_tool, list):
            post_tool = []
        post_tool.append(hook_entry)
        hooks["PostToolUse"] = post_tool
        settings["hooks"] = hooks

        with open(SETTINGS_FILE, "w") as f:
            json.dump(settings, f, indent=2)

        print(f"  {C.GREEN}{C.BOLD}Hook installed! Restart Claude Code to activate.{C.RESET}")
    else:
        print(f"  Run: {C.BOLD}tokenxray --install-hook --confirm{C.RESET} to auto-install")

    print()
