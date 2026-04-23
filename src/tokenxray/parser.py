"""Session parsing and cost calculation for Claude Code and Gemini CLI."""

import json
import glob
import sys
from datetime import datetime
from pathlib import Path
from collections import defaultdict

from tokenxray.config import CLAUDE_PROJECTS_DIR, GEMINI_SESSIONS_DIR, COPILOT_WORKSPACE_DIR, get_pricing


def find_session_files(base_path=None):
    """Find all Claude Code JSONL conversation logs, excluding subagent files."""
    path = Path(base_path) if base_path else CLAUDE_PROJECTS_DIR
    if not path.exists():
        return []
    return sorted(
        f for f in glob.glob(str(path / "**/*.jsonl"), recursive=True)
        if "subagents" not in Path(f).parts
    )


def find_gemini_session_files():
    """Find all Gemini CLI session JSON files."""
    if not GEMINI_SESSIONS_DIR.exists():
        return []
    return sorted(glob.glob(str(GEMINI_SESSIONS_DIR / "*/chats/session-*.json")))


def parse_session(filepath):
    """Parse a single session JSONL file into structured data."""
    entries = []
    with open(filepath) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    session = {
        "file": filepath,
        "id": Path(filepath).stem[:12],
        "full_id": Path(filepath).stem,
        "project": Path(filepath).parent.name,
        "turns": [],
        "user_messages": [],
        "tool_calls": defaultdict(int),
        "tool_results_chars": 0,
        "assistant_output_chars": 0,
        "models_used": set(),
        "start_time": None,
        "end_time": None,
        "total_input": 0,
        "total_output": 0,
        "total_cache_read": 0,
        "total_cache_create": 0,
    }

    for entry in entries:
        etype = entry.get("type")

        ts = entry.get("timestamp")
        if ts:
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                if session["start_time"] is None:
                    session["start_time"] = dt
                session["end_time"] = dt
            except (ValueError, AttributeError):
                pass

        if etype == "assistant":
            _parse_assistant_entry(entry, session)
        elif etype == "user":
            _parse_user_entry(entry, session)

    session["models_used"] = list(session["models_used"])
    return session


def _parse_assistant_entry(entry, session):
    msg = entry.get("message", {})
    usage = msg.get("usage", {})
    model = msg.get("model", "unknown")
    session["models_used"].add(model)

    if usage:
        inp = usage.get("input_tokens", 0)
        out = usage.get("output_tokens", 0)
        cr = usage.get("cache_read_input_tokens", 0)
        cc = usage.get("cache_creation_input_tokens", 0)

        session["total_input"] += inp
        session["total_output"] += out
        session["total_cache_read"] += cr
        session["total_cache_create"] += cc

        session["turns"].append({
            "num": len(session["turns"]) + 1,
            "input": inp, "output": out,
            "cache_read": cr, "cache_create": cc,
            "total_sent": inp + cr + cc,
            "model": model,
        })

    content = msg.get("content", [])
    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use":
                session["tool_calls"][block.get("name", "unknown")] += 1
            elif block.get("type") == "text":
                session["assistant_output_chars"] += len(block.get("text", ""))


def _parse_user_entry(entry, session):
    msg = entry.get("message", {})
    content = msg.get("content", "")

    if isinstance(content, str) and 10 < len(content) < 5000:
        session["user_messages"].append(len(content))
    elif isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_result":
                result = block.get("content", "")
                if isinstance(result, str):
                    session["tool_results_chars"] += len(result)
                elif isinstance(result, list):
                    for rc in result:
                        if isinstance(rc, dict):
                            session["tool_results_chars"] += len(str(rc.get("text", "")))
            elif block.get("type") == "text":
                text = block.get("text", "")
                if 10 < len(text) < 5000:
                    session["user_messages"].append(len(text))


def _pick_model(models_used):
    """Pick a representative model for display/fallback, skipping <synthetic>."""
    real = sorted(m for m in models_used if m != "<synthetic>")
    if real:
        return real[0]
    return "claude-opus-4-6"


