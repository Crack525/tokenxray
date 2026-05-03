"""Pricing models, paths, and constants."""

import platform
from pathlib import Path

# ─── Paths ─────────────────────────────────────────────────────────────────────

CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"
GEMINI_SESSIONS_DIR = Path.home() / ".gemini" / "tmp"

# VS Code stores Copilot data in platform-specific locations
_system = platform.system()
if _system == "Darwin":
    COPILOT_WORKSPACE_DIR = (
        Path.home()
        / "Library"
        / "Application Support"
        / "Code"
        / "User"
        / "workspaceStorage"
    )
elif _system == "Windows":
    COPILOT_WORKSPACE_DIR = (
        Path.home() / "AppData" / "Roaming" / "Code" / "User" / "workspaceStorage"
    )
else:  # Linux
    COPILOT_WORKSPACE_DIR = (
        Path.home() / ".config" / "Code" / "User" / "workspaceStorage"
    )
SETTINGS_FILE = Path.home() / ".claude" / "settings.json"
DATA_DIR = Path.home() / ".tokenxray"
BASELINE_FILE = DATA_DIR / "baseline.json"
HOOK_SCRIPT = DATA_DIR / "cost_hook.py"
STATUSLINE_SCRIPT = DATA_DIR / "statusline.py"
LIVE_SESSION_FILE = DATA_DIR / "live_session.json"

# Backward compat alias
PROJECTS_DIR = CLAUDE_PROJECTS_DIR

# ─── Pricing (per million tokens) ──────────────────────────────────────────────
# Verified against Anthropic + Google official pricing pages on 2026-04-23.
# Claude cache_create = 5-min TTL write price (1-hr TTL is 2× input; JSONL
# does not distinguish TTL tiers, so this is a lower-bound assumption).

PRICING_LAST_UPDATED = "2026-04-23"

PRICING = {
    # Claude models
    "claude-opus-4-6": {
        "input": 5.0,
        "output": 25.0,
        "cache_read": 0.50,
        "cache_create": 6.25,
        "label": "Opus 4.6",
    },
    "claude-sonnet-4-6": {
        "input": 3.0,
        "output": 15.0,
        "cache_read": 0.30,
        "cache_create": 3.75,
        "label": "Sonnet 4.6",
    },
    "claude-sonnet-4-5-20250514": {
        "input": 3.0,
        "output": 15.0,
        "cache_read": 0.30,
        "cache_create": 3.75,
        "label": "Sonnet 4.5",
    },
    "claude-haiku-4-5-20251001": {
        "input": 1.0,
        "output": 5.0,
        "cache_read": 0.10,
        "cache_create": 1.25,
        "label": "Haiku 4.5",
    },
    # Copilot (estimated from char counts — no real token data available)
    "copilot-agent": {
        "input": 3.0,
        "output": 15.0,
        "cache_read": 0.30,
        "cache_create": 3.75,
        "label": "Copilot",
    },
    # Gemini models (<=200K context tier, symmetric context cache pricing)
    "gemini-2.5-pro": {
        "input": 1.25,
        "output": 10.0,
        "cache_read": 0.125,
        "cache_create": 0.125,
        "label": "Gemini 2.5 Pro",
    },
    "gemini-2.5-flash": {
        "input": 0.30,
        "output": 2.50,
        "cache_read": 0.03,
        "cache_create": 0.03,
        "label": "Gemini 2.5 Flash",
    },
}

DEFAULT_PRICING = {
    "input": 3.0,
    "output": 15.0,
    "cache_read": 0.30,
    "cache_create": 3.75,
    "label": "Unknown (Sonnet pricing)",
}


def get_pricing(model: str) -> dict:
    """Get pricing for a model, matching by prefix or exact name."""
    if model in PRICING:
        return PRICING[model]
    for key, p in PRICING.items():
        if model.startswith(key.split("-202")[0]):
            return p
    return DEFAULT_PRICING


def get_model_label(model: str) -> str:
    """Get human-readable model label."""
    return get_pricing(model).get("label", "unknown")
