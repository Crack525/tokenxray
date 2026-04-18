"""Deep dive into a single session."""

from pathlib import Path

from tokenxray.colors import C
from tokenxray.display import fmt_cost, fmt_tokens, bar, duration_str
from tokenxray.parser import load_all_sessions


def run(args):
    session_id = args.session
    sessions = load_all_sessions(args.path, source_filter=getattr(args, "source", None))

    s = None
    for sess in sessions:
        if sess["full_id"].startswith(session_id) or session_id in sess["full_id"]:
            s = sess
            break

    if not s:
        print(f"{C.RED}Session '{session_id}' not found.{C.RESET}")
        return

    cost = s["cost"]
    total_sent = s["total_input"] + s["total_cache_read"] + s["total_cache_create"]
    user_q_tokens = sum(s["user_messages"]) // 4
    tool_result_tokens = s["tool_results_chars"] // 4
    assistant_tokens = s["assistant_output_chars"] // 4

    # Header
    print()
    print(f"{C.BOLD}{C.CYAN}TokenXRay — Session Deep Dive{C.RESET}")
    print(f"{C.DIM}{'─' * 70}{C.RESET}")
    print(f"  Session:  {s['full_id']}")
    print(f"  Project:  {s['project']}")
    print(f"  Duration: {duration_str(s['start_time'], s['end_time'])}")
    print(f"  Model:    {', '.join(s['models_used'][:3])}")
    print(f"  Turns:    {len(s['turns'])}")

    # Cost breakdown
    print()
    print(f"  {C.BOLD}Cost Breakdown:{C.RESET}")
    print(f"    Fresh input:     {fmt_cost(cost['input']):>10}")
    print(f"    Cache read:      {fmt_cost(cost['cache_read']):>10}  {C.DIM}(90% discount){C.RESET}")
    print(f"    Cache create:    {fmt_cost(cost['cache_create']):>10}  {C.DIM}(25% premium){C.RESET}")
    print(f"    Output:          {fmt_cost(cost['output']):>10}")
    print(f"    {C.BOLD}Total:           {fmt_cost(cost['total']):>10}{C.RESET}")
    print(f"    Without caching: {fmt_cost(cost['total_no_cache']):>10}")
    if cost["total_no_cache"] > 0:
        print(
            f"    {C.GREEN}Caching saved:   {fmt_cost(cost['cache_savings']):>10} "
            f"({cost['cache_savings'] / cost['total_no_cache'] * 100:.0f}%){C.RESET}"
        )

    # Token breakdown
    print()
    print(f"  {C.BOLD}Token Breakdown:{C.RESET}")
    print(f"    Total sent to model:   {fmt_tokens(total_sent):>10}")
    if total_sent > 0:
        print(f"      Cache read (reused): {fmt_tokens(s['total_cache_read']):>10}  "
              f"({s['total_cache_read'] / total_sent * 100:.0f}%)")
    print(f"      Cache create (new):  {fmt_tokens(s['total_cache_create']):>10}")
    print(f"      Fresh input:         {fmt_tokens(s['total_input']):>10}")
    print(f"    Output generated:      {fmt_tokens(s['total_output']):>10}")

    # Waste ratio
    print()
    print(f"  {C.BOLD}The Waste Ratio:{C.RESET}")
    if user_q_tokens > 0 and total_sent > 0:
        q_pct = user_q_tokens / total_sent * 100
        print(f"    Your questions:     {fmt_tokens(user_q_tokens):>10}  ({q_pct:.3f}% of input)")
    print(f"    Tool results:       {fmt_tokens(tool_result_tokens):>10}")
    print(f"    Assistant output:   {fmt_tokens(assistant_tokens):>10}")

    max_ctx = max(t["total_sent"] for t in s["turns"]) if s["turns"] else 0
    total_all_sent = sum(t["total_sent"] for t in s["turns"])
    if max_ctx > 0 and total_all_sent > max_ctx:
        resend_pct = (total_all_sent - max_ctx) / total_all_sent * 100
        print(
            f"    {C.RED}Context re-sent:    {fmt_tokens(total_all_sent - max_ctx):>10}  "
            f"({resend_pct:.0f}% waste from re-reading){C.RESET}"
        )

    # Context growth
    print()
    print(f"  {C.BOLD}Context Growth:{C.RESET}")
    if s["turns"]:
        max_sent = max(t["total_sent"] for t in s["turns"])
        step = max(1, len(s["turns"]) // 12)
        for i, t in enumerate(s["turns"]):
            if i % step == 0 or i == len(s["turns"]) - 1:
                print(
                    f"    Turn {t['num']:>4}: {fmt_tokens(t['total_sent']):>8}  "
                    f"{C.BLUE}{bar(t['total_sent'], max_sent, 35)}{C.RESET}"
                )

    # Token bombs
    print()
    print(f"  {C.BOLD}Token Bombs (largest outputs):{C.RESET}")
    for t in sorted(s["turns"], key=lambda t: t["output"], reverse=True)[:5]:
        if t["output"] > 0:
            print(f"    Turn {t['num']:>4}: {C.YELLOW}{fmt_tokens(t['output']):>8}{C.RESET} output tokens")

    # Tool usage
    if s["tool_calls"]:
        print()
        print(f"  {C.BOLD}Tool Usage:{C.RESET}")
        for name, count in sorted(s["tool_calls"].items(), key=lambda x: x[1], reverse=True)[:10]:
            print(f"    {name:>20}: {count:>4} calls")

    # Cache creation analysis
    print()
    print(f"  {C.BOLD}Cache Creation Analysis (biggest cost driver):{C.RESET}")
    for t in sorted(s["turns"], key=lambda t: t["cache_create"], reverse=True)[:5]:
        if t["cache_create"] > 0:
            cc_cost = (t["cache_create"] / 1e6) * cost["pricing"]["cache_create"]
            print(
                f"    Turn {t['num']:>4}: {fmt_tokens(t['cache_create']):>8} new cache tokens  "
                f"({fmt_cost(cc_cost)})"
            )

    print()
