"""CLI argument parsing and command routing."""

import argparse

from tokenxray.colors import C


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
    parser.add_argument("--install-hook", action="store_true", help="Install live cost tracking hook")
    parser.add_argument("--confirm", action="store_true", help="Auto-confirm hook installation")
    parser.add_argument("--source", choices=["claude", "gemini", "all"], default="all",
                        help="Filter by tool (default: all)")
    parser.add_argument("--no-color", action="store_true", help="Disable colored output")

    args = parser.parse_args()

    if args.no_color:
        C.disable()

    if args.session:
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
    else:
        from tokenxray.commands.overview import run
        run(args)
