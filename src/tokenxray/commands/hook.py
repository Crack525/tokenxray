"""Install Claude Code live cost tracking hook + auto-checkpoint + resume hook."""

import json
import os

from tokenxray.colors import C
from tokenxray.config import DATA_DIR, HOOK_SCRIPT, SETTINGS_FILE, LIVE_SESSION_FILE

RESUME_HOOK_SCRIPT = DATA_DIR / "resume_hook.py"

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

# Defaults — override via ~/.tokenxray/config.json
DEFAULT_CONFIG = {
    "split_turns": 80,
    "split_cost": 30,
    "alert_thresholds": [10, 25, 50, 100, 200, 500],
    "status_interval": 10,
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
                file=sys.stderr,
            )
            print(
                f"\\033[1m\\033[32m[TokenXRay] Auto-checkpoint saved to {cp_path}\\033[0m",
                file=sys.stderr,
            )
            print(
                f"\\033[2m[TokenXRay] Start a fresh session \\u2014 your context will be restored automatically.\\033[0m",
                file=sys.stderr,
            )
        except Exception:
            # Still show the split warning even if checkpoint fails
            print(
                f"\\n\\033[1m\\033[31m[TokenXRay] Consider splitting this session! "
                f"({turn_count} turns, ${total_cost:.2f}, ctx {ctx_str}) "
                f"\\u2014 marathon sessions burn 92% of budget\\033[0m",
                file=sys.stderr,
            )

    # ─── Cost threshold alerts ───────────────────────────────────────────
    for t in cfg["alert_thresholds"]:
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
    if turn_count % cfg["status_interval"] == 0:
        print(
            f"\\033[2m[TokenXRay] {model_label} \\u2014 turn {turn_count}, "
            f"${total_cost:.2f} total, ~${cost_per_turn:.2f}/turn, "
            f"ctx {ctx_str}\\033[0m",
            file=sys.stderr,
        )

if __name__ == "__main__":
    main()
'''

RESUME_HOOK_CODE = '''#!/usr/bin/env python3
"""TokenXRay resume hook — auto-loads checkpoint in new sessions.

Runs as a UserPromptSubmit hook. On each user message:
1. Checks if .claude/checkpoint.md exists in the current directory.
2. If found and recent (< 48 hours), tells Claude to read it.
3. Renames checkpoint after first load so it only fires once per session.
"""
import sys
from pathlib import Path
from datetime import datetime, timezone

def main():
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
        file=sys.stderr,
    )
    print(
        f"Read .claude/checkpoint.md.loaded to continue where the last session left off.",
        file=sys.stderr,
    )
    print(
        f"The checkpoint contains: goal, files modified, recent context, and session stats.",
        file=sys.stderr,
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

    cost_hook_installed = any(
        str(HOOK_SCRIPT) in str(h.get("hooks", []))
        for h in post_tool if isinstance(h, dict)
    )
    resume_hook_installed = any(
        str(RESUME_HOOK_SCRIPT) in str(h.get("hooks", []))
        for h in user_prompt if isinstance(h, dict)
    )

    both_installed = cost_hook_installed and resume_hook_installed

    if both_installed:
        print(f"{C.GREEN}Hooks already installed! Scripts updated at {DATA_DIR}{C.RESET}")
        return

    print()
    print(f"{C.BOLD}{C.CYAN}TokenXRay — Install Live Cost + Auto-Checkpoint Hooks{C.RESET}")
    print(f"{C.DIM}{'─' * 70}{C.RESET}")
    print(f"  Cost hook:   {HOOK_SCRIPT}")
    print(f"  Resume hook: {RESUME_HOOK_SCRIPT}")
    print(f"  Tracks cost, auto-checkpoints at 80 turns/$30, auto-resumes next session")
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

        settings["hooks"] = hooks

        with open(SETTINGS_FILE, "w") as f:
            json.dump(settings, f, indent=2)

        print(f"  {C.GREEN}{C.BOLD}Hooks installed! Restart Claude Code to activate.{C.RESET}")
    else:
        print(f"  Run: {C.BOLD}tokenxray --install-hook --confirm{C.RESET} to auto-install")

    print()
