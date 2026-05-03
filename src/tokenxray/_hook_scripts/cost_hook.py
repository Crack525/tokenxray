#!/usr/bin/env python3
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

TOKENXRAY_HOOK_VERSION = "%%TOKENXRAY_VERSION%%"

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
    "trajectory_warn_turn": 30,
    "trajectory_warn_cost": 8.0,
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


PRICING_FILE = Path.home() / ".tokenxray" / "pricing.json"


def _load_pricing():
    try:
        with open(PRICING_FILE) as f:
            data = json.load(f)
        return data.get("pricing", {}), data.get(
            "default",
            {
                "input": 3.0,
                "output": 15.0,
                "cache_read": 0.30,
                "cache_create": 3.75,
                "label": "unknown",
            },
        )
    except (FileNotFoundError, json.JSONDecodeError):
        return {}, {
            "input": 3.0,
            "output": 15.0,
            "cache_read": 0.30,
            "cache_create": 3.75,
            "label": "unknown",
        }


_PRICING, _DEFAULT = _load_pricing()


def get_pricing(model):
    if model in _PRICING:
        return _PRICING[model]
    for key, p in _PRICING.items():
        if model.startswith(key.split("-202")[0]):
            return p
    return _DEFAULT


def get_current_model(fallback=""):
    """Read current model label from settings.json, fallback to last seen JSONL model."""
    try:
        with open(SETTINGS_FILE) as f:
            model = json.load(f).get("model", "")
    except (FileNotFoundError, json.JSONDecodeError):
        model = ""
    if not model:
        model = fallback
    return get_pricing(model)["label"]


def write_debug(message, enabled=False):
    """Append diagnostics to ~/.tokenxray/debug.log when enabled."""
    if not enabled:
        return
    try:
        DEBUG_LOG.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with open(DEBUG_LOG, "a") as f:
            f.write(f"[{ts}] cost_hook: {message}\n")
    except Exception:
        pass


_HOOK_MARKERS = ("\nRan ", "\nRead skill [", "Completed with input:", "tool_result")


