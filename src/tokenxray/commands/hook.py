"""Install Claude Code live cost tracking hook + auto-checkpoint + resume hook."""

import json
import os

from tokenxray.colors import C
from tokenxray.config import DATA_DIR, HOOK_SCRIPT, SETTINGS_FILE

RESUME_HOOK_SCRIPT = DATA_DIR / "resume_hook.py"
SUBAGENT_HOOK_SCRIPT = DATA_DIR / "subagent_hook.py"

HOOK_CODE = '''#!/usr/bin/env python3
"""TokenXRay live cost hook — surfaces session cost + auto-checkpoint.

Runs as a PostToolUse hook. After each tool use:
1. Reads session JSONL to compute cumulative cost, turn count, context size.
2. Shows model + cost/turn info every 10 turns so you know what you're spending.
3. Alerts at cost thresholds ($10, $25, $50, $100, $200, $500).
4. Warns to consider splitting when sessions get expensive.
5. Auto-saves a checkpoint at the split threshold (80 turns or $30).

Model choice is yours — this hook gives you the data to decide.
Use /model to switch anytime.
"""
import json
import sys
import glob
from pathlib import Path
from datetime import datetime, timezone

COST_LOG = Path.home() / ".tokenxray" / "live_session.json"
CONFIG_FILE = Path.home() / ".tokenxray" / "config.json"
PROJECTS_DIR = Path.home() / ".claude" / "projects"
SETTINGS_FILE = Path.home() / ".claude" / "settings.json"
DEBUG_LOG = Path.home() / ".tokenxray" / "debug.log"

# Defaults — override via ~/.tokenxray/config.json
DEFAULT_CONFIG = {
    "split_turns": 60,
    "split_cost": 5,
    "alert_thresholds": [1, 3, 5, 10, 25, 50],
    "status_interval": 10,
    "debug_log": False,
    "hard_stop": False,
    "hard_stop_turns": 120,
    "hard_stop_cost": 50,
    "opus_nudge": True,
    "opus_nudge_turn": 20,
    "opus_nudge_cost": 5.0,
}

def load_config():
    cfg = dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_FILE) as f:
            user = json.load(f)
        cfg.update(user)
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return cfg

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


def write_debug(message, enabled=False):
    """Append diagnostics to ~/.tokenxray/debug.log when enabled."""
    if not enabled:
        return
    try:
        DEBUG_LOG.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with open(DEBUG_LOG, "a") as f:
            f.write(f"[{ts}] cost_hook: {message}\\n")
    except Exception:
        pass


def extract_checkpoint(jsonl_path):
    """Extract working state from session JSONL for auto-checkpoint."""
    user_messages = []
    files_edited = set()
    files_read = set()
    commands_run = []
    assistant_texts = []
    cwd = None
    git_branch = None
    session_id = None

    try:
        with open(jsonl_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                entry_type = entry.get("type", "")

                if entry_type == "user":
                    if not cwd:
                        cwd = entry.get("cwd")
                        git_branch = entry.get("gitBranch")
                        session_id = entry.get("sessionId")
                    msg = entry.get("message", {})
                    content = msg.get("content", "")
                    if isinstance(content, str) and len(content) > 10:
                        if not content.startswith("<") and "tool_result" not in content:
                            user_messages.append(content[:500])

                elif entry_type == "assistant":
                    msg = entry.get("message", {})
                    content = msg.get("content", [])
                    if isinstance(content, list):
                        for block in content:
                            if not isinstance(block, dict):
                                continue
                            if block.get("type") == "text":
                                text = block.get("text", "")
                                if len(text) > 20:
                                    assistant_texts.append(text[:1000])
                            elif block.get("type") == "tool_use":
                                name = block.get("name", "")
                                inp = block.get("input", {})
                                if name in ("Edit", "Write"):
                                    fp = inp.get("file_path", "")
                                    if fp:
                                        files_edited.add(fp)
                                elif name == "Read":
                                    fp = inp.get("file_path", "")
                                    if fp:
                                        files_read.add(fp)
                                elif name == "Bash":
                                    cmd = inp.get("command", "")
                                    if cmd:
                                        commands_run.append(cmd[:200])
    except Exception:
        pass

    return {
        "session_id": session_id,
        "cwd": cwd,
        "git_branch": git_branch,
        "user_messages": user_messages,
        "files_edited": sorted(files_edited),
        "files_read": sorted(files_read)[-20:],
        "commands_run": commands_run[-10:],
        "assistant_summary": assistant_texts[-5:],
    }


def format_checkpoint(cp):
    """Format checkpoint data as markdown."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    turns = cp.get("turns", 0)
    cost = cp.get("cost", 0)
    model = cp.get("model", "unknown")
    ctx = cp.get("context_size", "?")
    sid = cp.get("session_id", "unknown")
    branch = cp.get("git_branch", "unknown")
    cpt = cost / turns if turns > 0 else 0

    lines = []
    lines.append("# Session Checkpoint")
    lines.append(f"> Auto-saved by TokenXRay | {now} | {turns} turns | ${cost:.2f} | {model}")
    lines.append(f"> Session: {sid} | Branch: {branch}")
    lines.append("")

    user_msgs = cp.get("user_messages", [])
    lines.append("## Original Goal")
    lines.append(user_msgs[0] if user_msgs else "*(no user messages captured)*")
    lines.append("")

    lines.append("## Recent Context")
    recent = user_msgs[-3:] if len(user_msgs) > 1 else []
    if recent:
        for msg in recent:
            lines.append(f"- {msg[:200]}")
    else:
        lines.append("*(no recent messages)*")
    lines.append("")

    lines.append("## Files Modified")
    edited = cp.get("files_edited", [])
    if edited:
        for fp in edited:
            lines.append(f"- `{fp}`")
    else:
        lines.append("*(none)*")
    lines.append("")

    lines.append("## Key Files Read")
    read_files = cp.get("files_read", [])
    if read_files:
        for fp in read_files:
            lines.append(f"- `{fp}`")
    else:
        lines.append("*(none)*")
    lines.append("")

    lines.append("## Recent Commands")
    cmds = cp.get("commands_run", [])
    if cmds:
        for cmd in cmds:
            lines.append(f"- `{cmd}`")
    else:
        lines.append("*(none)*")
    lines.append("")

    lines.append("## Last Assistant Output")
    summaries = cp.get("assistant_summary", [])
    if summaries:
        for s in summaries[-3:]:
            lines.append(s[:500])
            lines.append("")
    else:
        lines.append("*(none)*")
        lines.append("")

    lines.append("## Session Stats")
    lines.append(f"- Turns: {turns}")
    lines.append(f"- Cost: ${cost:.2f} (${cpt:.2f}/turn avg)")
    lines.append(f"- Context: {ctx}")
    lines.append(f"- Model: {model}")
    lines.append(f"- Splitting now saves ~60-70% on continued work")
    lines.append("")
    lines.append("---")
    lines.append("*Auto-generated by TokenXRay. This file is read by the next session automatically.*")
    lines.append("")

    return "\\n".join(lines)


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        return

    cfg = load_config()
    debug_enabled = cfg.get("debug_log", False)
    write_debug("invoked", debug_enabled)

    session_id = data.get("session_id", "unknown")
    jsonl_files = glob.glob(str(PROJECTS_DIR / "**" / f"{session_id}.jsonl"), recursive=True)
    if not jsonl_files:
        write_debug("no matching jsonl file found", debug_enabled)
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
    prev_opus_nudge_shown = False
    if COST_LOG.exists():
        try:
            with open(COST_LOG) as f:
                prev = json.load(f)
            if prev.get("session_id") == session_id:
                prev_turns = prev.get("turns", 0)
                prev_alerts = prev.get("alerts", [])
                prev_split_warned = prev.get("split_warned", False)
                prev_opus_nudge_shown = prev.get("opus_nudge_shown", False)
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
        "opus_nudge_shown": prev_opus_nudge_shown,
    }
    COST_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(COST_LOG, "w") as f:
        json.dump(tracker, f)

    new_turn = turn_count > prev_turns

    ctx_str = f"{last_ctx/1000:.0f}K" if last_ctx < 1e6 else f"{last_ctx/1e6:.1f}M"
    cost_per_turn = total_cost / turn_count if turn_count > 0 else 0
    model_label = get_current_model()

    # ─── Hard stop: block further tool use past ceiling (fires every call) ─
    if cfg.get("hard_stop"):
        stop_turns = cfg.get("hard_stop_turns", 120)
        stop_cost = cfg.get("hard_stop_cost", 50)
        if turn_count >= stop_turns or total_cost >= stop_cost:
            reason = f"turn limit ({turn_count}/{stop_turns})" if turn_count >= stop_turns else f"cost limit (${total_cost:.2f}/${stop_cost})"
            checkpoint_note = (
                "Checkpoint was auto-saved earlier."
                if prev_split_warned
                else "Run: tokenxray --checkpoint to save your work before closing."
            )
            print(
                f"\\n\\033[1m\\033[31m[TokenXRay] HARD STOP \\u2014 {reason} reached. "
                f"Session blocked.\\033[0m\\n"
                f"\\033[1mPlease wrap up and start a fresh session.\\033[0m\\n"
                f"\\033[2m{checkpoint_note} "
                f"Disable with: hard_stop=false in ~/.tokenxray/config.json\\033[0m",
                file=sys.stdout,
            )
            write_debug(f"hard_stop triggered: {reason}", debug_enabled)
            sys.exit(2)

    # ─── Cost threshold alerts (fire even without new turn) ──────────────
    new_threshold = False
    for t in cfg["alert_thresholds"]:
        if total_cost >= t and t not in prev_alerts:
            new_threshold = True
            tracker["alerts"].append(t)
            with open(COST_LOG, "w") as f:
                json.dump(tracker, f)
            print(
                f"\\n\\033[1m\\033[33m[TokenXRay] ${total_cost:.2f} spent "
                f"(crossed ${t}) \\u2014 {model_label}, {turn_count} turns, "
                f"ctx {ctx_str}, ~${cost_per_turn:.2f}/turn\\033[0m",
                file=sys.stdout,
            )
            write_debug(f"threshold alert fired at ${t}", debug_enabled)
            return

    # Below here, only act on new turns to avoid duplicates
    if not new_turn:
        return

    # ─── Opus nudge (once per session) ──────────────────────────────────
    if cfg.get("opus_nudge", True) and not tracker.get("opus_nudge_shown"):
        nudge_turn = cfg.get("opus_nudge_turn", 20)
        nudge_cost = cfg.get("opus_nudge_cost", 5.0)
        if "opus" in last_model.lower() and (turn_count >= nudge_turn or total_cost >= nudge_cost):
            tracker["opus_nudge_shown"] = True
            with open(COST_LOG, "w") as f:
                json.dump(tracker, f)
            print(
                f"\\n\\033[1m\\033[35m[TokenXRay] You\\'re on Opus ($15/MTok input) \\u2014 "
                f"Sonnet costs 5x less and handles most coding tasks well.\\033[0m\\n"
                f"\\033[1m\\033[35mConsider switching: /model claude-sonnet-4-6\\033[0m\\n"
                f"\\033[2m[TokenXRay] Disable: set opus_nudge=false in ~/.tokenxray/config.json\\033[0m",
                file=sys.stdout,
            )

    # ─── Split session warning + auto-checkpoint ────────────────────────
    if not tracker.get("split_warned") and (turn_count > cfg["split_turns"] or total_cost >= cfg["split_cost"]):
        tracker["split_warned"] = True
        with open(COST_LOG, "w") as f:
            json.dump(tracker, f)

        # Auto-checkpoint: extract session state and save
        try:
            cp = extract_checkpoint(jsonl_files[0])
            cp["turns"] = turn_count
            cp["cost"] = total_cost
            cp["model"] = model_label
            cp["context_size"] = ctx_str

            cp_path = Path(cp.get("cwd") or ".") / ".claude" / "checkpoint.md"
            cp_path.parent.mkdir(parents=True, exist_ok=True)
            cp_path.write_text(format_checkpoint(cp))

            print(
                f"\\n\\033[1m\\033[31m[TokenXRay] Consider splitting this session! "
                f"({turn_count} turns, ${total_cost:.2f}, ctx {ctx_str}) "
                f"\\u2014 marathon sessions burn 92% of budget\\033[0m",
                file=sys.stdout,
            )
            print(
                f"\\033[1m\\033[32m[TokenXRay] Auto-checkpoint saved to {cp_path}\\033[0m",
                file=sys.stdout,
            )
            print(
                f"\\033[2m[TokenXRay] Start a fresh session \\u2014 your context will be restored automatically.\\033[0m",
                file=sys.stdout,
            )
            write_debug("split warning shown and checkpoint saved", debug_enabled)
        except Exception:
            # Still show the split warning even if checkpoint fails
            print(
                f"\\n\\033[1m\\033[31m[TokenXRay] Consider splitting this session! "
                f"({turn_count} turns, ${total_cost:.2f}, ctx {ctx_str}) "
                f"\\u2014 marathon sessions burn 92% of budget\\033[0m",
                file=sys.stdout,
            )
            write_debug("split warning shown but checkpoint save failed", debug_enabled)

    # ─── Cost status every N turns — stdout so Claude sees it ─────────
    past_threshold = len(tracker["alerts"]) > 0
    if past_threshold or turn_count % cfg["status_interval"] == 0:
        print(
            f"\\033[2m[TokenXRay] {model_label} \\u2014 turn {turn_count}, "
            f"${total_cost:.2f} total, ~${cost_per_turn:.2f}/turn, "
            f"ctx {ctx_str}\\033[0m",
            file=sys.stdout,
        )
        write_debug("status line emitted", debug_enabled)

if __name__ == "__main__":
    main()
'''

