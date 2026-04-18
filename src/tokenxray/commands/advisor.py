"""Smart model advisor — auto-switches between Opus and Sonnet based on prompt complexity."""

import json
import os

from tokenxray.colors import C
from tokenxray.config import DATA_DIR, SETTINGS_FILE

ADVISOR_SCRIPT = DATA_DIR / "model_advisor.py"

ADVISOR_CODE = '''#!/usr/bin/env python3
"""TokenXRay model advisor — auto-switches model based on prompt complexity.

Runs as a UserPromptSubmit hook. Reads the user's prompt, classifies it,
and updates settings.json to use Opus for complex tasks, Sonnet for routine ones.
"""
import json
import re
import sys
from pathlib import Path

SETTINGS_FILE = Path.home() / ".claude" / "settings.json"
STATE_FILE = Path.home() / ".tokenxray" / "advisor_state.json"

OPUS = "claude-opus-4-6"
SONNET = "claude-sonnet-4-6"

# ─── Classification rules ────────────────────────────────────────────────────

# Patterns that signal complex reasoning → use Opus
OPUS_PATTERNS = [
    # Architecture & design
    r"\\b(architect|design|plan|blueprint|rfc|proposal)\\b.*\\b(layer|system|module|api|service|feature|approach)\\b",
    r"\\b(design|plan|build)\\b.{5,}\\b(new|caching|system|layer|module)\\b",
    r"\\b(refactor|restructur|redesign|rearchitect|overhaul|rework)\\b",
    r"\\b(trade.?off|pros?.and.cons|compare.approaches|evaluate.options)\\b",
    # Deep analysis & debugging
    r"\\b(investigate|debug|root.cause|diagnose|figure.out.why)\\b",
    r"\\b(analyze|audit|review.*(code|pr|design|architecture))\\b",
    r"\\bwhy\\b.{0,20}\\b(is|does|doesn.t|isn.t|won.t|fail|break|crash|error)\\b",
    # Multi-step complex tasks
    r"\\b(implement|build|create|develop).{10,}(system|service|module|feature|api|pipeline)\\b",
    r"\\b(migrate|port|convert).{5,}(to|from|between)\\b",
    r"\\b(step.by.step|comprehensive|thorough|detailed.plan)\\b",
    # Security & correctness
    r"\\b(security|vulnerabilit|exploit|injection|auth)\\b",
    r"\\b(race.condition|deadlock|memory.leak|concurren)\\b",
    # Research
    r"\\b(research|explore|brainstorm|think.*carefully|fresh.*mind)\\b",
]

# Patterns that signal routine task → use Sonnet
SONNET_PATTERNS = [
    # Quick operations
    r"^\\s*(commit|push|pull|merge|rebase|cherry.pick)\\b",
    r"^\\s*(run|execute|start|stop|restart|test|lint|format|build)\\b",
    r"^\\s*(install|update|upgrade|add|remove).{0,30}(dependenc|package|module)?\\s*$",
    # Simple edits
    r"\\b(rename|change|replace|swap|move|copy|delete|remove)\\s+\\w+\\s+(to|with|from)\\b",
    r"\\b(add|insert|append).{0,20}(import|line|field|column|property)\\b",
    r"\\b(fix|correct).{0,15}(typo|spelling|indent|format|lint|whitespace)\\b",
    r"\\b(update|bump).{0,15}(version|dependency|package)\\b",
    # Lookups
    r"^\\s*(find|search|grep|look|show|list|read|cat|check|what.is)\\b",
    r"^\\s*(where|which|how.many|count)\\b",
    r"\\b(show.*diff|git.*status|git.*log)\\b",
    # Memory/recall
    r"^\\s*(recall|remember|forget|save.*memory|update.*memory)\\b",
    # Short prompts (< 80 chars) are usually simple
    r"^.{1,80}$",
    # Simple questions
    r"^\\s*(is|are|do|does|can|did|has|have|was|were)\\b.{0,80}$",
    # Confirmations
    r"^\\s*(yes|no|ok|sure|proceed|continue|go.ahead|do.it|lgtm|approved)\\s*$",
]


def classify(prompt):
    """Classify prompt as 'opus', 'sonnet', or 'keep' (no change)."""
    text = prompt.strip().lower()

    if not text:
        return "keep"

    opus_score = 0
    sonnet_score = 0

    for pattern in OPUS_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            opus_score += 1

    for pattern in SONNET_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            sonnet_score += 1

    # Opus signals are high-value — one strong signal wins over length-based sonnet
    if opus_score >= 1:
        return "opus"

    # Multiple sonnet signals or single clear one
    if sonnet_score >= 1:
        return "sonnet"

    # Prompt length heuristic: long prompts (>500 chars) tend to be complex
    if len(text) > 500:
        return "opus"

    return "keep"


def get_current_model():
    """Read current model from settings.json."""
    try:
        with open(SETTINGS_FILE) as f:
            return json.load(f).get("model", SONNET)
    except (FileNotFoundError, json.JSONDecodeError):
        return SONNET


def set_model(model):
    """Update model in settings.json, preserving all other settings."""
    settings = {}
    try:
        with open(SETTINGS_FILE) as f:
            settings = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    if settings.get("model") == model:
        return False  # no change needed

    settings["model"] = model
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=2)
    return True


def save_state(decision, prompt_preview):
    """Save advisor state for debugging."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    state = {"decision": decision, "prompt": prompt_preview[:100]}
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        return

    prompt = data.get("prompt", "")
    if not prompt:
        return

    decision = classify(prompt)
    current = get_current_model()

    if decision == "keep":
        return

    target = OPUS if decision == "opus" else SONNET
    target_label = "Opus" if decision == "opus" else "Sonnet"
    current_label = "Opus" if "opus" in current else "Sonnet"

    if target == current:
        return  # already on the right model

    changed = set_model(target)
    save_state(decision, prompt)

    if changed:
        icon = "\\U0001f9e0" if decision == "opus" else "\\u26a1"
        print(
            f"\\033[2m[TokenXRay] {icon} {current_label} \\u2192 {target_label} "
            f"(auto-switched for this prompt)\\033[0m",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
'''