def calc_cost(session):
    """Calculate session cost with per-turn model-specific pricing.

    Each turn is priced using its own model so mixed-model sessions (e.g. a
    session that switched from Opus to Sonnet mid-way) are costed accurately
    and deterministically regardless of set ordering.

    Falls back to session-level aggregate pricing for sessions without per-turn
    model data (e.g. some Gemini/Copilot edge cases).
    """
    turns = session.get("turns", [])

    if turns:
        input_cost = 0.0
        output_cost = 0.0
        cache_read_cost = 0.0
        cache_create_cost = 0.0
        total_no_cache = 0.0

        for turn in turns:
            model = turn.get("model", "unknown")
            if model in ("<synthetic>", "unknown"):
                model = _pick_model(session["models_used"])
            pricing = get_pricing(model)

            inp = turn.get("input", 0)
            out = turn.get("output", 0)
            cr = turn.get("cache_read", 0)
            cc = turn.get("cache_create", 0)

            input_cost += (inp / 1e6) * pricing["input"]
            output_cost += (out / 1e6) * pricing["output"]
            cache_read_cost += (cr / 1e6) * pricing["cache_read"]
            cache_create_cost += (cc / 1e6) * pricing["cache_create"]
            total_no_cache += ((inp + cr + cc) / 1e6) * pricing["input"] + (out / 1e6) * pricing["output"]

        total = input_cost + output_cost + cache_read_cost + cache_create_cost
        pricing = get_pricing(_pick_model(session["models_used"]))
    else:
        # No per-turn data — fall back to session-level aggregate
        pricing = get_pricing(_pick_model(session["models_used"]))
        input_cost = (session["total_input"] / 1e6) * pricing["input"]
        output_cost = (session["total_output"] / 1e6) * pricing["output"]
        cache_read_cost = (session["total_cache_read"] / 1e6) * pricing["cache_read"]
        cache_create_cost = (session["total_cache_create"] / 1e6) * pricing["cache_create"]
        total = input_cost + output_cost + cache_read_cost + cache_create_cost
        total_no_cache = (
            (session["total_input"] + session["total_cache_read"] + session["total_cache_create"])
            / 1e6 * pricing["input"]
        ) + output_cost

    return {
        "input": input_cost,
        "output": output_cost,
        "cache_read": cache_read_cost,
        "cache_create": cache_create_cost,
        "total": total,
        "total_no_cache": total_no_cache,
        "cache_savings": total_no_cache - total,
        "pricing": pricing,
    }


def parse_gemini_session(filepath):
    """Parse a single Gemini CLI session JSON file into structured data."""
    with open(filepath) as f:
        data = json.load(f)

    session_id = data.get("sessionId", Path(filepath).stem)
    project_hash = data.get("projectHash", "unknown")

    session = {
        "file": filepath,
        "id": session_id[:12],
        "full_id": session_id,
        "project": f"gemini/{project_hash[:8]}",
        "source": "gemini",
        "turns": [],
        "user_messages": [],
        "tool_calls": defaultdict(int),
        "tool_results_chars": 0,
        "assistant_output_chars": 0,
        "models_used": set(),
        "start_time": None,
        "end_time": None,
        "total_input": 0,
        "total_output": 0,
        "total_cache_read": 0,
        "total_cache_create": 0,
    }

    # Parse timestamps
    for ts_field in ("startTime", "lastUpdated"):
        ts = data.get(ts_field)
        if ts:
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                if ts_field == "startTime":
                    session["start_time"] = dt
                else:
                    session["end_time"] = dt
            except (ValueError, AttributeError):
                pass

    for msg in data.get("messages", []):
        if msg.get("type") == "user":
            content = msg.get("content", "")
            if isinstance(content, str) and 10 < len(content) < 5000:
                session["user_messages"].append(len(content))
            continue

        if msg.get("type") != "gemini":
            continue

        tokens = msg.get("tokens")
        if not tokens:
            continue

        model = msg.get("model", "unknown")
        session["models_used"].add(model)

        # Gemini token structure:
        # input = total input (includes cached portion)
        # cached = portion of input served from cache
        # output = output tokens
        # thoughts = thinking tokens (billed at output rate)
        # tool = tool-use tokens
        inp_total = tokens.get("input", 0)
        cached = tokens.get("cached", 0)
        output = tokens.get("output", 0)
        thoughts = tokens.get("thoughts", 0)
        fresh_input = inp_total - cached

        # Map to our structure:
        # fresh input → total_input
        # cached → total_cache_read (cheaper rate)
        # No cache_create concept in Gemini
        # thoughts billed at output rate → add to output
        session["total_input"] += fresh_input
        session["total_cache_read"] += cached
        session["total_output"] += output + thoughts

        session["turns"].append({
            "num": len(session["turns"]) + 1,
            "input": fresh_input,
            "output": output + thoughts,
            "cache_read": cached,
            "cache_create": 0,
            "total_sent": inp_total,
            "model": model,
        })

        # Count tool calls
        for tc in msg.get("toolCalls", []):
            session["tool_calls"][tc.get("name", "unknown")] += 1

        content = msg.get("content", "")
        if isinstance(content, str):
            session["assistant_output_chars"] += len(content)

    session["models_used"] = list(session["models_used"])
    return session


