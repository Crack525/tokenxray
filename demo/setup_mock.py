#!/usr/bin/env python3
"""
Generate mock Claude Code session JSONL files for the TokenXRay demo.
Creates sessions that reproduce the 10%/89% cost pattern from the blog post.

Usage:
    python demo/setup_mock.py [--home DEMO_HOME]
"""
import json
import os
import random
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

random.seed(42)  # reproducible

PRICING = {
    "claude-sonnet-4-6": {
        "input": 3.0, "output": 15.0,
        "cache_read": 0.30, "cache_create": 3.75,
    },
    "claude-opus-4-6": {
        "input": 15.0, "output": 75.0,
        "cache_read": 1.50, "cache_create": 18.75,
    },
}

BASE_TIME = datetime(2026, 3, 1, 9, 0, 0)


# ── Helpers ─────────────────────────────────────────────────────────────────

def make_id():
    return str(uuid.uuid4())


def jitter(v, pct=0.25):
    delta = int(v * pct)
    return max(0, v + random.randint(-delta, delta))


def generate_turns(num_turns, target_cost, model="claude-sonnet-4-6"):
    """
    Work backwards from target_cost to produce JSONL assistant entries.
    Distribution: 51% cache_create, 35% cache_read, 9% output, 5% fresh input.
    Context grows linearly (cache_read ramps from 0 to 2× average).
    """
    p = PRICING[model]

    # Token counts from target proportions
    total_cc   = int(target_cost * 0.51 / p["cache_create"] * 1e6)
    total_cr   = int(target_cost * 0.35 / p["cache_read"]   * 1e6)
    total_out  = int(target_cost * 0.09 / p["output"]        * 1e6)
    total_fresh= int(target_cost * 0.05 / p["input"]         * 1e6)

    avg_cc     = max(1, total_cc    // num_turns)
    avg_cr     = max(0, total_cr    // num_turns)
    avg_out    = max(1, total_out   // num_turns)
    avg_fresh  = max(1, total_fresh // num_turns)

    turns = []
    for i in range(num_turns):
        cr = int(avg_cr * 2.0 * i / max(num_turns - 1, 1))
        turns.append({
            "cache_create": jitter(avg_cc),
            "cache_read":   cr,
            "input":        jitter(avg_fresh),
            "output":       jitter(avg_out),
        })
    return turns


def build_session_jsonl(session_id, turns, model, base_time, interval_secs=90):
    """Assemble JSONL lines (one assistant entry per turn, one user entry)."""
    lines = []
    ts = base_time
    for t in turns:
        ts_str = ts.isoformat() + "Z"

        user = {
            "type": "user",
            "timestamp": ts_str,
            "message": {
                "role": "user",
                "content": [{"type": "text", "text": "continue"}],
            },
        }
        lines.append(json.dumps(user))

        asst = {
            "type": "assistant",
            "timestamp": ts_str,
            "message": {
                "id": f"msg_{uuid.uuid4().hex[:24]}",
                "role": "assistant",
                "model": model,
                "content": [{"type": "text", "text": "..."}],
                "usage": {
                    "input_tokens":               t["input"],
                    "output_tokens":              t["output"],
                    "cache_read_input_tokens":    t["cache_read"],
                    "cache_creation_input_tokens":t["cache_create"],
                },
            },
        }
        lines.append(json.dumps(asst))
        ts += timedelta(seconds=interval_secs)

    return "\n".join(lines) + "\n"


# ── Session catalogue ────────────────────────────────────────────────────────

SESSIONS = [
    # project-name, session-id (None → random), turns, target-cost, model, interval_secs
    # ── Short sessions (1-10 turns) ─────────────────────────────────────────
    ("my-api",       None, 3,  0.04,  "claude-sonnet-4-6", 60),
    ("my-api",       None, 5,  0.07,  "claude-sonnet-4-6", 60),
    ("my-api",       None, 7,  0.12,  "claude-sonnet-4-6", 60),
    ("my-api",       None, 9,  0.18,  "claude-sonnet-4-6", 60),
    ("my-api",       None, 2,  0.02,  "claude-sonnet-4-6", 60),
    ("frontend",     None, 4,  0.06,  "claude-sonnet-4-6", 60),
    ("frontend",     None, 6,  0.09,  "claude-sonnet-4-6", 60),
    ("frontend",     None, 8,  0.14,  "claude-sonnet-4-6", 60),
    ("frontend",     None, 3,  0.04,  "claude-sonnet-4-6", 60),
    ("auth-service", None, 5,  0.08,  "claude-sonnet-4-6", 60),
    ("auth-service", None, 7,  0.11,  "claude-sonnet-4-6", 60),
    ("infra",        None, 4,  0.06,  "claude-sonnet-4-6", 60),
    ("infra",        None, 6,  0.10,  "claude-sonnet-4-6", 60),
    ("scripts",      None, 3,  0.04,  "claude-sonnet-4-6", 60),
    ("scripts",      None, 2,  0.02,  "claude-sonnet-4-6", 60),
    ("scripts",      None, 8,  0.14,  "claude-sonnet-4-6", 60),
    ("my-api",       None, 4,  0.06,  "claude-sonnet-4-6", 60),
    ("my-api",       None, 6,  0.10,  "claude-sonnet-4-6", 60),
    ("frontend",     None, 5,  0.07,  "claude-sonnet-4-6", 60),
    ("frontend",     None, 7,  0.12,  "claude-sonnet-4-6", 60),
    # ── Medium sessions (11-30 turns) ───────────────────────────────────────
    ("my-api",       None, 14,  2.20, "claude-sonnet-4-6", 90),
    ("my-api",       None, 22,  3.80, "claude-sonnet-4-6", 90),
    ("my-api",       None, 28,  4.90, "claude-sonnet-4-6", 90),
    ("frontend",     None, 18,  2.90, "claude-sonnet-4-6", 90),
    ("frontend",     None, 25,  4.20, "claude-sonnet-4-6", 90),
    ("auth-service", None, 12,  1.80, "claude-sonnet-4-6", 90),
    ("auth-service", None, 20,  3.40, "claude-sonnet-4-6", 90),
    ("infra",        None, 16,  2.50, "claude-sonnet-4-6", 90),
    # ── Long sessions (31-100 turns) ────────────────────────────────────────
    ("my-api",       None, 45,  7.10, "claude-sonnet-4-6", 120),
    ("my-api",       None, 68,  11.2, "claude-sonnet-4-6", 120),
    ("frontend",     None, 52,  8.40, "claude-sonnet-4-6", 120),
    ("frontend",     None, 80,  13.1, "claude-sonnet-4-6", 120),
    ("auth-service", None, 38,  5.90, "claude-sonnet-4-6", 120),
    ("auth-service", None, 76,  12.4, "claude-sonnet-4-6", 120),
    ("infra",        None, 60,  9.60, "claude-sonnet-4-6", 120),
    # ── Marathon sessions (100+ turns) ──────────────────────────────────────
    # THE session from the blog post — fixed ID used in demo.tape
    ("my-api",       "a4f2c831-9d7e-4b8a-b2e1-f3c9d0e5a6b8",
                         399,  104.0, "claude-sonnet-4-6", 210),
    ("frontend",     None, 280,  67.3, "claude-sonnet-4-6", 200),
    ("auth-service", None, 350,  89.1, "claude-sonnet-4-6", 195),
    ("my-api",       None, 210,  48.7, "claude-sonnet-4-6", 180),
    ("infra",        None, 165,  37.4, "claude-sonnet-4-6", 170),
    ("frontend",     None, 130,  28.9, "claude-sonnet-4-6", 160),
]


def write_sessions(base_home: Path):
    projects_dir = base_home / ".claude" / "projects"
    current_time = BASE_TIME

    for entry in SESSIONS:
        project, sid, turns, cost, model, interval = entry
        sid = sid or make_id()

        proj_dir = projects_dir / project
        proj_dir.mkdir(parents=True, exist_ok=True)

        jsonl = build_session_jsonl(
            sid,
            generate_turns(turns, cost, model),
            model,
            current_time,
            interval_secs=interval,
        )

        (proj_dir / f"{sid}.jsonl").write_text(jsonl)
        current_time += timedelta(days=random.randint(1, 5), hours=random.randint(0, 8))

    print(f"✓  {len(SESSIONS)} sessions written to {projects_dir}")


if __name__ == "__main__":
    demo_home = Path(__file__).parent / "home"
    if "--home" in sys.argv:
        idx = sys.argv.index("--home")
        demo_home = Path(sys.argv[idx + 1])

    write_sessions(demo_home)
