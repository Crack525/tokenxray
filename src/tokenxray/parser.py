"""JSONL session parsing and cost calculation."""

import json
import glob
from datetime import datetime
from pathlib import Path
from collections import defaultdict

from tokenxray.config import PROJECTS_DIR, get_pricing


def find_session_files(base_path=None):
    """Find all Claude Code JSONL conversation logs."""
    path = Path(base_path) if base_path else PROJECTS_DIR
    if not path.exists():
        return []
    return sorted(glob.glob(str(path / "**/*.jsonl"), recursive=True))


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


def calc_cost(session):
    """Calculate session cost using model-specific pricing."""
    model = session["models_used"][0] if session["models_used"] else "unknown"
    pricing = get_pricing(model)

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


def load_all_sessions(base_path=None):
    """Parse all sessions and return those with usage data."""
    sessions = []
    for f in find_session_files(base_path):
        try:
            s = parse_session(f)
            if s["turns"]:
                s["cost"] = calc_cost(s)
                sessions.append(s)
        except Exception:
            continue
    return sessions