RESUME_HOOK_CODE = '''#!/usr/bin/env python3
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
            f.write(f"[{ts}] resume_hook: {message}\\n")
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

    ctx_str = f"{ctx/1000:.0f}K" if ctx < 1e6 else f"{ctx/1e6:.1f}M"
    cost_per_turn = cost / turns

    print(
        f"\\033[2m[TokenXRay] Last session: {turns} turns, "
        f"${cost:.2f} total, ~${cost_per_turn:.2f}/turn, "
        f"{model}, ctx {ctx_str}\\033[0m",
        file=sys.stderr,
    )

    # Mark as shown
    try:
        SUMMARY_SHOWN.write_text(prev_session)
    except Exception:
        pass


def check_checkpoint():
    """Load checkpoint if recent and not already loaded."""
    checkpoint = Path.cwd() / ".claude" / "checkpoint.md"
    if not checkpoint.exists():
        return

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
    print(
        f"\\n[TokenXRay] Previous session checkpoint found ({age_label} ago).",
        file=sys.stdout,
    )
    print(
        f"Read .claude/checkpoint.md.loaded to continue where the last session left off.",
        file=sys.stdout,
    )
    print(
        f"The checkpoint contains: goal, files modified, recent context, and session stats.",
        file=sys.stdout,
    )


def main():
    cfg = load_config()
    debug_enabled = cfg.get("debug_log", False)
    write_debug("invoked", debug_enabled)
    show_last_session_summary()
    check_checkpoint()

if __name__ == "__main__":
    main()
'''