def run(args):
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Write the advisor script
    with open(ADVISOR_SCRIPT, "w") as f:
        f.write(ADVISOR_CODE)
    os.chmod(ADVISOR_SCRIPT, 0o755)

    # Check if already installed
    settings = {}
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE) as f:
                settings = json.load(f)
        except json.JSONDecodeError:
            pass

    hooks = settings.get("hooks", {})
    prompt_hooks = hooks.get("UserPromptSubmit", [])

    already = any(
        str(ADVISOR_SCRIPT) in str(h.get("hooks", []))
        for h in prompt_hooks if isinstance(h, dict)
    )

    if already:
        print(f"{C.GREEN}Model advisor already installed! Script updated at {ADVISOR_SCRIPT}{C.RESET}")
        return

    print()
    print(f"{C.BOLD}{C.CYAN}TokenXRay — Install Smart Model Advisor{C.RESET}")
    print(f"{C.DIM}{'─' * 70}{C.RESET}")
    print(f"  Script: {ADVISOR_SCRIPT}")
    print(f"  Auto-switches between Opus and Sonnet based on prompt complexity")
    print(f"  Complex tasks (architecture, debugging, refactoring) → Opus")
    print(f"  Routine tasks (commits, lookups, simple edits) → Sonnet (5x cheaper)")
    print()

    if getattr(args, "confirm", False):
        hook_entry = {
            "hooks": [{"type": "command", "command": f"python3 {ADVISOR_SCRIPT}"}],
        }
        if not isinstance(prompt_hooks, list):
            prompt_hooks = []
        prompt_hooks.append(hook_entry)
        hooks["UserPromptSubmit"] = prompt_hooks
        settings["hooks"] = hooks

        with open(SETTINGS_FILE, "w") as f:
            json.dump(settings, f, indent=2)

        print(f"  {C.GREEN}{C.BOLD}Model advisor installed! Restart Claude Code to activate.{C.RESET}")
    else:
        print(f"  Run: {C.BOLD}tokenxray --install-advisor --confirm{C.RESET} to auto-install")

    print()
