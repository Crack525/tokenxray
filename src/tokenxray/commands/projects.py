"""Per-project cost breakdown."""

from collections import defaultdict

from tokenxray.colors import C
from tokenxray.display import fmt_cost, bar
from tokenxray.parser import find_session_files, parse_session, calc_cost


def run(args):
    files = find_session_files(args.path)
    projects = defaultdict(lambda: {
        "sessions": 0, "turns": 0, "cost": 0, "cache_create_cost": 0,
        "output_cost": 0, "cache_read_cost": 0, "input_cost": 0,
    })

    for f in files:
        try:
            s = parse_session(f)
            if not s["turns"]:
                continue
            cost = calc_cost(s)
            proj = s["project"]
            projects[proj]["sessions"] += 1
            projects[proj]["turns"] += len(s["turns"])
            projects[proj]["cost"] += cost["total"]
            projects[proj]["cache_create_cost"] += cost["cache_create"]
            projects[proj]["cache_read_cost"] += cost["cache_read"]
            projects[proj]["output_cost"] += cost["output"]
            projects[proj]["input_cost"] += cost["input"]
        except Exception:
            continue

    if not projects:
        print(f"{C.RED}No session data found.{C.RESET}")
        return

    total_cost = sum(p["cost"] for p in projects.values())
    total_cc = sum(p["cache_create_cost"] for p in projects.values())

    print()
    print(f"{C.BOLD}{C.CYAN}TokenXRay — Project Breakdown{C.RESET}")
    print(f"{C.DIM}{'─' * 70}{C.RESET}")
    print(
        f"  {C.BOLD}{len(projects)}{C.RESET} projects  "
        f"  {C.BOLD}{fmt_cost(total_cost)}{C.RESET} total cost  "
        f"  {C.RED}Cache creation: {fmt_cost(total_cc)} ({total_cc / total_cost * 100:.0f}%){C.RESET}"
    )
    print()

    print(f"  {C.DIM}{'Project':>40} {'Sessions':>8} {'Turns':>7} {'Cost':>9} {'CC Cost':>9} {'CC%':>5} {'Share':>6}{C.RESET}")
    print(f"  {C.DIM}{'─' * 85}{C.RESET}")

    for proj, data in sorted(projects.items(), key=lambda x: x[1]["cost"], reverse=True):
        cc_pct = data["cache_create_cost"] / data["cost"] * 100 if data["cost"] > 0 else 0
        share = data["cost"] / total_cost * 100 if total_cost > 0 else 0
        cost_color = C.RED if data["cost"] > 100 else (C.YELLOW if data["cost"] > 10 else C.GREEN)

        display_name = proj.replace("-Users-mdniajul-hasan-Documents-", "")
        if len(display_name) > 40:
            display_name = "..." + display_name[-37:]

        print(
            f"  {display_name:>40} {data['sessions']:>8} {data['turns']:>7,} "
            f"{cost_color}{fmt_cost(data['cost']):>9}{C.RESET} "
            f"{fmt_cost(data['cache_create_cost']):>9} {cc_pct:>4.0f}% "
            f"{C.YELLOW}{bar(share, 100, 10)}{C.RESET} {share:.0f}%"
        )

    # Cost composition
    print()
    print(f"  {C.BOLD}Where Your Money Goes (all projects):{C.RESET}")
    total_input_cost = sum(p["input_cost"] for p in projects.values())
    total_output_cost = sum(p["output_cost"] for p in projects.values())
    total_cr_cost = sum(p["cache_read_cost"] for p in projects.values())

    for label, val, color in [
        ("Cache creation (25% premium)", total_cc, C.RED),
        ("Cache reads (90% discount)", total_cr_cost, C.YELLOW),
        ("Output generation", total_output_cost, C.BLUE),
        ("Fresh input", total_input_cost, C.DIM),
    ]:
        pct = val / total_cost * 100 if total_cost > 0 else 0
        print(f"    {color}{label:>35}: {fmt_cost(val):>9} ({pct:.0f}%) {bar(pct, 100, 20)}{C.RESET}")

    print()
