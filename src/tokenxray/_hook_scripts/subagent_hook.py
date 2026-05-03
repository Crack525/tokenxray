#!/usr/bin/env python3
"""TokenXRay subagent hook — warns on Agent tool calls.

Runs as a PreToolUse hook, matcher: Agent.
Fires before each Agent tool invocation:
1. Shows a full warning on the first Agent call in the session.
2. Shows a brief reminder every subagent_warn_interval calls after that.
3. Never blocks — non-blocking, informational only.
"""

import json
import sys
from pathlib import Path

COST_LOG = Path.home() / ".tokenxray" / "live_session.json"
CONFIG_FILE = Path.home() / ".tokenxray" / "config.json"

DEFAULT_CONFIG = {
    "subagent_warn": True,
    "subagent_warn_interval": 5,
    "debug_log": False,
}

DEBUG_LOG = Path.home() / ".tokenxray" / "debug.log"


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_FILE) as f:
            user = json.load(f)
        cfg.update(user)
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return cfg


def write_debug(message, enabled=False):
    if not enabled:
        return
    try:
        DEBUG_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(DEBUG_LOG, "a") as f:
            f.write(f"subagent_hook: {message}\n")
    except Exception:
        pass


def load_state(session_id):
    """Return live_session.json contents, or None if missing/stale."""
    try:
        with open(COST_LOG) as f:
            state = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    if state.get("session_id") != session_id:
        return None
    return state


def save_state(session_id, updates):
    """Read-merge-write: preserves all existing keys, silent on failure."""
    try:
        try:
            with open(COST_LOG) as f:
                existing = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            existing = {}
        # Guard: don\'t merge into a stale session
        if existing.get("session_id") != session_id:
            return
        existing.update(updates)
        COST_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(COST_LOG, "w") as f:
            json.dump(existing, f)
    except Exception:
        pass


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        return

    # Flexible tool name matching — handle varying field names across clients
    tool_name = data.get("tool_name", "") or data.get("toolName", "") or ""
    if "agent" not in tool_name.lower():
        return

    session_id = data.get("session_id", "") or data.get("sessionId", "") or ""
    if not session_id:
        return

    cfg = load_config()
    debug_enabled = cfg.get("debug_log", False)
    write_debug("invoked", debug_enabled)
    if not cfg.get("subagent_warn", True):
        write_debug("subagent_warn disabled", debug_enabled)
        return

    state = load_state(session_id)
    if state is None:
        write_debug("no live state, showing minimal first-call warning", debug_enabled)
        print(
            "\n\033[1m\033[33m[TokenXRay] Agent call — subagents spawn a full context "
            "and cost significantly more per task.\033[0m\n"
            "\033[2m[TokenXRay] Disable: set subagent_warn=false in ~/.tokenxray/config.json\033[0m",
            file=sys.stdout,
        )
        return

    call_count = state.get("subagent_calls", 0) + 1
    save_state(session_id, {"subagent_calls": call_count})
    write_debug(f"subagent call_count={call_count}", debug_enabled)

    total_cost = state.get("total_cost", 0.0)
    turn_count = state.get("turns", 0)
    model = state.get("model", "unknown")
    cost_per_turn = total_cost / turn_count if turn_count > 0 else 0.0

    interval = cfg.get("subagent_warn_interval", 5)

    if call_count == 1:
        print(
            f"\n\033[1m\033[33m[TokenXRay] Agent call — subagents spawn a full context "
            f"and cost significantly more per task.\033[0m\n"
            f"\033[2m[TokenXRay] Session: {turn_count} turns, ${total_cost:.2f} so far "
            f"(~${cost_per_turn:.2f}/turn), {model}\033[0m\n"
            f"\033[2m[TokenXRay] Disable: set subagent_warn=false in ~/.tokenxray/config.json\033[0m",
            file=sys.stdout,
        )
    elif interval > 0 and call_count % interval == 0:
        print(
            f"\033[2m[TokenXRay] Agent call #{call_count} this session — "
            f"${total_cost:.2f} total so far.\033[0m",
            file=sys.stdout,
        )


if __name__ == "__main__":
    main()
