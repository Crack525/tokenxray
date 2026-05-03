"""Model advisor — removed.

Model switching was removed from TokenXRay. The decision of which model to use
is a human judgment call, not something that can be reliably automated.

The --install-advisor flag now just installs/updates the cost hook, which
surfaces session cost, turn count, context size, and current model so the
developer has the information to decide for themselves.
"""

from tokenxray.colors import C
from tokenxray.commands.hook import run as install_hook


def run(args):
    print()
    print(f"{C.BOLD}{C.CYAN}TokenXRay — Model Advisor{C.RESET}")
    print(f"{C.DIM}{'─' * 70}{C.RESET}")
    print("  Model switching is a human decision. TokenXRay gives you the data:")
    print("    - Session cost, turn count, context size, cost/turn")
    print("    - Alerts at cost thresholds ($10, $25, $50, $100, $200)")
    print("    - Split warnings for marathon sessions")
    print(f"  Use {C.BOLD}/model{C.RESET} to switch models anytime.")
    print()
    print("  Installing/updating the cost hook...")
    print()

    install_hook(args)
