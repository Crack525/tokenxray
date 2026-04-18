"""Install Claude Code live cost tracking hook."""

import json
import os

from tokenxray.colors import C
from tokenxray.config import DATA_DIR, HOOK_SCRIPT, SETTINGS_FILE, LIVE_SESSION_FILE

HOOK_CODE = '''#!/usr/bin/env python3
"""TokenXRay live cost hook — surfaces session cost so you can decide.

Runs as a PostToolUse hook. After each tool use:
1. Reads session JSONL to compute cumulative cost, turn count, context size.
2. Shows model + cost/turn info every 10 turns so you know what you're spending.
3. Alerts at cost thresholds ($10, $25, $50, $100, $200, $500).
4. Warns to consider splitting when sessions get expensive.

Model choice is yours — this hook gives you the data to decide.
Use /model to switch anytime.
"""
import json
import sys
import glob
from pathlib import Path

COST_LOG = Path.home() / ".tokenxray" / "live_session.json"
PROJECTS_DIR = Path.home() / ".claude" / "projects"
SETTINGS_FILE = Path.home() / ".claude" / "settings.json"

PRICING = {
    "claude-opus-4-6": {"input": 15.0, "output": 75.0, "cache_read": 1.50, "cache_create": 18.75, "label": "Opus"},
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0, "cache_read": 0.30, "cache_create": 3.75, "label": "Sonnet"},
    "claude-sonnet-4-5": {"input": 3.0, "output": 15.0, "cache_read": 0.30, "cache_create": 3.75, "label": "Sonnet"},
    "claude-haiku-4-5": {"input": 0.80, "output": 4.0, "cache_read": 0.08, "cache_create": 1.0, "label": "Haiku"},
}
DEFAULT = {"input": 3.0, "output": 15.0, "cache_read": 0.30, "cache_create": 3.75, "label": "unknown"}

def get_pricing(model):
    for key, p in PRICING.items():
        if key in model:
            return p
    return DEFAULT


def get_current_model():
    """Read current model label from settings.json."""
    try:
        with open(SETTINGS_FILE) as f:
            model = json.load(f).get("model", "")
    except (FileNotFoundError, json.JSONDecodeError):
        model = ""
    return get_pricing(model)["label"]


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
    last_model = "unknown"

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
                last_model = msg.get("model", "unknown")
                p = get_pricing(last_model)
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
    prev_split_warned = False
    if COST_LOG.exists():
        try:
            with open(COST_LOG) as f:
                prev = json.load(f)
            if prev.get("session_id") == session_id:
                prev_turns = prev.get("turns", 0)
                prev_alerts = prev.get("alerts", [])
                prev_split_warned = prev.get("split_warned", False)
        except (json.JSONDecodeError, KeyError):
            pass

    tracker = {
        "session_id": session_id,
        "total_cost": total_cost,
        "turns": turn_count,
        "alerts": prev_alerts,
        "context_size": last_ctx,
        "model": get_current_model(),
        "split_warned": prev_split_warned,
    }
    COST_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(COST_LOG, "w") as f:
        json.dump(tracker, f)

    if turn_count <= prev_turns:
        return

    ctx_str = f"{last_ctx/1000:.0f}K" if last_ctx < 1e6 else f"{last_ctx/1e6:.1f}M"
    cost_per_turn = total_cost / turn_count if turn_count > 0 else 0
    model_label = get_current_model()

    # ─── Split session warning ───────────────────────────────────────────
    if not tracker.get("split_warned") and (turn_count > 80 or total_cost >= 30):
        tracker["split_warned"] = True
        with open(COST_LOG, "w") as f:
            json.dump(tracker, f)
        print(
            f"\\n\\033[1m\\033[31m[TokenXRay] Consider splitting this session! "
            f"({turn_count} turns, ${total_cost:.2f}, ctx {ctx_str}) "
            f"\\u2014 marathon sessions burn 92% of budget\\033[0m",
            file=sys.stderr,
        )

    # ─── Cost threshold alerts ───────────────────────────────────────────
    for t in [10, 25, 50, 100, 200, 500]:
        if total_cost >= t and t not in prev_alerts:
            tracker["alerts"].append(t)
            with open(COST_LOG, "w") as f:
                json.dump(tracker, f)
            print(
                f"\\n\\033[1m\\033[33m[TokenXRay] ${total_cost:.2f} spent "
                f"(crossed ${t}) \\u2014 {model_label}, {turn_count} turns, "
                f"ctx {ctx_str}, ~${cost_per_turn:.2f}/turn\\033[0m",
                file=sys.stderr,
            )
            return

    # ─── Periodic status every 10 turns ──────────────────────────────────
    if turn_count % 10 == 0:
        print(
            f"\\033[2m[TokenXRay] {model_label} \\u2014 turn {turn_count}, "
            f"${total_cost:.2f} total, ~${cost_per_turn:.2f}/turn, "
            f"ctx {ctx_str}\\033[0m",
            file=sys.stderr,
        )

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
