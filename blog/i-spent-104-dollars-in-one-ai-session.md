# I Spent $104 in a Single AI Coding Session. Then I Audited All 686 of Mine.

*April 2026*

---

I was researching token waste in Claude Code. The irony? That research session itself cost me **$104**.

I didn't know until the next day. There was no warning, no counter, nothing. Just a quiet $104 charge for a single conversation.

I wrote a script to analyze the damage. The pattern was worse than I expected.

## The Audit

I analyzed **686 Claude Code sessions** — every session I'd run, totaling **$14,000+ in API costs**. I broke them down by length:

```
Session Segments:
  1-10 turns:   388 sessions (57%)  →  avg $0.19   →  <1% of total spend
  11-30 turns:  110 sessions (16%)  →  avg $3.18   →   2% of total spend
  31-100 turns: 117 sessions (17%)  →  avg $9.08   →   8% of total spend
  100+ turns:    71 sessions (10%)  →  avg $177    →  89% of total spend
                                                       ^^^
```

Read that last line again.

**10% of my sessions burned 89% of my money.**

The 71 marathon sessions — the ones where I was "in the zone," deep in a refactor or a tricky bug — those cost me $12,560. The other 615 sessions? $1,484 combined.

## What's Actually Eating Your Tokens

My actual questions — the text I typed — averaged **0.012%** of total input tokens. The other 99.99% is the model re-reading the entire conversation history, system prompts, tool definitions, and every file it ever touched. Every turn.

So where does the money go?

### Cache creation is 51% of total cost

Everyone celebrates prompt caching: "90% cheaper on cache reads!" True. But writing to the cache costs **25% MORE** than regular input. As your session grows, every new token enters the cache at that premium.

In my data, cache creation was the **single biggest expense** — 51% of total cost. Not output tokens. Not my prompts. The cache write fee.

### Everything stays in context forever

Every `cat` output, every `grep` result, every file read, every verbose response — it all stays in context. A 10K-token file read at turn 5 gets re-processed at turns 6, 7, 8... 100. That single read can generate over a million cached tokens by session end. A verbose 3,000-token response compounds the same way — re-read on every subsequent turn, generating ~300K additional input tokens over the session.

## The Math Behind It

A 100-turn session doesn't cost 10x a 10-turn session.

It costs **100x or more.**

Context accumulates quadratically. Every new turn processes all previous context. Turn 1 reads 18K tokens. Turn 100 reads 68K. Turn 200 reads 131K. Turn 399 reads your entire conversation history — compressed, expanded, re-cached — every single time.

That session: **399 turns, 2.4 hours, $104.** The context hit 131K tokens before auto-compaction kicked in. (When I later audited all 686 sessions, I found three sessions over $1,000 — the worst was $1,477 across 4,389 turns. The pattern compounds the longer you let it run.)

## So I Built TokenXRay

I turned those analysis scripts into a proper CLI tool. Zero dependencies, pure Python, reads your local session logs. No API keys, no cloud, nothing leaves your machine.

```bash
pip install tokenxray
```

### What it shows you

**Session overview** — where your money actually went:

```
TokenXRay - Session Overview
----------------------------------------------------------------------
  686 sessions    53,000+ total turns    $14,000+ total cost

  Segment Breakdown:
    1-10 turns:  388 sessions  avg  $0.19   total    $72   ░░░░░░░░░░  1%
         11-30:  110 sessions  avg  $3.18   total   $349   ░░░░░░░░░░  2%
        31-100:  117 sessions  avg  $9.08   total  $1,063  █░░░░░░░░░  8%
          100+:   71 sessions  avg   $177   total $12,560  █████████░ 89%
```

Drill into any session and it breaks down the cost by cache read, cache create, and output — then shows the waste ratio (my $104 session: 2.9K tokens of actual questions, 24.4M tokens of re-sent context). It flags marathon sessions and high cache creation costs with specific actions.

### What it does about it

After a one-time `tokenxray --install-hook --confirm`, three Claude Code hooks run automatically in every session:

- **Cost hook** — tracks spending silently in the background. Shows status every 10 turns, alerts at cost thresholds. At 60 turns or $5, auto-saves your session state to `.claude/checkpoint.md`. If you want the session blocked rather than just warned, enable hard-stop mode in `~/.tokenxray/config.json` — it returns exit code 2 past a configurable ceiling, so Claude is forced to wrap up before any next action.
- **Resume hook** — when you start a fresh session, detects the checkpoint and prints last-session stats plus the checkpoint path. It fires once, then gets out of the way.
- **Subagent hook** — warns before `Agent` tool calls. Shows a full warning on the first subagent call in a session, then periodic reminders, so high-cost subprocess usage is visible in real time.

You never run `tokenxray` during a session. The hooks handle it.

The real value isn't the real-time alerts — it's the retrospective. Running `tokenxray --diagnose` once a week teaches you to scope sessions better upfront. After a few runs, you start naturally thinking "I'll do the refactor, then start fresh for tests" instead of running a 200-turn marathon. That's where the actual savings come from.

## How It Compares

The LLM observability space is booming — Braintrust raised $80M, Langfuse was acquired by ClickHouse, Helicone by Mintlify. These are enterprise tracing platforms built for platform teams. They require API keys, proxy servers, and SDK integration.

TokenXRay is different: local-first, zero-config, aimed at the individual developer paying the bill.

| | Enterprise tools (Langfuse, Helicone, etc.) | TokenXRay |
|---|---|---|
| **Setup** | API keys + proxy/SDK integration | `pip install tokenxray` |
| **Data** | Sent to their cloud | Stays on your machine |
| **Target** | Platform engineering teams | Individual developers |
| **Insight** | Request-level tracing | Session-level waste analysis |
| **Action** | Dashboards | Auto-checkpoint + resume hooks |
| **AI tools** | Generic LLM APIs | Claude Code + Gemini + Copilot natively |
| **Cost** | Free tier → paid plans | Free, forever |

The closest alternatives: **claude-dashboard** (383 stars) shows current session info but no cost analysis. **tokencost** (1,963 stars) calculates prices but doesn't track sessions or intervene. **LiteLLM** (43K stars) has budget caps but requires proxy infrastructure.

None of them read your existing session logs. None auto-checkpoint and resume.

## What I Changed

The fix isn't complicated. It's session discipline:

1. **Split sessions at 60 turns.** A 120-turn session costs 4x+ what two 60-turn sessions cost, because context accumulates quadratically.
2. **Use Sonnet for routine tasks.** Opus costs 5x more. Your `git status` doesn't need a $15/MTok model.
3. **Avoid agent subprocesses for simple lookups.** `Read` is cheaper than spawning a subagent that re-reads your entire context. TokenXRay now warns on these calls in real time via the subagent hook.

TokenXRay automates #1 completely. It shows you #2 and reinforces #3 both in diagnosis and in-session subagent warnings.

A 200-turn session doesn't cost 2× a 100-turn session — it costs roughly 4× more, because context compounds on every turn. Applied retroactively to my full 686-session history, these patterns would have saved me over **$8,000**.

## Try It

```bash
pip install tokenxray
tokenxray
```

You'll see exactly where your tokens go. For most developers, the first run is a wake-up call.

If you want live cost tracking and auto-checkpoint:

```bash
tokenxray --install-hook --confirm
```

**Your data stays local.** Zero dependencies. Python 3.9+. Works with Claude Code, Gemini CLI, and GitHub Copilot.

[GitHub](https://github.com/Crack525/tokenxray) | [PyPI](https://pypi.org/project/tokenxray/)
