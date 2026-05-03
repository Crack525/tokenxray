"""crossmem impact analysis — compare token spend before/after crossmem installation."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from tokenxray.colors import C
from tokenxray.display import fmt_cost, fmt_tokens, bar
from tokenxray.parser import load_all_sessions


def _detect_crossmem_install_date() -> datetime | None:
    """Return the datetime crossmem hook was installed, or None if not found."""
    settings_path = Path.home() / ".claude" / "settings.json"
    if not settings_path.exists():
        return None

    try:
        data = json.loads(settings_path.read_text())
    except (json.JSONDecodeError, OSError):
        return None

    # Confirm crossmem is actually wired in hooks
    hooks = data.get("hooks", {})
    crossmem_found = False
    for hook_list in hooks.values():
        for entry in hook_list:
            for h in entry.get("hooks", []):
                cmd = h.get("command", "")
                if "crossmem" in cmd:
                    crossmem_found = True
                    break

    if not crossmem_found:
        return None

    # Use settings.json mtime as the install date proxy
    mtime = settings_path.stat().st_mtime
    return datetime.fromtimestamp(mtime, tz=timezone.utc)


def _session_stats(sessions: list) -> dict:
    if not sessions:
        return {
            "count": 0,
            "avg_cost": 0,
            "avg_input": 0,
            "avg_turns": 0,
            "avg_cache_pct": 0,
            "total_cost": 0,
        }

    costs = [s["cost"]["total"] for s in sessions]
    inputs = [s["total_input"] for s in sessions]
    turns = [len(s["turns"]) for s in sessions]

    cache_pcts = []
    for s in sessions:
        total_sent = s["total_input"] + s["total_cache_read"] + s["total_cache_create"]
        pct = s["total_cache_read"] / total_sent * 100 if total_sent > 0 else 0
        cache_pcts.append(pct)

    return {
        "count": len(sessions),
        "avg_cost": sum(costs) / len(costs),
        "avg_input": sum(inputs) / len(inputs),
        "avg_turns": sum(turns) / len(turns),
        "avg_cache_pct": sum(cache_pcts) / len(cache_pcts),
        "total_cost": sum(costs),
    }


def _delta_str(before: float, after: float, lower_is_better: bool = True) -> str:
    if before == 0:
        return f"{C.DIM}n/a{C.RESET}"
    pct = (after - before) / before * 100
    improved = (pct < 0) if lower_is_better else (pct > 0)
    color = C.GREEN if improved else C.RED
    sign = "+" if pct > 0 else ""
    return f"{color}{sign}{pct:.1f}%{C.RESET}"


def run(args):
    install_date = _detect_crossmem_install_date()

    if install_date is None:
        print(f"\n  {C.YELLOW}crossmem not detected in Claude Code hooks.{C.RESET}")
        print(f"  {C.DIM}Run: crossmem install-hook{C.RESET}\n")
        return

    sessions = load_all_sessions(args.path, source_filter="claude")
    sessions_with_time = [s for s in sessions if s["start_time"] is not None]

    # Normalise all start_times to UTC-aware for comparison
    def to_utc(dt):
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt

    before = [s for s in sessions_with_time if to_utc(s["start_time"]) < install_date]
    after = [s for s in sessions_with_time if to_utc(s["start_time"]) >= install_date]

    b = _session_stats(before)
    a = _session_stats(after)

    print()
    print(f"{C.BOLD}{C.CYAN}TokenXRay — crossmem Impact Analysis{C.RESET}")
    print(f"{C.DIM}{'─' * 60}{C.RESET}")
    print(
        f"  crossmem installed: {C.BOLD}{install_date.strftime('%Y-%m-%d %H:%M UTC')}{C.RESET}"
        f"  {C.DIM}(via ~/.claude/settings.json mtime){C.RESET}"
    )
    print()

    if b["count"] == 0:
        print(
            f"  {C.YELLOW}No sessions found before crossmem install date — nothing to compare.{C.RESET}"
        )
        print(f"  {C.DIM}{a['count']} sessions recorded after install.{C.RESET}\n")
        return

    if a["count"] == 0:
        print(
            f"  {C.YELLOW}No sessions found after crossmem install date — too early to measure.{C.RESET}"
        )
        print(f"  {C.DIM}{b['count']} sessions recorded before install.{C.RESET}\n")
        return

    col_w = 28
    print(
        f"  {C.DIM}{'Metric':<{col_w}}{'Before':>12}{'After':>12}{'Delta':>10}{C.RESET}"
    )
    print(f"  {C.DIM}{'─' * 62}{C.RESET}")

    rows = [
        ("Sessions", f"{b['count']}", f"{a['count']}", None),
        (
            "Avg cost / session",
            fmt_cost(b["avg_cost"]),
            fmt_cost(a["avg_cost"]),
            _delta_str(b["avg_cost"], a["avg_cost"]),
        ),
        (
            "Avg input tokens",
            fmt_tokens(int(b["avg_input"])),
            fmt_tokens(int(a["avg_input"])),
            _delta_str(b["avg_input"], a["avg_input"]),
        ),
        (
            "Avg turns / session",
            f"{b['avg_turns']:.1f}",
            f"{a['avg_turns']:.1f}",
            _delta_str(b["avg_turns"], a["avg_turns"]),
        ),
        (
            "Avg cache hit %",
            f"{b['avg_cache_pct']:.1f}%",
            f"{a['avg_cache_pct']:.1f}%",
            _delta_str(b["avg_cache_pct"], a["avg_cache_pct"], lower_is_better=False),
        ),
        ("Total cost", fmt_cost(b["total_cost"]), fmt_cost(a["total_cost"]), None),
    ]

    for label, bval, aval, delta in rows:
        delta_col = delta if delta is not None else f"{C.DIM}—{C.RESET}"
        print(f"  {label:<{col_w}}{bval:>12}{aval:>12}  {delta_col}")

    print()

    # Summary verdict
    if b["avg_cost"] > 0 and a["avg_cost"] < b["avg_cost"]:
        saved_per_session = b["avg_cost"] - a["avg_cost"]
        pct = saved_per_session / b["avg_cost"] * 100
        projected = saved_per_session * a["count"]
        bar_pct = bar(pct, 100, 20)
        print(
            f"  {C.GREEN}{C.BOLD}crossmem is saving ~{fmt_cost(saved_per_session)}/session "
            f"({pct:.0f}% reduction){C.RESET}"
        )
        print(
            f"  {C.GREEN}{bar_pct}{C.RESET}  {C.DIM}projected savings over {a['count']} sessions: "
            f"{fmt_cost(projected)}{C.RESET}"
        )
    elif b["avg_cost"] > 0 and a["avg_cost"] >= b["avg_cost"]:
        print(
            f"  {C.YELLOW}No cost reduction detected yet.{C.RESET}  "
            f"{C.DIM}crossmem impact grows with session count — check back later.{C.RESET}"
        )

    print()
    print(
        f"  {C.DIM}Caveat: install date is approximated from settings.json mtime. "
        f"Session mix (project size, task type) also affects cost.{C.RESET}"
    )
    print()
