"""Default overview of all sessions."""

from tokenxray.colors import C
from tokenxray.display import fmt_cost, bar, duration_str, display_project_name
from tokenxray.config import get_model_label, DEFAULT_PRICING, PRICING_LAST_UPDATED
from tokenxray.parser import load_all_sessions, _pick_model


def run(args):
    from tokenxray.commands.hook import check_hook_skew

    sessions = load_all_sessions(args.path, source_filter=getattr(args, "source", None))
    if not sessions:
        print(f"{C.RED}No sessions with usage data found.{C.RESET}")
        return

    sessions.sort(key=lambda s: s["cost"]["total"], reverse=True)
    top_n = args.top or 15

    unknown_label = DEFAULT_PRICING["label"]
    unknown_count = sum(
        1 for s in sessions
        if get_model_label(_pick_model(s["models_used"])) == unknown_label
    )

    total_cost = sum(s["cost"]["total"] for s in sessions)
    total_turns = sum(len(s["turns"]) for s in sessions)
    total_saved = sum(s["cost"]["cache_savings"] for s in sessions)

    print()
    print(f"{C.BOLD}{C.CYAN}TokenXRay — Session Overview{C.RESET}  {C.DIM}pricing updated {PRICING_LAST_UPDATED} · anthropic + google{C.RESET}")
    print(f"{C.DIM}{'─' * 70}{C.RESET}")
    print(
        f"  {C.BOLD}{len(sessions)}{C.RESET} sessions  "
        f"  {C.BOLD}{total_turns:,}{C.RESET} total turns  "
        f"  {C.BOLD}{fmt_cost(total_cost)}{C.RESET} total cost  "
        f"  {C.GREEN}{fmt_cost(total_saved)} saved by caching{C.RESET}"
    )
    if unknown_count:
        print(
            f"  {C.YELLOW}Note: {unknown_count} session(s) have an unrecognized model and were "
            f"priced using Sonnet defaults — costs may be approximate.{C.RESET}"
        )
    old_ver, new_ver = check_hook_skew()
    if old_ver:
        print(
            f"  {C.YELLOW}Hook scripts are stale (v{old_ver} deployed, v{new_ver} installed). "
            f"Run: tokenxray --install-hook --confirm{C.RESET}"
        )
    print()

    # Segment breakdown
    segments = [
        ("1-10 turns", lambda s: len(s["turns"]) <= 10),
        ("11-30", lambda s: 11 <= len(s["turns"]) <= 30),
        ("31-100", lambda s: 31 <= len(s["turns"]) <= 100),
        ("100+", lambda s: len(s["turns"]) > 100),
    ]

    print(f"  {C.BOLD}Segment Breakdown:{C.RESET}")
    for name, filt in segments:
        seg = [s for s in sessions if filt(s)]
        if not seg:
            continue
        seg_cost = sum(s["cost"]["total"] for s in seg)
        pct = seg_cost / total_cost * 100 if total_cost > 0 else 0
        avg = seg_cost / len(seg)
        print(
            f"    {name:>10}: {len(seg):>4} sessions  "
            f"avg {fmt_cost(avg):>7}  "
            f"total {fmt_cost(seg_cost):>8}  "
            f"{C.YELLOW}{bar(pct, 100, 20)}{C.RESET} {pct:.0f}%"
        )

    # Top sessions table
    print()
    print(f"  {C.BOLD}Top {min(top_n, len(sessions))} Most Expensive Sessions:{C.RESET}")
    print(
        f"  {C.DIM}{'Session':>12}  {'Project':>25}  {'Turns':>6}  "
        f"{'Cost':>8}  {'Cache%':>6}  {'Model':>12}  {'Elapsed':>8}{C.RESET}"
    )
    print(f"  {C.DIM}{'─' * 90}{C.RESET}")

    for s in sessions[:top_n]:
        total_sent = s["total_input"] + s["total_cache_read"] + s["total_cache_create"]
        cache_pct = s["total_cache_read"] / total_sent * 100 if total_sent > 0 else 0

        model_label = get_model_label(_pick_model(s["models_used"]))

        cost_color = C.RED if s["cost"]["total"] > 50 else (
            C.YELLOW if s["cost"]["total"] > 10 else C.GREEN
        )

        print(
            f"  {s['id']:>12}  {display_project_name(s['project'], 25):>25}  {len(s['turns']):>6}  "
            f"{cost_color}{fmt_cost(s['cost']['total']):>8}{C.RESET}  "
            f"{cache_pct:>5.0f}%  {model_label:>12}  "
            f"{duration_str(s['start_time'], s['end_time']):>8}"
        )

    if len(sessions) > top_n:
        remaining_cost = sum(s["cost"]["total"] for s in sessions[top_n:])
        print(
            f"  {C.DIM}... and {len(sessions) - top_n} more sessions "
            f"({fmt_cost(remaining_cost)} total){C.RESET}"
        )

    print()
    print(f"  {C.DIM}Deep dive: tokenxray --session <id>{C.RESET}")

    # Nudge first-time users to install hooks if not yet configured
    from tokenxray.config import SETTINGS_FILE
    hooks_installed = False
    try:
        import json as _json
        with open(SETTINGS_FILE) as _f:
            hooks_installed = bool(_json.load(_f).get("hooks"))
    except (FileNotFoundError, Exception):
        pass
    if not hooks_installed:
        print(
            f"  {C.DIM}Tip: run {C.RESET}{C.BOLD}tokenxray --install-hook --confirm"
            f"{C.RESET}{C.DIM} to enable live cost tracking + auto-checkpoint.{C.RESET}"
        )
    print()
