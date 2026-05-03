"""Actionable money-saving recommendations."""

from datetime import datetime

from tokenxray.colors import C
from tokenxray.display import fmt_cost, fmt_tokens
from tokenxray.parser import load_all_sessions


def run(args):
    sessions = load_all_sessions(args.path, source_filter=getattr(args, "source", None))
    if not sessions:
        print(f"{C.RED}No sessions found.{C.RESET}")
        return

    total_cost = sum(s["cost"]["total"] for s in sessions)
    recommendations = []

    _check_marathons(sessions, total_cost, recommendations)
    _check_cache_creation(sessions, total_cost, recommendations)
    _check_token_bombs(sessions, recommendations)
    _check_output_cost(sessions, total_cost, recommendations)
    _check_model_choice(sessions, total_cost, recommendations)
    _check_subagents(sessions, total_cost, recommendations)
    _check_projection(sessions, recommendations)

    _display(sessions, total_cost, recommendations)


def _marathon_threshold(sessions: list) -> int:
    """Compute a personalized marathon threshold from the user's own session history.

    Uses 2× the 75th-percentile turn count so the threshold adapts to the user's
    natural rhythm rather than a hardcoded number. Minimum of 30 and minimum 5
    sessions required; falls back to 100 for sparse histories.
    """
    turn_counts = sorted(len(s["turns"]) for s in sessions)
    if len(turn_counts) < 5:
        return 100
    p75_index = int(len(turn_counts) * 0.75)
    p75 = turn_counts[p75_index]
    return max(int(p75 * 2), 30)


def _check_marathons(sessions, total_cost, recs):
    threshold = _marathon_threshold(sessions)
    marathons = [s for s in sessions if len(s["turns"]) > threshold]
    marathon_cost = sum(s["cost"]["total"] for s in marathons)
    if marathons and total_cost > 0 and marathon_cost / total_cost > 0.5:
        avg_turns = sum(len(s["turns"]) for s in marathons) / len(marathons)
        savings = marathon_cost * 0.30
        recs.append(
            {
                "severity": "critical",
                "title": "Marathon sessions are burning your wallet",
                "detail": (
                    f"{len(marathons)} sessions with {threshold}+ turns cost {fmt_cost(marathon_cost)} "
                    f"({marathon_cost / total_cost * 100:.0f}% of total). Avg: {avg_turns:.0f} turns."
                ),
                "action": (
                    f"Start fresh sessions more often. Splitting could save ~{fmt_cost(savings)}."
                ),
                "potential_savings": savings,
            }
        )


def _check_cache_creation(sessions, total_cost, recs):
    total_cc = sum(s["cost"]["cache_create"] for s in sessions)
    cc_pct = total_cc / total_cost * 100 if total_cost > 0 else 0
    if cc_pct > 40:
        recs.append(
            {
                "severity": "critical",
                "title": f"Cache creation is {cc_pct:.0f}% of your total cost",
                "detail": (
                    f"Paying {fmt_cost(total_cc)} in cache creation fees (25% premium). "
                    f"Triggered by new content entering context."
                ),
                "action": (
                    "Reduce context growth: shorter prompts, partial file reads, concise responses."
                ),
                "potential_savings": total_cc * 0.20,
            }
        )


def _check_token_bombs(sessions, recs):
    bomb_sessions = []
    for s in sessions:
        bombs = [t for t in s["turns"] if t["output"] > 3000]
        if bombs:
            cost = sum(
                (t["output"] / 1e6) * s["cost"]["pricing"]["output"] for t in bombs
            )
            amplified = cost * 0.5
            bomb_sessions.append({"bombs": len(bombs), "cost": cost + amplified})

    if bomb_sessions:
        total_bombs = sum(b["bombs"] for b in bomb_sessions)
        total_cost = sum(b["cost"] for b in bomb_sessions)
        recs.append(
            {
                "severity": "high",
                "title": f"{total_bombs} token bombs across {len(bomb_sessions)} sessions",
                "detail": "Responses over 3K tokens. Direct cost plus context inflation.",
                "action": "Ask for concise responses. Each verbose output inflates all future turns.",
                "potential_savings": total_cost * 0.50,
            }
        )


def _check_output_cost(sessions, total_cost, recs):
    output_cost = sum(s["cost"]["output"] for s in sessions)
    output_tokens = sum(s["total_output"] for s in sessions)
    total_turns = sum(len(s["turns"]) for s in sessions)
    if total_cost > 0 and output_cost > total_cost * 0.05 and total_turns > 0:
        avg = output_tokens / total_turns
        recs.append(
            {
                "severity": "medium",
                "title": f"Output tokens: {fmt_cost(output_cost)} ({output_cost / total_cost * 100:.0f}%)",
                "detail": f"Average {avg:.0f} output tokens/turn. Total: {fmt_tokens(output_tokens)}.",
                "action": "Request concise responses. Verbose output compounds as context.",
                "potential_savings": output_cost * 0.40,
            }
        )


