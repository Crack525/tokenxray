# TokenXRay

**See where your AI coding tokens actually go.**

We spent $104 in a single Claude Code session researching token waste. Then we audited ourselves and discovered something every developer using AI coding tools should know.

## The Problem We Found

We analyzed **514 Claude Code sessions** totaling **$12,600+ in API costs**. Here's what the data showed:

```
Session Segments:
  1-10 turns:   329 sessions (64%)  →  avg $0.19   →  <1% of total spend
  11-30 turns:   76 sessions (15%)  →  avg $4.01   →   2% of total spend
  31-100 turns:  61 sessions (12%)  →  avg $11.05  →   5% of total spend
  100+ turns:    48 sessions  (9%)  →  avg $241    →  92% of total spend
                                                       ^^^
```

**9% of sessions burn 92% of the money.** And within those sessions:

- Your actual questions are **0.012%** of total input tokens
- **99%** of tokens are the model re-reading old context
- **Cache creation** (25% premium) is **51%** of total cost — the single biggest expense
- Tool results (bash output, file reads) ride in context **forever**, never pruned

No existing tool shows you this. Not your API dashboard. Not your billing page. We had to write custom scripts to see it. So we turned those scripts into TokenXRay.

## Install

### pip (recommended)

```bash
pip install tokenxray
```

### From source (no venv needed)

```bash
git clone https://github.com/niajulhasan/tokenxray.git
cd tokenxray

# Option A: install it
pip install -e .

# Option B: just run it directly (zero setup)
PYTHONPATH=src python3 -m tokenxray
```

**Zero external dependencies.** Pure Python stdlib. No venv required.

## Quick Start

```bash
# See all your sessions at a glance
tokenxray

# Deep dive into your most expensive session
tokenxray --session <id>

# Which projects are burning money?
tokenxray --projects

# Get actionable recommendations
tokenxray --diagnose

# Save a baseline, compare later
tokenxray --baseline
tokenxray --compare

# Interactive HTML dashboard
tokenxray --dashboard

# Extract checkpoint from most recent session
tokenxray --checkpoint

# Export for spreadsheets
tokenxray --export csv > sessions.csv

# Install live cost tracking + auto-checkpoint in Claude Code
tokenxray --install-hook --confirm
```

## What You'll See

### Session Overview

```
TokenXRay - Session Overview
----------------------------------------------------------------------
  514 sessions    43,000+ total turns    $12,600+ total cost

  Segment Breakdown:
    1-10 turns:  329 sessions  avg  $0.19   total    $62   ░░░░░░░░░░  0%
         11-30:   76 sessions  avg  $4.01   total   $305   ░░░░░░░░░░  2%
        31-100:   61 sessions  avg $11.05   total   $674   █░░░░░░░░░  5%
          100+:   48 sessions  avg   $241   total $11,600  ████████░░ 92%
```

### Session Deep Dive

```
TokenXRay - Session Deep Dive
----------------------------------------------------------------------
  Session:  060870e6-7cdd-425a-8e3b-8b9e29e7d3e8
  Duration: 2.4hrs
  Turns:    399

  Cost Breakdown:
    Cache read:           $47.30  (90% discount)
    Cache create:         $46.95  (25% premium)  <-- biggest cost!
    Output:               $10.20
    Total:                  $104

  The Waste Ratio:
    Your questions:          2.9K  (0.012% of input)
    Context re-sent:       24.4M  (99% waste from re-reading)

  Context Growth:
    Turn    1:    18.4K  ███░░░░░░░░░░░░░░░░░░░░░░░░░
    Turn  101:    67.7K  ██████████████░░░░░░░░░░░░░░░
    Turn  201:   131.3K  ████████████████████████████░░
    Turn  301:    52.3K  ███████████░░░░░░░░░░░░░░░░░░  (compacted)
```

### Diagnosis

```
TokenXRay - Diagnosis & Recommendations
----------------------------------------------------------------------
  Potential savings: $16,000+

  [!!!] Marathon sessions are burning your wallet
        48 sessions with 100+ turns cost $11,600 (92% of total)
        Action: Start fresh sessions more often.

  [!!!] Cache creation is 51% of your total cost
        Paying $6,448 in cache creation fees (25% premium)
        Action: Reduce context growth with shorter responses.

  [!! ] Subagents cost $3,239 (26% of total)
        Action: Use direct tools (Grep, Read) over agents for lookups.

  [!  ] Opus usage: $12,600 across 237 sessions
        Same work on Sonnet would cost ~$2,500.
        Action: Use Sonnet for routine tasks.
```

## Interactive Dashboard

Generate a self-contained HTML dashboard with charts and heatmaps:

```bash
tokenxray --dashboard
```

Opens an interactive dashboard with:
- Cost breakdown by session segment (Chart.js bar/pie charts)
- Session cost heatmap over time
- Token type distribution (input, output, cache read, cache create)
- Actionable recommendations based on your usage patterns

The dashboard is a single HTML file — no server, no dependencies, works offline.

## Live Cost Tracking + Auto-Checkpoint

Install Claude Code hooks that track spending and auto-save session state:

```bash
tokenxray --install-hook --confirm
```

This installs two hooks:

**Cost Hook** (PostToolUse) — runs after every tool use:
- Tracks running cost for each session
- Alerts when you cross cost thresholds ($10, $25, $50, $100, $200, $500)
- Shows periodic cost updates every 10 turns
- **Auto-checkpoints** when sessions get expensive (80+ turns or $30+)

