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

# Export for spreadsheets
tokenxray --export csv > sessions.csv

# Install live cost tracking in Claude Code
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

## Live Cost Tracking

Install a Claude Code hook that tracks your spending in real-time:

```bash
tokenxray --install-hook --confirm
```

This adds a PostToolUse hook that:
- Tracks running cost for each session
- Alerts when you cross $10, $25, $50, $100, $200 thresholds
- Shows periodic cost updates every 20 turns

```
[TokenXRay] Session cost: $25.42 (crossed $25 threshold, 142 turns, ctx 98K)
```

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
```

### GitHub Copilot
Not yet supported — Copilot doesn't store token usage data locally.

**Your data stays local.** TokenXRay reads files on your machine and writes to `~/.tokenxray/`. Nothing is sent anywhere.

## Supported Models

| Model | Input | Output | Cache Read | Cache Create |
|-------|-------|--------|------------|--------------|
| Claude Opus 4.6 | $15/MTok | $75/MTok | $1.50/MTok | $18.75/MTok |
| Claude Sonnet 4.6 | $3/MTok | $15/MTok | $0.30/MTok | $3.75/MTok |
| Claude Sonnet 4.5 | $3/MTok | $15/MTok | $0.30/MTok | $3.75/MTok |
| Claude Haiku 4.5 | $0.80/MTok | $4/MTok | $0.08/MTok | $1.00/MTok |
| Gemini 2.5 Pro | $1.25/MTok | $10/MTok | $0.31/MTok | — |
| Gemini 2.5 Flash | $0.15/MTok | $0.60/MTok | $0.04/MTok | — |

## Key Insights From Our Research

**1. Cache creation is the hidden cost killer**

Everyone talks about prompt caching saving money (and it does — 78% in our case). But nobody talks about cache *creation* costing 25% more than regular input. When your session context grows, every new token enters the cache at a premium. In our data, cache creation was **51% of total cost**.

**2. Your questions are noise in the token stream**

Across 514 sessions, actual user questions averaged **0.01%** of total input tokens. The other 99.99% is system prompts, tool definitions, conversation history, and tool results — all re-sent every turn.

**3. Marathon sessions are exponentially expensive**

A 100-turn session doesn't cost 10x a 10-turn session. It costs **100x+** because context accumulates and every new turn processes all previous context. The model re-reads your entire conversation history on every single turn.

**4. Output verbosity compounds**

A verbose 3K-token response doesn't just cost output tokens. That response enters the context and gets re-read on every subsequent turn. Over 100 more turns, that single response generates ~300K additional input tokens.

## What's Next

TokenXRay currently gives you **visibility** — it shows where tokens go. Phase 2 will add **optimization**:

- Context optimizer proxy for Claude Code
- Conversation history summarization
- Tool result pruning
- Cache-layout optimization for maximum cache hits

## Requirements

- Python 3.9+
- Claude Code and/or Gemini CLI (reads their local session logs)
- No external dependencies

## License

MIT
