"""Save and compare baselines."""

import json
from datetime import datetime

from tokenxray.colors import C
from tokenxray.config import DATA_DIR, BASELINE_FILE
from tokenxray.display import fmt_cost
from tokenxray.parser import load_all_sessions


def run_save(args):
    sessions = load_all_sessions(args.path, source_filter=getattr(args, "source", None))
    if not sessions:
        print(f"{C.RED}No sessions found.{C.RESET}")
        return

    total_cost = sum(s["cost"]["total"] for s in sessions)
    total_turns = sum(len(s["turns"]) for s in sessions)

    segment_stats = {}
    for name, lo, hi in [("1-10", 1, 10), ("11-30", 11, 30), ("31-100", 31, 100), ("100+", 101, 99999)]:
        seg = [s for s in sessions if lo <= len(s["turns"]) <= hi]
        segment_stats[name] = {
            "count": len(seg),
            "total_cost": sum(s["cost"]["total"] for s in seg),
            "avg_cost": sum(s["cost"]["total"] for s in seg) / len(seg) if seg else 0,
        }

    baseline = {
        "timestamp": datetime.now().isoformat(),
        "session_count": len(sessions),
        "total_turns": total_turns,
        "total_cost": total_cost,
        "avg_cost_per_session": total_cost / len(sessions),
        "segments": segment_stats,
    }

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(BASELINE_FILE, "w") as f:
        json.dump(baseline, f, indent=2)

    print()
    print(f"{C.BOLD}{C.GREEN}Baseline saved!{C.RESET}")
    print(f"  File: {BASELINE_FILE}")
    print(f"  Sessions: {len(sessions)}, Total: {fmt_cost(total_cost)}, Avg: {fmt_cost(baseline['avg_cost_per_session'])}")
    print(f"  {C.DIM}Compare later with: tokenxray --compare{C.RESET}")
    print()


def run_compare(args):
    if not BASELINE_FILE.exists():
        print(f"{C.RED}No baseline found. Run: tokenxray --baseline{C.RESET}")
        return

    with open(BASELINE_FILE) as f:
        bl = json.load(f)

    sessions = load_all_sessions(args.path, source_filter=getattr(args, "source", None))
    cur_cost = sum(s["cost"]["total"] for s in sessions)
    cur_sessions = len(sessions)
    cur_turns = sum(len(s["turns"]) for s in sessions)
    cur_avg = cur_cost / cur_sessions if cur_sessions else 0

    def delta(val, fmt_fn=fmt_cost):
        if val > 0:
            return f"{C.RED}+{fmt_fn(val)}{C.RESET}"
        if val < 0:
            return f"{C.GREEN}{fmt_fn(val)}{C.RESET}"
        return f"{C.DIM}no change{C.RESET}"

    print()
    print(f"{C.BOLD}{C.CYAN}TokenXRay — Baseline Comparison{C.RESET}")
    print(f"{C.DIM}{'─' * 70}{C.RESET}")
    print(f"  Baseline from: {bl['timestamp'][:19]}")
    print()

    print(f"  {'':>20} {'Baseline':>12} {'Current':>12} {'Delta':>15}")
    print(f"  {C.DIM}{'─' * 60}{C.RESET}")
    print(f"  {'Sessions':>20} {bl['session_count']:>12} {cur_sessions:>12} {delta(cur_sessions - bl['session_count'], str)}")
    print(f"  {'Total turns':>20} {bl['total_turns']:>12,} {cur_turns:>12,} {delta(cur_turns - bl['total_turns'], str)}")
    print(f"  {'Total cost':>20} {fmt_cost(bl['total_cost']):>12} {fmt_cost(cur_cost):>12} {delta(cur_cost - bl['total_cost'])}")
    print(f"  {'Avg cost/session':>20} {fmt_cost(bl['avg_cost_per_session']):>12} {fmt_cost(cur_avg):>12} {delta(cur_avg - bl['avg_cost_per_session'])}")

    # Segment comparison
    print()
    print(f"  {C.BOLD}Segment Comparison:{C.RESET}")
    for name in ["1-10", "11-30", "31-100", "100+"]:
        lo = {"1-10": 1, "11-30": 11, "31-100": 31, "100+": 101}[name]
        hi = {"1-10": 10, "11-30": 30, "31-100": 100, "100+": 99999}[name]
        cur_seg = [s for s in sessions if lo <= len(s["turns"]) <= hi]
        cur_seg_avg = sum(s["cost"]["total"] for s in cur_seg) / len(cur_seg) if cur_seg else 0
        base_avg = bl.get("segments", {}).get(name, {}).get("avg_cost", 0)
        base_count = bl.get("segments", {}).get(name, {}).get("count", 0)
        print(
            f"    {name:>6} turns: {base_count:>4} -> {len(cur_seg):>4} sessions  "
            f"avg {fmt_cost(base_avg):>7} -> {fmt_cost(cur_seg_avg):>7}  {delta(cur_seg_avg - base_avg)}"
        )

    print()