```
[TokenXRay] Opus — turn 40, $12.50 total, ~$0.31/turn, ctx 85K
[TokenXRay] $25.42 spent (crossed $25) — Opus, 142 turns, ctx 98K
[TokenXRay] Consider splitting this session! (80 turns, $31.20, ctx 120K)
[TokenXRay] Auto-checkpoint saved to .claude/checkpoint.md
```

**Resume Hook** (UserPromptSubmit) — runs when you start a new session:
- Detects `.claude/checkpoint.md` from the previous session
- Tells Claude to read it — full context restored automatically
- Only fires once, then renames the file so it doesn't repeat

**Zero user action required.** Expensive session auto-saves, next session auto-resumes.

### Manual Checkpoint

Extract a checkpoint from the most recent session at any time:

```bash
tokenxray --checkpoint
```

This reads the latest session JSONL, extracts goal, files modified, commands run, and assistant context, then saves it to `.claude/checkpoint.md` in the project directory.

If you're inside a Claude Code session, you can also use the `/checkpoint` slash command — Claude will synthesize a richer checkpoint from its own context and optionally save to crossmem.

### Configurable Guardrails

Customize thresholds via `~/.tokenxray/config.json`:

```json
{
    "split_turns": 80,
    "split_cost": 30,
    "alert_thresholds": [10, 25, 50, 100, 200, 500],
    "status_interval": 10
}
```

| Key | Default | Description |
|-----|---------|-------------|
| `split_turns` | 80 | Warn + checkpoint after this many turns |
| `split_cost` | 30 | Warn + checkpoint after this cost ($) |
| `alert_thresholds` | [10,25,50,100,200,500] | Cost milestones that trigger alerts |
| `status_interval` | 10 | Show status update every N turns |

## Before / After Comparison

Save a baseline before changing your habits, then compare:

```bash
# Before: save your current state
tokenxray --baseline

# ... change habits, use Sonnet more, split sessions ...

# After: see the difference
tokenxray --compare
```

```
                     Baseline      Current          Delta
  Sessions              514          520    +6
  Total cost          $6,414       $6,480    +$66
  Avg cost/session    $12.48       $12.46    -$0.02   <-- improving!
```

## Supported Tools

### Claude Code
Reads JSONL conversation logs from `~/.claude/projects/**/*.jsonl`. Full token breakdown: input, output, cache read (90% discount), cache creation (25% premium).

### Gemini CLI
Reads session JSON from `~/.gemini/tmp/*/chats/session-*.json`. Token breakdown: input, output, cached, thinking tokens. No cache creation premium.

```bash
# View only Claude sessions
tokenxray --source claude

# View only Gemini sessions
tokenxray --source gemini

# View everything (default)
tokenxray --source all

# View only Copilot sessions
tokenxray --source copilot
```

### GitHub Copilot (VS Code)
Reads transcript JSONL from VS Code workspace storage. **Limitation:** Copilot marks token usage events as ephemeral (in-memory only), so token counts are estimated from message character lengths (~4 chars/token). Turn counts and tool usage are accurate.

**Your data stays local.** TokenXRay reads files on your machine and writes to `~/.tokenxray/`. Nothing is sent anywhere.

## Supported Models

| Model | Input | Output | Cache Read | Cache Create |
|-------|-------|--------|------------|--------------|
| Claude Opus 4.6 | $15/MTok | $75/MTok | $1.50/MTok | $18.75/MTok |
| Claude Sonnet 4.6 | $3/MTok | $15/MTok | $0.30/MTok | $3.75/MTok |
| Claude Sonnet 4.5 | $3/MTok | $15/MTok | $0.30/MTok | $3.75/MTok |
| Claude Haiku 4.5 | $0.80/MTok | $4/MTok | $0.08/MTok | $1.00/MTok |
| Gemini 2.5 Pro | $1.25/MTok | $10/MTok | $0.3125/MTok | $1.25/MTok |
| Gemini 2.5 Flash | $0.15/MTok | $0.60/MTok | $0.0375/MTok | $0.15/MTok |
| Copilot (estimated) | ~$3/MTok | ~$15/MTok | — | — |

## Key Insights From Our Research

**1. Cache creation is the hidden cost killer**

Everyone talks about prompt caching saving money (and it does — 78% in our case). But nobody talks about cache *creation* costing 25% more than regular input. When your session context grows, every new token enters the cache at a premium. In our data, cache creation was **51% of total cost**.

**2. Your questions are noise in the token stream**

Across 514 sessions, actual user questions averaged **0.012%** of total input tokens. The other 99.99% is system prompts, tool definitions, conversation history, and tool results — all re-sent every turn.

**3. Marathon sessions are exponentially expensive**

A 100-turn session doesn't cost 10x a 10-turn session. It costs **100x+** because context accumulates and every new turn processes all previous context. The model re-reads your entire conversation history on every single turn.

**4. Output verbosity compounds**

A verbose 3K-token response doesn't just cost output tokens. That response enters the context and gets re-read on every subsequent turn. Over 100 more turns, that single response generates ~300K additional input tokens.

## What's Next

TokenXRay gives you **visibility** (where tokens go) and **guardrails** (auto-checkpoint expensive sessions). Next up:

- Session optimizer — intelligent context pruning and tool result summarization
- Cache-layout optimization for maximum cache hits
- Team usage dashboards

## Additional Flags

| Flag | Description |
|------|-------------|
| `--top N` | Show top N sessions (default: 15) |
| `--path <dir>` | Custom path to Claude projects directory |
| `--no-color` | Disable colored output |
| `--source <tool>` | Filter by tool: `claude`, `gemini`, `copilot`, or `all` |

## Requirements

- Python 3.9+
- Claude Code, Gemini CLI, and/or GitHub Copilot (reads their local session logs)
- No external dependencies

## License

MIT