def _is_hook_injected(text):
    return any(m in text for m in _HOOK_MARKERS)


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
                    if entry.get("agentId"):
                        continue
                    if not cwd:
                        cwd = entry.get("cwd")
                        git_branch = entry.get("gitBranch")
                        session_id = entry.get("sessionId")
                    msg = entry.get("message", {})
                    content = msg.get("content", "")
                    if isinstance(content, str) and len(content) > 10:
                        if not content.startswith("<") and not _is_hook_injected(
                            content
                        ):
                            user_messages.append(content[:500])
                    elif isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "text":
                                text = block.get("text", "")
                                if (
                                    len(text) > 10
                                    and not text.startswith("<")
                                    and not _is_hook_injected(text)
                                ):
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
    lines.append(
        f"> Auto-saved by TokenXRay | {now} | {turns} turns | ${cost:.2f} | {model}"
    )
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
    lines.append("- Splitting now saves ~60-70% on continued work")
    lines.append("")
    lines.append("---")
    lines.append(
        "*Auto-generated by TokenXRay. This file is read by the next session automatically.*"
    )
    lines.append("")

    return "\n".join(lines)


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        return

    cfg = load_config()
    debug_enabled = cfg.get("debug_log", False)
    write_debug("invoked", debug_enabled)

    session_id = data.get("session_id", "unknown")
    jsonl_files = glob.glob(
        str(PROJECTS_DIR / "**" / f"{session_id}.jsonl"), recursive=True
    )
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
                total_cost += (
                    (inp / 1e6) * p["input"]
                    + (out / 1e6) * p["output"]
                    + (cr / 1e6) * p["cache_read"]
                    + (cc / 1e6) * p["cache_create"]
                )
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
    prev_trajectory_warned = False
    prev_pre_stop_saved = False
    if COST_LOG.exists():
        try:
            with open(COST_LOG) as f:
                prev = json.load(f)
            if prev.get("session_id") == session_id:
                prev_turns = prev.get("turns", 0)
                prev_alerts = prev.get("alerts", [])
                prev_split_warned = prev.get("split_warned", False)
                prev_opus_nudge_shown = prev.get("opus_nudge_shown", False)
                prev_trajectory_warned = prev.get("trajectory_warned", False)
                prev_pre_stop_saved = prev.get("pre_stop_saved", False)
        except (json.JSONDecodeError, KeyError):
            pass

    tracker = {
        "session_id": session_id,
        "total_cost": total_cost,
        "turns": turn_count,
        "alerts": prev_alerts,
        "context_size": last_ctx,
        "model": get_current_model(last_model),
        "split_warned": prev_split_warned,
        "opus_nudge_shown": prev_opus_nudge_shown,
        "trajectory_warned": prev_trajectory_warned,
        "pre_stop_saved": prev_pre_stop_saved,
    }
    COST_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(COST_LOG, "w") as f:
        json.dump(tracker, f)

    new_turn = turn_count > prev_turns

    ctx_str = f"{last_ctx / 1000:.0f}K" if last_ctx < 1e6 else f"{last_ctx / 1e6:.1f}M"
    cost_per_turn = total_cost / turn_count if turn_count > 0 else 0
    model_label = get_current_model(last_model)

    # ─── Pre-hardstop: silent checkpoint at 80% of ceiling ──────────────
    if cfg.get("hard_stop") and not tracker.get("pre_stop_saved"):
        stop_turns = cfg.get("hard_stop_turns", 120)
        stop_cost = cfg.get("hard_stop_cost", 50)
        if turn_count >= stop_turns * 0.8 or total_cost >= stop_cost * 0.8:
            try:
                cp = extract_checkpoint(jsonl_files[0])
                cp["turns"] = turn_count
                cp["cost"] = total_cost
                cp["model"] = model_label
                cp["context_size"] = ctx_str
                cp_path = Path(cp.get("cwd") or ".") / ".claude" / "checkpoint.md"
                cp_path.parent.mkdir(parents=True, exist_ok=True)
                cp_content = format_checkpoint(cp)
                cp_path.write_text(cp_content)
                global_cp = Path.home() / ".tokenxray" / "checkpoint.md"
                try:
                    global_cp.parent.mkdir(parents=True, exist_ok=True)
                    global_cp.write_text(cp_content)
                except OSError:
                    pass
            except Exception:
                pass
            tracker["pre_stop_saved"] = True
            with open(COST_LOG, "w") as f:
                json.dump(tracker, f)
            write_debug(
                f"pre-hardstop checkpoint saved at turn {turn_count}", debug_enabled
            )

    # ─── Hard stop: block further tool use past ceiling (fires every call) ─
    if cfg.get("hard_stop"):
        stop_turns = cfg.get("hard_stop_turns", 120)
        stop_cost = cfg.get("hard_stop_cost", 50)
        if turn_count >= stop_turns or total_cost >= stop_cost:
            reason = (
                f"turn limit ({turn_count}/{stop_turns})"
                if turn_count >= stop_turns
                else f"cost limit (${total_cost:.2f}/${stop_cost})"
            )
            checkpoint_note = (
                "Checkpoint was auto-saved earlier."
                if prev_split_warned
                else "Run: tokenxray --checkpoint to save your work before closing."
            )
            print(
                f"\n\033[1m\033[31m[TokenXRay] HARD STOP \u2014 {reason} reached. "
                f"Session blocked.\033[0m\n"
                f"\033[1mPlease wrap up and start a fresh session.\033[0m\n"
                f"\033[2m{checkpoint_note} "
                f"Disable with: hard_stop=false in ~/.tokenxray/config.json\033[0m",
                file=sys.stdout,
            )
            write_debug(f"hard_stop triggered: {reason}", debug_enabled)
            sys.exit(2)

    # ─── Cost threshold alerts (fire even without new turn) ──────────────
    for t in cfg["alert_thresholds"]:
        if total_cost >= t and t not in prev_alerts:
            tracker["alerts"].append(t)
            with open(COST_LOG, "w") as f:
                json.dump(tracker, f)
            print(
                f"\n\033[1m\033[33m[TokenXRay] ${total_cost:.2f} spent "
                f"(crossed ${t}) \u2014 {model_label}, {turn_count} turns, "
                f"ctx {ctx_str}, ~${cost_per_turn:.2f}/turn\033[0m",
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
        if "opus" in last_model.lower() and (
            turn_count >= nudge_turn or total_cost >= nudge_cost
        ):
            tracker["opus_nudge_shown"] = True
            with open(COST_LOG, "w") as f:
                json.dump(tracker, f)
            print(
                "\n\033[1m\033[35m[TokenXRay] You're on Opus ($15/MTok input) \u2014 "
                "Sonnet costs 5x less and handles most coding tasks well.\033[0m\n"
                "\033[1m\033[35mConsider switching: /model claude-sonnet-4-6\033[0m\n"
                "\033[2m[TokenXRay] Disable: set opus_nudge=false in ~/.tokenxray/config.json\033[0m",
                file=sys.stdout,
            )

    # ─── Trajectory projection: early warning before split threshold ─────
    if not tracker.get("trajectory_warned") and turn_count >= cfg.get(
        "trajectory_warn_turn", 30
    ):
        warn_cost = cfg.get("trajectory_warn_cost", 8.0)
        horizon = cfg.get("hard_stop_turns", 120) if cfg.get("hard_stop") else 200
        projected = cost_per_turn * horizon
        if projected >= warn_cost:
            tracker["trajectory_warned"] = True
            with open(COST_LOG, "w") as f:
                json.dump(tracker, f)
            print(
                f"\n\033[1m\033[33m[TokenXRay] Trajectory alert: at ${cost_per_turn:.3f}/turn, "
                f"this session projects to ${projected:.1f} over {horizon} turns. "
                f"Scope remaining work or split now.\033[0m",
                file=sys.stdout,
            )
            write_debug(
                f"trajectory alert fired at turn {turn_count}, projected ${projected:.1f}",
                debug_enabled,
            )

    # ─── Split session warning + auto-checkpoint ────────────────────────
    if not tracker.get("split_warned") and (
        turn_count > cfg["split_turns"] or total_cost >= cfg["split_cost"]
    ):
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
            cp_content = format_checkpoint(cp)
            cp_path.write_text(cp_content)
            # Also write global so resume hook finds it from any directory
            global_cp = Path.home() / ".tokenxray" / "checkpoint.md"
            try:
                global_cp.parent.mkdir(parents=True, exist_ok=True)
                global_cp.write_text(cp_content)
            except OSError:
                pass

            print(
                f"\n\033[1m\033[31m[TokenXRay] Consider splitting this session! "
                f"({turn_count} turns, ${total_cost:.2f}, ctx {ctx_str}) "
                f"\u2014 marathon sessions burn 92% of budget\033[0m",
                file=sys.stdout,
            )
            print(
                f"\033[1m\033[32m[TokenXRay] Auto-checkpoint saved to {cp_path}\033[0m",
                file=sys.stdout,
            )
            print(
                "\033[2m[TokenXRay] Start a fresh session \u2014 your context will be restored automatically.\033[0m",
                file=sys.stdout,
            )
            write_debug("split warning shown and checkpoint saved", debug_enabled)
        except Exception:
            # Still show the split warning even if checkpoint fails
            print(
                f"\n\033[1m\033[31m[TokenXRay] Consider splitting this session! "
                f"({turn_count} turns, ${total_cost:.2f}, ctx {ctx_str}) "
                f"\u2014 marathon sessions burn 92% of budget\033[0m",
                file=sys.stdout,
            )
            write_debug("split warning shown but checkpoint save failed", debug_enabled)

    # ─── Cost status every N turns — stdout so Claude sees it ─────────
    past_threshold = len(tracker["alerts"]) > 0
    if past_threshold or turn_count % cfg["status_interval"] == 0:
        print(
            f"\033[2m[TokenXRay] {model_label} \u2014 turn {turn_count}, "
            f"${total_cost:.2f} total, ~${cost_per_turn:.2f}/turn, "
            f"ctx {ctx_str}\033[0m",
            file=sys.stdout,
        )
        write_debug("status line emitted", debug_enabled)


if __name__ == "__main__":
    main()
