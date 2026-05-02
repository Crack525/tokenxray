# I Set a $10 Ceiling on Claude Code. It Actually Stopped.

*May 2026*

---

I was 47 turns into a refactoring session. Claude tried to run a Bash command.

It couldn't.

```
[TokenXRay] HARD STOP — cost limit ($10.43/$10) reached. Session blocked.
Please wrap up and start a fresh session.
Checkpoint was auto-saved earlier. Disable with: hard_stop=false in ~/.tokenxray/config.json
```

Exit code 2. Every subsequent tool call returned the same message. The session was over — not because Claude ran out of context, not because I manually stopped it, but because I'd drawn a line and the tool held it.

That had never happened to me with any AI coding tool before.

---

## What exists today

There are good tools for watching Claude Code spend money:

- **ccusage** (13.5K GitHub stars) — reads your JSONL logs and shows cost history. Excellent retrospective analysis. Fires no alerts. Can't stop anything.
- **RTK** (37K GitHub stars) — intercepts bash output before it enters context, compresses it, cuts 60–90% of terminal-derived token bloat. Impressive. Works at the shell layer. Can't stop a session.
- **claude-monitor**, **claude-dashboard**, various cost trackers — report after the fact. Same limit.

None of them will halt Claude mid-session. They observe. They report. They don't stop.

The reason is architectural: RTK works as a shell wrapper before tokens enter context. The others read logs after sessions end. Neither approach gives them a handle on the session while it's running.

Claude Code's hook system does. A PostToolUse hook fires after every tool call — and if it exits with code 2, Claude Code cannot proceed with the next action. That exit code is the ceiling.

---

## How to set one

One config change. Edit `~/.tokenxray/config.json`:

```json
{
    "hard_stop": true,
    "hard_stop_turns": 120,
    "hard_stop_cost": 10
}
```

That's it. The hook is already installed if you ran `tokenxray --install-hook --confirm`. The `hard_stop` key is off by default — flip it to `true`, set your ceiling, done.

When either limit is crossed:

1. The hook fires on the next tool call
2. Prints the hard-stop message in red to the conversation
3. Exits code 2
4. Every subsequent tool call repeats the same — Claude cannot continue

Claude can still *respond* to you — it just can't run any tools. That means you can ask it to summarize what it was doing, save state, or plan the next session. The session isn't bricked — it's parked.

A checkpoint is auto-saved at that point (or earlier, at the 60-turn/$5 soft checkpoint). Start a fresh session, read the checkpoint, continue. Same work, fresh context, zero compounding.

---

## What hard-stop is for

Hard-stop isn't for every session. I run most sessions without it. It's for three specific situations:

**1. When you walk away**

You leave Claude running on a long task. An hour later you're back: 340 turns, $180, still going. Hard-stop prevents this. Set a ceiling before you leave. If you're not watching, the ceiling is.

**2. When you're using a model you can't afford to overshoot**

Opus 4.7 is $15/MTok input. One marathon session at that rate hits $50–100 without drama. If you're on a budget, hard-stop at $20 means you never wake up to a surprise.

**3. When you're testing something cost-sensitive**

You want to know what a task costs at most. Hard-stop gives you a guaranteed upper bound. The task either finishes under your ceiling or stops at it. Either way, the bill is bounded.

---

## The difference between a warning and a ceiling

TokenXRay also fires advisory alerts when you cross $1, $3, $5, $10, $25, $50:

```
[TokenXRay] $5.20 spent (crossed $5) — Sonnet 4.6, 41 turns, ctx 52K, ~$0.13/turn
```

These are useful. They show up in the conversation. But Claude keeps going. You can choose to act or ignore them.

Hard-stop doesn't give you a choice. That's the point.

If you've ever watched an alert fire, thought "I'll wrap up soon," and then found yourself at $40 an hour later — hard-stop is for that.

---

## Try it

```bash
pip install tokenxray
tokenxray --install-hook --confirm
```

Then add to `~/.tokenxray/config.json`:

```json
{"hard_stop": true, "hard_stop_cost": 10}
```

The next time you hit $10, Claude stops.

**[GitHub](https://github.com/Crack525/tokenxray)** | **[PyPI](https://pypi.org/project/tokenxray/)**

---

*If you haven't read the original post about how 10% of sessions burned 89% of my total spend, it's [here](i-spent-104-dollars-in-one-ai-session.md). Hard-stop is the ceiling — that post explains why you need one.*
