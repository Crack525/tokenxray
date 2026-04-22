# I Spent $104 in a Single AI Coding Session. Then I Found Where $8,000 Disappeared.

*April 2026*

---

I was researching token waste in Claude Code. The session that produced the findings cost me **$104**.

I didn't know until the next day. No warning. No counter. Just a quiet charge for a single conversation I thought was routine.

If you use Claude Code, Gemini CLI, or Copilot daily and pay your own API bills — this post is about you. Not about enterprise teams with observability budgets. You, running sessions at your desk, with no idea how fast the cost compounds.

---

## The Finding

I audited every session I'd ever run. **686 sessions. $14,000+ in total API costs.**

The pattern:

```
Session Segments:
  1-10 turns:   388 sessions (57%)  →  avg $0.19  →   <1% of total spend
  11-30 turns:  110 sessions (16%)  →  avg $3.18  →    2% of total spend
  31-100 turns: 117 sessions (17%)  →  avg $9.08  →    8% of total spend
  100+ turns:    71 sessions (10%)  →  avg  $177  →   89% of total spend
                                                       ^^^
```

**10% of my sessions burned 89% of my money.**

Those 71 marathon sessions — the deep refactors, the tricky bugs where I was "in the zone" — cost me $12,560. The other 615 sessions? $1,484 combined.

Applied retroactively, fixing this pattern would have saved me over **$8,000**.

---

## Why It Happens

The reason isn't obvious until you look at the actual numbers.

### Your words are almost nothing

My actual questions — the text I typed — averaged **0.012%** of total input tokens. Everything else is the model re-reading your entire conversation history, system prompts, tool definitions, and every file it ever touched. Every turn.

### Context doesn't grow linearly — it compounds

A 100-turn session doesn't cost 10× a 10-turn session. It costs **100× or more.**

Every new turn processes all previous context. Here's what that looks like in practice:

```
Turn   1  →   18K tokens processed
Turn  50  →   43K tokens processed
Turn 100  →   68K tokens processed
Turn 200  →  131K tokens processed
Turn 400  →  260K tokens processed (auto-compaction kicks in)
```

Each bar is the cost of that single turn — not cumulative. By turn 100, a single exchange costs nearly 4× what it cost at turn 1. Across 100 turns, the total bill is roughly 100× what turn 1 implied.

That $104 session: 399 turns, 2.4 hours. The context crossed 131K tokens before auto-compaction. When I audited all 686 sessions, I found three over $1,000. The worst: $1,477 across 4,389 turns.

### Cache creation is the hidden tax

Everyone celebrates prompt caching: "90% cheaper on cache reads!" True. But writing to the cache costs **25% more** than regular input. As your session grows, every new token enters the cache at that premium.

In my data, cache creation was the **single biggest cost category — 51% of total spend**. Not output tokens. Not my prompts. The cache write fee, silently compounding every turn.

### Everything stays in context forever

A 10K-token file read at turn 5 gets re-processed at turn 6, 7, 8 ... 100. That single read can generate over a million cached tokens by session end. A verbose 3,000-token response compounds the same way — re-read on every subsequent turn, generating ~300K additional input tokens across the session.

Your context is a leaky bucket that never drains.

---

## Before and After

Here's what session discipline actually looks like in practice.

**Before** (how I ran sessions for two years):

```
Monday: One long refactor session — 180 turns, 4 hours     →  $89
Tuesday: Bug hunt + fix, didn't want to lose context        →  $52
Wednesday: Feature + tests in the same session              →  $61
Week total:                                                    $202
```

**After** (splitting at ~60 turns):

```
Monday AM: Refactor planning + core changes    →  60 turns  →  $12
Monday PM: Edge cases + cleanup                →  55 turns  →   $9
Tuesday AM: Bug diagnosis                      →  45 turns  →   $7
Tuesday PM: Fix + verification                 →  40 turns  →   $5
Wednesday: Feature                             →  58 turns  →  $11
Wednesday: Tests (fresh session)               →  50 turns  →   $8
Week total:                                                    $52
```

Same work. Same depth. **74% less cost.** The difference is that context never compounds past the inflection point.

A 120-turn session costs 4× what two 60-turn sessions cost — not 2×. That asymmetry is the whole game.

---

## What I Built

I turned the analysis scripts into a CLI tool. It reads the session logs Claude Code already writes to `~/.claude/projects/`. No API keys. No cloud. No proxy. Zero dependencies. Nothing leaves your machine.

```bash
pip install tokenxray
tokenxray
```

**TokenXRay** does two things: shows you exactly where your tokens went, and runs hooks in every session so you don't have to think about it again.

---

## What It Shows You

**Session overview** — your full history, segmented by cost:

```
TokenXRay - Session Overview
----------------------------------------------------------------------
  686 sessions    53,000+ total turns    $14,000+ total cost

  Segment Breakdown:
    1-10 turns:  388 sessions  avg  $0.19  total    $72   ░░░░░░░░░░  1%
         11-30:  110 sessions  avg  $3.18  total   $349   ░░░░░░░░░░  2%
        31-100:  117 sessions  avg  $9.08  total  $1,063  █░░░░░░░░░  8%
          100+:   71 sessions  avg   $177  total $12,560  █████████░ 89%
```

**Session deep dive** — drill into any session and see cost broken down by cache read, cache create, and output. Flags the waste ratio: my $104 session — 2.9K tokens of actual questions, 24.4M tokens of re-sent context. That's the number that changes behavior.

**Diagnosis** (`tokenxray --diagnose`) — runs once a week, flags your worst patterns, gives you specific actions. After a few runs you start naturally thinking "I'll do the refactor, then start fresh for tests" before the session even begins. That's where the savings are.

---

## What It Does During Sessions

After a one-time setup:

```bash
tokenxray --install-hook --confirm
```

Three hooks run automatically in every Claude Code session:

**Cost hook** — tracks spending silently. Shows a status line every 10 turns. At 60 turns or $5, auto-saves your session state to `.claude/checkpoint.md` — exact context, files in play, where you stopped. If you want Claude blocked rather than just warned, enable hard-stop mode in `~/.tokenxray/config.json`: it returns exit code 2 past your ceiling, forcing Claude to wrap up before any next action.

**Resume hook** — when you start a fresh session, detects the checkpoint and prints last-session stats plus the checkpoint path. Fires once, then gets out of the way.

**Subagent hook** — warns before `Agent` tool calls. The first subagent call in a session shows a full warning; subsequent ones show periodic reminders. Subagents re-read your entire context inside a subprocess — they're expensive in ways that aren't obvious until you see the bill.

You never run `tokenxray` mid-session. The hooks handle it.

---

## Why Local-First Matters

The LLM observability space has attracted serious money: Braintrust raised $80M, Langfuse was acquired by ClickHouse, Helicone by Mintlify. These are enterprise tracing platforms — they require API keys, proxy servers, and SDK integration. They send your data to their cloud.

TokenXRay works differently by design:

| | Enterprise tools (Langfuse, Helicone, etc.) | TokenXRay |
|---|---|---|
| **Setup** | API keys + proxy/SDK integration | `pip install tokenxray` |
| **Data** | Sent to their cloud | Stays on your machine |
| **Target** | Platform engineering teams | Individual developers |
| **Insight** | Request-level tracing | Session-level waste analysis |
| **Action** | Dashboards | Auto-checkpoint + resume hooks |
| **AI tools** | Generic LLM APIs | Claude Code + Gemini + Copilot natively |
| **Cost** | Free tier → paid plans | Free, forever |

Your session logs contain your code, your architecture decisions, your debugging process. They're not telemetry data — they're your work. They shouldn't leave your machine.

The other reason for local-first: TokenXRay reads logs that already exist. You don't change your workflow to use it. There's no SDK to wrap, no proxy to route through. Install once, run once, get the picture. The hooks are the only ongoing behavior change — and they're invisible.

Closest alternatives: **claude-dashboard** (383 stars) shows current session info but no cost analysis. **tokencost** (1,963 stars) calculates prices but doesn't track sessions or intervene. **LiteLLM** (43K stars) has budget caps but requires proxy infrastructure. None of them read your existing logs. None auto-checkpoint and resume.

---

## The Three Changes That Matter

1. **Split sessions at 60 turns.** A 120-turn session costs 4× what two 60-turn sessions cost, because context compounds quadratically. TokenXRay automates the checkpoint — you just start fresh.

2. **Use Sonnet for routine tasks.** Opus costs 5×. Your `git status` review doesn't need a $15/MTok model. TokenXRay flags when you're using Opus on low-complexity work and shows the cost differential.

3. **Avoid agent subprocesses for simple lookups.** A `Read` call is cheaper than spawning a subagent that re-reads your full context inside a new process. The subagent hook surfaces these calls in real time so you can decide before the cost lands.

Applied to my 686-session history: **$8,000+ saved.**

---

## Try It

```bash
pip install tokenxray
tokenxray
```

The first run shows your full history. Most developers find their own 89% stat — the sessions they thought were productive that were actually burning the budget.

For live tracking and auto-checkpoint:

```bash
tokenxray --install-hook --confirm
```

Your data stays local. Zero dependencies. Python 3.9+. Works with Claude Code, Gemini CLI, and GitHub Copilot.

[GitHub](https://github.com/Crack525/tokenxray) | [PyPI](https://pypi.org/project/tokenxray/)