SUBAGENT_HOOK_CODE = '''#!/usr/bin/env python3
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
            f.write(f"subagent_hook: {message}\\n")
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
        # Guard: don\\'t merge into a stale session
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
        write_debug("no live state for session", debug_enabled)
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
            f"\\n\\033[1m\\033[33m[TokenXRay] Agent call — subagents spawn a full context "
            f"and cost significantly more per task.\\033[0m\\n"
            f"\\033[2m[TokenXRay] Session: {turn_count} turns, ${total_cost:.2f} so far "
            f"(~${cost_per_turn:.2f}/turn), {model}\\033[0m\\n"
            f"\\033[2m[TokenXRay] Disable: set subagent_warn=false in ~/.tokenxray/config.json\\033[0m",
            file=sys.stdout,
        )
    elif interval > 0 and call_count % interval == 0:
        print(
            f"\\033[2m[TokenXRay] Agent call #{call_count} this session — "
            f"${total_cost:.2f} total so far.\\033[0m",
            file=sys.stdout,
        )


if __name__ == "__main__":
    main()
'''


def run(args):
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Write the cost hook script
    with open(HOOK_SCRIPT, "w") as f:
        f.write(HOOK_CODE)
    os.chmod(HOOK_SCRIPT, 0o755)

    # Write the resume hook script
    with open(RESUME_HOOK_SCRIPT, "w") as f:
        f.write(RESUME_HOOK_CODE)
    os.chmod(RESUME_HOOK_SCRIPT, 0o755)

    # Write the subagent hook script
    with open(SUBAGENT_HOOK_SCRIPT, "w") as f:
        f.write(SUBAGENT_HOOK_CODE)
    os.chmod(SUBAGENT_HOOK_SCRIPT, 0o755)

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
    user_prompt = hooks.get("UserPromptSubmit", [])
    pre_tool = hooks.get("PreToolUse", [])

    cost_hook_installed = any(
        str(HOOK_SCRIPT) in str(h.get("hooks", []))
        for h in post_tool if isinstance(h, dict)
    )
    resume_hook_installed = any(
        str(RESUME_HOOK_SCRIPT) in str(h.get("hooks", []))
        for h in user_prompt if isinstance(h, dict)
    )
    subagent_hook_installed = any(
        str(SUBAGENT_HOOK_SCRIPT) in str(h.get("hooks", []))
        for h in pre_tool if isinstance(h, dict)
    )

    both_installed = cost_hook_installed and resume_hook_installed and subagent_hook_installed

    if both_installed:
        print(f"{C.GREEN}Hooks already installed! Scripts updated at {DATA_DIR}{C.RESET}")
        return

    print()
    print(f"{C.BOLD}{C.CYAN}TokenXRay — Install Live Cost + Auto-Checkpoint Hooks{C.RESET}")
    print(f"{C.DIM}{'─' * 70}{C.RESET}")
    print(f"  Cost hook:     {HOOK_SCRIPT}")
    print(f"  Resume hook:   {RESUME_HOOK_SCRIPT}")
    print(f"  Subagent hook: {SUBAGENT_HOOK_SCRIPT}")
    print(f"  Tracks cost, auto-checkpoints at split threshold, warns on Agent calls")
    print()

    if getattr(args, "confirm", False):
        if not cost_hook_installed:
            hook_entry = {
                "matcher": ".*",
                "hooks": [{"type": "command", "command": f"python3 {HOOK_SCRIPT}"}],
            }
            if not isinstance(post_tool, list):
                post_tool = []
            post_tool.append(hook_entry)
            hooks["PostToolUse"] = post_tool

        if not resume_hook_installed:
            resume_entry = {
                "matcher": "",
                "hooks": [{"type": "command", "command": f"python3 {RESUME_HOOK_SCRIPT}"}],
            }
            if not isinstance(user_prompt, list):
                user_prompt = []
            user_prompt.append(resume_entry)
            hooks["UserPromptSubmit"] = user_prompt

        if not subagent_hook_installed:
            subagent_entry = {
                "matcher": "Agent",
                "hooks": [{"type": "command", "command": f"python3 {SUBAGENT_HOOK_SCRIPT}"}],
            }
            if not isinstance(pre_tool, list):
                pre_tool = []
            pre_tool.append(subagent_entry)
            hooks["PreToolUse"] = pre_tool

        settings["hooks"] = hooks

        with open(SETTINGS_FILE, "w") as f:
            json.dump(settings, f, indent=2)

        print(f"  {C.GREEN}{C.BOLD}Hooks installed! Restart Claude Code to activate.{C.RESET}")
    else:
        print(f"  Run: {C.BOLD}tokenxray --install-hook --confirm{C.RESET} to auto-install")

    print()