def _check_model_choice(sessions, total_cost, recs):
    opus = [s for s in sessions if any("opus" in m for m in s["models_used"])]
    if opus:
        opus_cost = sum(s["cost"]["total"] for s in opus)
        sonnet_eq = opus_cost / 5
        savings = opus_cost - sonnet_eq
        if savings > 10:
            recs.append(
                {
                    "severity": "medium",
                    "title": f"Opus usage: {fmt_cost(opus_cost)} across {len(opus)} sessions",
                    "detail": f"Opus is 5x pricier than Sonnet. Same work on Sonnet: ~{fmt_cost(sonnet_eq)}.",
                    "action": "Use Sonnet for routine tasks. Reserve Opus for complex reasoning.",
                    "potential_savings": savings,
                }
            )


def _check_subagents(sessions, total_cost, recs):
    # Subagent JSONL files are excluded from loading. Detect subagent usage from
    # Agent tool calls in the parent sessions instead.
    sessions_with_agents = []
    total_agent_calls = 0
    for s in sessions:
        calls = s.get("tool_calls", {})
        agent_calls = sum(
            count
            for name, count in calls.items()
            if name.lower() == "agent" or name.lower().startswith("agent")
        )
        if agent_calls > 0:
            sessions_with_agents.append((s, agent_calls))
            total_agent_calls += agent_calls

    if sessions_with_agents:
        agent_session_cost = sum(s["cost"]["total"] for s, _ in sessions_with_agents)
        pct = agent_session_cost / total_cost * 100 if total_cost > 0 else 0
        if pct > 10 or total_agent_calls >= 10:
            recs.append(
                {
                    "severity": "high",
                    "title": (
                        f"Subagent-heavy workflow: {total_agent_calls} Agent calls in "
                        f"{len(sessions_with_agents)} sessions"
                    ),
                    "detail": (
                        f"These sessions account for {fmt_cost(agent_session_cost)} "
                        f"({pct:.0f}% of total spend)."
                    ),
                    "action": (
                        "Use direct tools (Grep, Read, Glob) for simple lookups and "
                        "reserve Agent calls for high-leverage tasks."
                    ),
                    "potential_savings": agent_session_cost * 0.20,
                }
            )


def _check_projection(sessions, recs):
    timed = [s for s in sessions if s["start_time"] and s["end_time"]]
    if not timed:
        return
    now = (
        datetime.now(timed[0]["start_time"].tzinfo)
        if timed[0]["start_time"].tzinfo
        else datetime.now()
    )
    recent = [
        s
        for s in timed
        if s["end_time"]
        and (
            now - s["end_time"].replace(tzinfo=now.tzinfo if now.tzinfo else None)
        ).days
        < 7
    ]
    if recent:
        cost = sum(s["cost"]["total"] for s in recent)
        monthly = cost / 7 * 30
        if monthly > 100:
            recs.append(
                {
                    "severity": "info",
                    "title": f"Projected monthly cost: {fmt_cost(monthly)}",
                    "detail": f"Last 7 days: {fmt_cost(cost)} across {len(recent)} sessions.",
                    "action": "This is your burn rate. Apply recommendations above.",
                    "potential_savings": 0,
                }
            )


def _display(sessions, total_cost, recommendations):
    print()
    print(f"{C.BOLD}{C.CYAN}TokenXRay — Diagnosis & Recommendations{C.RESET}")
    print(f"{C.DIM}{'─' * 70}{C.RESET}")
    print(
        f"  Analyzed {len(sessions)} sessions, total spend: {C.BOLD}{fmt_cost(total_cost)}{C.RESET}"
    )
    print()

    total_potential = sum(r["potential_savings"] for r in recommendations)
    if total_potential > 0:
        print(
            f"  {C.GREEN}{C.BOLD}Potential savings: {fmt_cost(total_potential)}{C.RESET}"
        )
        print()

    icons = {
        "critical": f"{C.RED}[!!!]",
        "high": f"{C.YELLOW}[!! ]",
        "medium": f"{C.BLUE}[!  ]",
        "info": f"{C.DIM}[inf]",
    }
    order = {"critical": 0, "high": 1, "medium": 2, "info": 3}
    recommendations.sort(key=lambda r: order.get(r["severity"], 99))

    for rec in recommendations:
        print(f"  {icons.get(rec['severity'], '[?]')} {C.BOLD}{rec['title']}{C.RESET}")
        print(f"      {C.DIM}{rec['detail']}{C.RESET}")
        print(f"      {C.GREEN}Action: {rec['action']}{C.RESET}")
        if rec["potential_savings"] > 0:
            print(
                f"      {C.GREEN}Potential savings: ~{fmt_cost(rec['potential_savings'])}{C.RESET}"
            )
        print()

    if not recommendations:
        print(
            f"  {C.GREEN}No major issues found. Your token usage looks healthy!{C.RESET}"
        )
        print()