def find_copilot_session_files():
    """Find all GitHub Copilot transcript JSONL files."""
    if not COPILOT_WORKSPACE_DIR.exists():
        return []
    return sorted(glob.glob(
        str(COPILOT_WORKSPACE_DIR / "*/GitHub.copilot-chat/transcripts/*.jsonl")
    ))


def parse_copilot_session(filepath):
    """Parse a GitHub Copilot transcript JSONL file.

    Note: Copilot transcripts don't include token usage data (marked ephemeral
    in the schema). We estimate tokens from message character counts (~4 chars/token).
    """
    entries = []
    with open(filepath) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    session_id = Path(filepath).stem
    # workspace hash from path
    ws_hash = Path(filepath).parent.parent.parent.name[:8]

    session = {
        "file": filepath,
        "id": session_id[:12],
        "full_id": session_id,
        "project": f"copilot/{ws_hash}",
        "source": "copilot",
        "turns": [],
        "user_messages": [],
        "tool_calls": defaultdict(int),
        "tool_results_chars": 0,
        "assistant_output_chars": 0,
        "models_used": set(),
        "start_time": None,
        "end_time": None,
        "total_input": 0,
        "total_output": 0,
        "total_cache_read": 0,
        "total_cache_create": 0,
    }

    # Track current turn's accumulated chars for token estimation
    current_turn_input_chars = 0
    current_turn_output_chars = 0

    for entry in entries:
        etype = entry.get("type", "")
        data = entry.get("data", {})

        ts = entry.get("timestamp")
        if ts:
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                if session["start_time"] is None:
                    session["start_time"] = dt
                session["end_time"] = dt
            except (ValueError, AttributeError):
                pass

        if etype == "session.start":
            model = data.get("selectedModel", "copilot-agent")
            session["models_used"].add(model)

        elif etype == "user.message":
            content = data.get("content", "")
            if isinstance(content, str):
                session["user_messages"].append(len(content))
                current_turn_input_chars += len(content)

        elif etype == "assistant.message":
            content = data.get("content", "")
            if isinstance(content, str):
                session["assistant_output_chars"] += len(content)
                current_turn_output_chars += len(content)

        elif etype == "tool.execution_start":
            tool_name = data.get("toolId", data.get("toolCallId", "unknown"))
            session["tool_calls"][tool_name] += 1

        elif etype == "assistant.turn_end":
            # Estimate tokens from chars (~4 chars per token)
            est_input = current_turn_input_chars // 4
            est_output = current_turn_output_chars // 4

            if est_input > 0 or est_output > 0:
                session["total_input"] += est_input
                session["total_output"] += est_output

                session["turns"].append({
                    "num": len(session["turns"]) + 1,
                    "input": est_input,
                    "output": est_output,
                    "cache_read": 0,
                    "cache_create": 0,
                    "total_sent": est_input,
                    "model": list(session["models_used"])[0] if session["models_used"] else "unknown",
                })

            # Accumulate input for next turn (context grows)
            current_turn_input_chars += current_turn_output_chars
            current_turn_output_chars = 0

    session["models_used"] = list(session["models_used"])
    return session


def load_all_sessions(base_path=None, include_gemini=True, source_filter=None):
    """Parse all sessions and return those with usage data."""
    sessions = []

    # Claude Code sessions
    if source_filter in (None, "all", "claude"):
        for f in find_session_files(base_path):
            try:
                s = parse_session(f)
                if s["turns"]:
                    s.setdefault("source", "claude")
                    s["cost"] = calc_cost(s)
                    sessions.append(s)
            except Exception as e:
                print(f"  [tokenxray] skipped Claude session {Path(f).name}: {e}", file=sys.stderr)
                continue

    # Gemini CLI sessions
    if source_filter in (None, "all", "gemini") and base_path is None:
        for f in find_gemini_session_files():
            try:
                s = parse_gemini_session(f)
                if s["turns"]:
                    s["cost"] = calc_cost(s)
                    sessions.append(s)
            except Exception as e:
                print(f"  [tokenxray] skipped Gemini session {Path(f).name}: {e}", file=sys.stderr)
                continue

    # GitHub Copilot sessions (estimated tokens — no billing data available)
    if source_filter in (None, "all", "copilot") and base_path is None:
        for f in find_copilot_session_files():
            try:
                s = parse_copilot_session(f)
                if s["turns"]:
                    s["cost"] = calc_cost(s)
                    sessions.append(s)
            except Exception as e:
                print(f"  [tokenxray] skipped Copilot session {Path(f).name}: {e}", file=sys.stderr)
                continue

    return sessions
