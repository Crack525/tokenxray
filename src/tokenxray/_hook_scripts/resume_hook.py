#!/usr/bin/env python3
"""TokenXRay resume hook — last session summary + auto-loads checkpoint.

Runs as a UserPromptSubmit hook. On each user message:
1. Shows a one-line cost summary of the previous session (fires once per session).
2. Checks if .claude/checkpoint.md exists in the current directory.
3. If found and recent (< 48 hours), tells Claude to read it.
4. Renames checkpoint after first load so it only fires once per session.

The summary uses live_session.json (written by the cost hook). On a new session's
first prompt, live_session.json still holds the PREVIOUS session's data — the cost
hook hasn't updated it yet. We detect "already shown" by recording the session_id
we last displayed, so it fires exactly once per session transition.
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timezone

COST_LOG = Path.home() / ".tokenxray" / "live_session.json"
SUMMARY_SHOWN = Path.home() / ".tokenxray" / ".last_summary_session"
HISTORY_LOG = Path.home() / ".tokenxray" / "history.jsonl"
CONFIG_FILE = Path.home() / ".tokenxray" / "config.json"
DEBUG_LOG = Path.home() / ".tokenxray" / "debug.log"


def load_config():
    cfg = {"debug_log": False}
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
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with open(DEBUG_LOG, "a") as f:
            f.write(f"[{ts}] resume_hook: {message}\n")
    except Exception:
        pass


def show_last_session_summary():
    """Show a one-line summary of the previous session (once per new session).

    On the first prompt of a new session, live_session.json still contains
    the previous session's data. We show it once, then write the session_id
    to .last_summary_session so we don't repeat.
    """
    if not COST_LOG.exists():
        return

    try:
        with open(COST_LOG) as f:
            prev = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return

    prev_session = prev.get("session_id", "")
    if not prev_session:
        return

    # Already shown for this session?
    try:
        if SUMMARY_SHOWN.exists():
            if SUMMARY_SHOWN.read_text().strip() == prev_session:
                return
    except Exception:
        pass

    turns = prev.get("turns", 0)
    cost = prev.get("total_cost", 0.0)
    model = prev.get("model", "unknown")
    ctx = prev.get("context_size", 0)
    if turns == 0 or cost == 0:
        return

    ctx_str = f"{ctx / 1000:.0f}K" if ctx < 1e6 else f"{ctx / 1e6:.1f}M"
    cost_per_turn = cost / turns

    print(
        f"\033[2m[TokenXRay] Last session: {turns} turns, "
        f"${cost:.2f} total, ~${cost_per_turn:.2f}/turn, "
        f"{model}, ctx {ctx_str}\033[0m",
        file=sys.stdout,
    )

    # Mark as shown
    try:
        SUMMARY_SHOWN.write_text(prev_session)
    except Exception:
        pass

    archive_session_to_history(prev)


def archive_session_to_history(prev):
    """Append previous session stats to ~/.tokenxray/history.jsonl."""
    try:
        entry = {
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "session_id": prev.get("session_id", ""),
            "project": Path.cwd().name,
            "turns": prev.get("turns", 0),
            "cost": prev.get("total_cost", 0.0),
            "model": prev.get("model", "unknown"),
            "context_size": prev.get("context_size", 0),
        }
        HISTORY_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(HISTORY_LOG, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass


def show_session_history():
    """Print the last 3 sessions for the current project from history.jsonl."""
    if not HISTORY_LOG.exists():
        return
    try:
        project = Path.cwd().name
        entries = []
        with open(HISTORY_LOG) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if e.get("project") == project:
                    entries.append(e)
        recent = entries[-3:]
        if not recent:
            return
        print(f"\033[2m[TokenXRay] Project history ({project}):", file=sys.stdout)
        for e in recent:
            turns = e.get("turns", 0)
            cost = e.get("cost", 0.0)
            model = e.get("model", "unknown")
            ctx = e.get("context_size", 0)
            ctx_str = f"{ctx / 1000:.0f}K" if ctx < 1e6 else f"{ctx / 1e6:.1f}M"
            ts = e.get("ts", "")[:10]
            print(
                f"  {ts}  {turns} turns  ${cost:.2f}  {model}  ctx {ctx_str}",
                file=sys.stdout,
            )
        print("\033[0m", end="", file=sys.stdout)
    except Exception:
        pass


def check_checkpoint():
    """Load checkpoint if recent and not already loaded.

    Checks two locations in priority order:
    1. Project-local: .claude/checkpoint.md (same directory as new session)
    2. Global fallback: ~/.tokenxray/checkpoint.md (written by --checkpoint from any session)
    """
    GLOBAL_CHECKPOINT = Path.home() / ".tokenxray" / "checkpoint.md"

    # Prefer project-local only if it's newer than (or global doesn't exist)
    # This prevents a stale local file from shadowing a fresh global checkpoint
    local = Path.cwd() / ".claude" / "checkpoint.md"
    local_mtime = local.stat().st_mtime if local.exists() else 0
    global_mtime = (
        GLOBAL_CHECKPOINT.stat().st_mtime if GLOBAL_CHECKPOINT.exists() else 0
    )

    if local_mtime == 0 and global_mtime == 0:
        return

    if local_mtime >= global_mtime:
        checkpoint = local
        is_global = False
    else:
        checkpoint = GLOBAL_CHECKPOINT
        is_global = True

    # Only load if recent (< 48 hours)
    try:
        mtime = datetime.fromtimestamp(checkpoint.stat().st_mtime, tz=timezone.utc)
        age_hours = (datetime.now(timezone.utc) - mtime).total_seconds() / 3600
        if age_hours > 48:
            return
    except Exception:
        return

    # Rename to .loaded so we only surface it once
    loaded = checkpoint.with_suffix(".md.loaded")
    try:
        checkpoint.rename(loaded)
    except Exception:
        pass

    age_label = f"{age_hours:.0f}h" if age_hours >= 1 else f"{age_hours * 60:.0f}m"
    read_path = str(loaded) if is_global else ".claude/checkpoint.md.loaded"
    print(
        f"\n[TokenXRay] Previous session checkpoint found ({age_label} ago).",
        file=sys.stdout,
    )
    print(
        f"Read {read_path} to continue where the last session left off.",
        file=sys.stdout,
    )
    print(
        "The checkpoint contains: goal, files modified, recent context, and session stats.",
        file=sys.stdout,
    )


def main():
    cfg = load_config()
    debug_enabled = cfg.get("debug_log", False)
    write_debug("invoked", debug_enabled)
    show_session_history()
    show_last_session_summary()
    check_checkpoint()


if __name__ == "__main__":
    main()
