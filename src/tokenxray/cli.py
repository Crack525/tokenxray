"""CLI argument parsing and command routing."""

import argparse

from tokenxray import __version__
from tokenxray.colors import C
from tokenxray.config import PRICING_LAST_UPDATED


def main():
    parser = argparse.ArgumentParser(
        description="TokenXRay — See where your AI coding tokens actually go.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--path", help="Path to Claude projects directory")
    parser.add_argument("--session", "-s", help="Deep dive into a specific session ID")
    parser.add_argument("--top", "-t", type=int, help="Show top N sessions (default: 15)")
    parser.add_argument("--projects", "-p", action="store_true", help="Cost breakdown by project")
    parser.add_argument("--diagnose", "-d", action="store_true", help="Money-saving recommendations")
    parser.add_argument("--baseline", "-b", action="store_true", help="Save current stats as baseline")
    parser.add_argument("--compare", "-c", action="store_true", help="Compare against saved baseline")
    parser.add_argument("--export", "-e", choices=["csv"], help="Export data as CSV")
    parser.add_argument("--install-hook", action="store_true",
                        help="Install live cost tracking hook (Claude Code only)")
    parser.add_argument("--install-advisor", action="store_true",
                        help="Install cost hook (shows session cost so you can decide model)")
    parser.add_argument("--checkpoint", action="store_true",
                        help="Extract checkpoint from most recent session")
    parser.add_argument("--dashboard", action="store_true",
                        help="Generate interactive HTML dashboard with charts")
    parser.add_argument("--confirm", action="store_true", help="Auto-confirm hook installation")
    parser.add_argument("--doctor", action="store_true",
                        help="Diagnose installation health (hooks, settings, data sources)")
    parser.add_argument("--mcp", action="store_true",
                        help="MCP tool usage audit — find dead-weight servers and unused tools")
    parser.add_argument("--enumerate-tools", action="store_true",
                        help="Enumerate available tools from live MCP servers (use with --mcp)")
    parser.add_argument("--source", choices=["claude", "gemini", "copilot", "all"], default="all",
                        help="Filter by tool (default: all)")
    parser.add_argument("--version", "-v", action="version",
                        version=f"tokenxray {__version__} · pricing updated {PRICING_LAST_UPDATED}",
                        help="Show version and exit")
    parser.add_argument("--no-color", action="store_true", help="Disable colored output")
    parser.add_argument(
        "--rules",
        action="store_true",
        help="Generate personalized CLAUDE.md rules from your session history",
    )
    parser.add_argument(
        "--rules-dry-run",
        action="store_true",
        help="Print generated rules to stdout without writing CLAUDE.md",
    )
    parser.add_argument(
        "--crossmem-impact",
        action="store_true",
        help="Compare token spend before/after crossmem installation",
    )

    args = parser.parse_args()

    if args.no_color:
        C.disable()

    if args.crossmem_impact:
        from tokenxray.commands.crossmem_impact import run
        run(args)
    elif args.rules or args.rules_dry_run:
        from tokenxray.commands.rules import run
        run(args)
    elif args.doctor:
        from tokenxray.commands.doctor import run
        run(args)
    elif args.mcp:
        from tokenxray.commands.mcp import run
        run(args)
    elif args.session:
        from tokenxray.commands.session import run
        run(args)
    elif args.projects:
        from tokenxray.commands.projects import run
        run(args)
    elif args.diagnose:
        from tokenxray.commands.diagnose import run
        run(args)
    elif args.baseline:
        from tokenxray.commands.baseline import run_save
        run_save(args)
    elif args.compare:
        from tokenxray.commands.baseline import run_compare
        run_compare(args)
    elif args.export:
        from tokenxray.commands.export import run
        run(args)
    elif args.install_hook:
        from tokenxray.commands.hook import run
        run(args)
    elif args.install_advisor:
        from tokenxray.commands.advisor import run
        run(args)
    elif args.checkpoint:
        from tokenxray.commands.checkpoint import run
        run(args)
    elif args.dashboard:
        from tokenxray.commands.dashboard import run
        run(args)
    else:
        from tokenxray.commands.overview import run
        run(args)
