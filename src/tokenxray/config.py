"""Pricing models, paths, and constants."""

from pathlib import Path

# ─── Paths ─────────────────────────────────────────────────────────────────────

CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"
GEMINI_SESSIONS_DIR = Path.home() / ".gemini" / "tmp"
SETTINGS_FILE = Path.home() / ".claude" / "settings.json"
DATA_DIR = Path.home() / ".tokenxray"
BASELINE_FILE = DATA_DIR / "baseline.json"
HOOK_SCRIPT = DATA_DIR / "cost_hook.py"
LIVE_SESSION_FILE = DATA_DIR / "live_session.json"

# Backward compat alias
PROJECTS_DIR = CLAUDE_PROJECTS_DIR

# ─── Pricing (per million tokens) ──────────────────────────────────────────────

PRICING = {
    # Claude models
    "claude-opus-4-6": {
        "input": 15.0, "output": 75.0,
        "cache_read": 1.50, "cache_create": 18.75,
        "label": "Opus 4.6",
    },
    "claude-sonnet-4-6": {
        "input": 3.0, "output": 15.0,
        "cache_read": 0.30, "cache_create": 3.75,
        "label": "Sonnet 4.6",
    },
    "claude-sonnet-4-5-20250514": {
        "input": 3.0, "output": 15.0,
        "cache_read": 0.30, "cache_create": 3.75,
        "label": "Sonnet 4.5",
    },
    "claude-haiku-4-5-20251001": {
        "input": 0.80, "output": 4.0,
        "cache_read": 0.08, "cache_create": 1.0,
        "label": "Haiku 4.5",
    },
    # Gemini models (<=200K context tier)
    "gemini-2.5-pro": {
        "input": 1.25, "output": 10.0,
        "cache_read": 0.3125, "cache_create": 1.25,
        "label": "Gemini 2.5 Pro",
    },
    "gemini-2.5-flash": {
        "input": 0.15, "output": 0.60,
        "cache_read": 0.0375, "cache_create": 0.15,
        "label": "Gemini 2.5 Flash",
    },
}

DEFAULT_PRICING = {
    "input": 3.0, "output": 15.0,
    "cache_read": 0.30, "cache_create": 3.75,
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
