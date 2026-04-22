"""Checkpoint extraction — extracts working state from session JSONL."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from tokenxray.colors import C
from tokenxray.config import CLAUDE_PROJECTS_DIR, DATA_DIR

GLOBAL_CHECKPOINT = DATA_DIR / "checkpoint.md"


def extract_checkpoint(jsonl_path):
    """Extract working state from a session JSONL file.

    Returns a dict with user_messages, files_edited, files_read,
    commands_run, assistant_summary, cwd, git_branch, session_id.
    """
    user_messages = []
    files_edited = set()
    files_read = set()
    commands_run = []
    assistant_texts = []
    cwd = None
    git_branch = None
    session_id = None

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
                elif isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            text = block.get("text", "")
                            if len(text) > 10 and not text.startswith("<"):
                                user_messages.append(text[:500])
                                break

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


def format_checkpoint(checkpoint):
    """Format checkpoint data as markdown."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    turns = checkpoint.get("turns", 0)
    cost = checkpoint.get("cost", 0)
    model = checkpoint.get("model", "unknown")
    ctx = checkpoint.get("context_size", "?")
    sid = checkpoint.get("session_id", "unknown")
    branch = checkpoint.get("git_branch", "unknown")
    cost_per_turn = cost / turns if turns > 0 else 0

    lines = []
    lines.append("# Session Checkpoint")
    lines.append(f"> Auto-saved by TokenXRay | {now} | {turns} turns | ${cost:.2f} | {model}")
    lines.append(f"> Session: {sid} | Branch: {branch}")
    lines.append("")

    # Original goal
    user_msgs = checkpoint.get("user_messages", [])
    lines.append("## Original Goal")
    if user_msgs:
        lines.append(user_msgs[0])
    else:
        lines.append("*(no user messages captured)*")
    lines.append("")

    # Recent context
    lines.append("## Recent Context")
    recent = user_msgs[-3:] if len(user_msgs) > 1 else []
    if recent:
        for msg in recent:
            lines.append(f"- {msg[:200]}")
    else:
        lines.append("*(no recent messages)*")
    lines.append("")

    # Files modified
    lines.append("## Files Modified")
    edited = checkpoint.get("files_edited", [])
    if edited:
        for fp in edited:
            lines.append(f"- `{fp}`")
    else:
        lines.append("*(none)*")
    lines.append("")

    # Key files read
    lines.append("## Key Files Read")
    read_files = checkpoint.get("files_read", [])
    if read_files:
        for fp in read_files:
            lines.append(f"- `{fp}`")
    else:
        lines.append("*(none)*")
    lines.append("")

    # Recent commands
    lines.append("## Recent Commands")
    cmds = checkpoint.get("commands_run", [])
    if cmds:
        for cmd in cmds:
            lines.append(f"- `{cmd}`")
    else:
        lines.append("*(none)*")
    lines.append("")

    # Last assistant output
    lines.append("## Last Assistant Output")
    summaries = checkpoint.get("assistant_summary", [])
    if summaries:
        for s in summaries[-3:]:
            lines.append(s[:500])
            lines.append("")
    else:
        lines.append("*(none)*")
        lines.append("")

    # Session stats
    lines.append("## Session Stats")
    lines.append(f"- Turns: {turns}")
    lines.append(f"- Cost: ${cost:.2f} (${cost_per_turn:.2f}/turn avg)")
    lines.append(f"- Context: {ctx}")
    lines.append(f"- Model: {model}")
    lines.append(f"- Splitting now saves ~60-70% on continued work")
    lines.append("")
    lines.append("---")
    lines.append("*Auto-generated by TokenXRay. This file is read by the next session automatically.*")
    lines.append("")

    return "\n".join(lines)


def _find_latest_session(path=None):
    """Find the most recently modified JSONL session file."""
    projects_dir = Path(path) if path else CLAUDE_PROJECTS_DIR
    if not projects_dir.exists():
        return None

    latest = None
    latest_mtime = 0
    for jsonl in projects_dir.rglob("*.jsonl"):
        mtime = jsonl.stat().st_mtime
        if mtime > latest_mtime:
            latest_mtime = mtime
            latest = jsonl
    return latest


def run(args):
    """CLI entry point for --checkpoint."""
    print()
    print(f"{C.BOLD}{C.CYAN}TokenXRay — Session Checkpoint{C.RESET}")
    print(f"{C.DIM}{'─' * 70}{C.RESET}")

    jsonl_path = _find_latest_session(getattr(args, "path", None))
    if not jsonl_path:
        print(f"  {C.RED}No session files found.{C.RESET}")
        print()
        return

    print(f"  Extracting from: {C.DIM}{jsonl_path.name}{C.RESET}")

    checkpoint = extract_checkpoint(str(jsonl_path))

    # Count turns/cost from the JSONL for stats
    total_cost = 0.0
    turn_count = 0
    last_ctx = 0
    last_model = "unknown"

    with open(jsonl_path) as f:
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
            from tokenxray.config import get_pricing
            p = get_pricing(last_model)
            inp = usage.get("input_tokens", 0)
            out = usage.get("output_tokens", 0)
            cr = usage.get("cache_read_input_tokens", 0)
            cc = usage.get("cache_creation_input_tokens", 0)
            total_cost += (inp/1e6)*p["input"] + (out/1e6)*p["output"] + (cr/1e6)*p["cache_read"] + (cc/1e6)*p["cache_create"]
            turn_count += 1
            last_ctx = inp + cr + cc

    from tokenxray.config import get_model_label
    checkpoint["turns"] = turn_count
    checkpoint["cost"] = total_cost
    checkpoint["model"] = get_model_label(last_model)
    ctx_str = f"{last_ctx/1000:.0f}K" if last_ctx < 1e6 else f"{last_ctx/1e6:.1f}M"
    checkpoint["context_size"] = ctx_str

    # Write checkpoint — fall back to cwd if session cwd is inaccessible
    cwd = checkpoint.get("cwd") or os.getcwd()
    checkpoint_path = Path(cwd) / ".claude" / "checkpoint.md"
    try:
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    except (PermissionError, OSError):
        checkpoint_path = Path(os.getcwd()) / ".claude" / "checkpoint.md"
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        print(f"  {C.YELLOW}Note: original cwd inaccessible, saving to current directory.{C.RESET}")

    content = format_checkpoint(checkpoint)
    checkpoint_path.write_text(content)

    # Also write to global location so resume hook finds it from any directory
    try:
        GLOBAL_CHECKPOINT.parent.mkdir(parents=True, exist_ok=True)
        GLOBAL_CHECKPOINT.write_text(content)
    except OSError:
        pass

    print(f"  {C.GREEN}{C.BOLD}Checkpoint saved to {checkpoint_path}{C.RESET}")
    print(f"  {turn_count} turns | ${total_cost:.2f} | {len(checkpoint.get('files_edited', []))} files modified")
    print()
