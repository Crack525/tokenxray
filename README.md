<p align="center">
  <img src="assets/icon.svg" width="64" height="64" alt="TokenXRay icon">
</p>

# TokenXRay

**See where your AI coding tokens actually go.**

I spent $104 in a single Claude Code session. Then I audited all 514 of mine and found that **9% of sessions burned 92% of the money** — $11,600 out of $12,600 total. The culprit: context that grows quadratically, cache creation fees nobody mentions, and tool results that ride in context forever.

TokenXRay reads your local session logs, shows you exactly where tokens go, and auto-checkpoints expensive sessions so you can split them without losing context.

<p align="center">
  <img src="blog/tokenxray-explained.png" alt="TokenXRay — The Problem and Solution" width="800">
</p>

## Install

```bash
pip install tokenxray
```

**Zero dependencies.** Pure Python stdlib. Python 3.9+.

## Quick Start

```bash
tokenxray                          # Session overview — where your money goes
tokenxray --session <id>           # Deep dive into a specific session
tokenxray --diagnose               # Actionable recommendations
tokenxray --projects               # Cost breakdown by project
tokenxray --dashboard              # Interactive HTML dashboard
tokenxray --checkpoint             # Extract session state to .claude/checkpoint.md
tokenxray --install-hook --confirm # Live cost tracking + auto-checkpoint
```

## What It Shows You

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

Drill into any session for cost breakdown by token type, context growth curve, and waste ratio. Run `--diagnose` for specific actions: split long sessions, switch to Sonnet for routine tasks, avoid subagents for simple lookups.

## Live Cost Tracking + Auto-Checkpoint

```bash
tokenxray --install-hook --confirm
```

Installs two Claude Code hooks:

- **Cost hook** — tracks running cost after every tool use, alerts at $10/$25/$50/$100 thresholds, auto-checkpoints at 80 turns or $30
- **Resume hook** — detects checkpoint from previous session, restores context automatically on next session start

```
[TokenXRay] Opus — turn 40, $12.50 total, ~$0.31/turn, ctx 85K
[TokenXRay] Consider splitting this session! (80 turns, $31.20, ctx 120K)
[TokenXRay] Auto-checkpoint saved to .claude/checkpoint.md
```

Customize thresholds in `~/.tokenxray/config.json`:

```json
{
    "split_turns": 80,
    "split_cost": 30,
    "alert_thresholds": [10, 25, 50, 100, 200, 500],
    "status_interval": 10
}
```

## Supported Tools

| Tool | Source | Notes |
|------|--------|-------|
| **Claude Code** | `~/.claude/projects/**/*.jsonl` | Full token breakdown: input, output, cache read, cache create |
| **Gemini CLI** | `~/.gemini/tmp/*/chats/session-*.json` | Input, output, cached, thinking tokens |
| **GitHub Copilot** | VS Code workspace storage | Estimated from message lengths (token events are ephemeral) |

```bash
tokenxray --source claude    # Claude only
tokenxray --source gemini    # Gemini only
tokenxray --source copilot   # Copilot only
tokenxray --source all       # Everything (default)
```

**Your data stays local.** TokenXRay reads files on your machine. Nothing is sent anywhere.

## Additional Flags

| Flag | Description |
|------|-------------|
| `--top N` | Show top N sessions (default: 15) |
| `--path <dir>` | Custom path to session logs directory |
| `--no-color` | Disable colored output |
| `--baseline` / `--compare` | Save baseline, compare after changing habits |
| `--export csv` | Export sessions to CSV |

## The Full Story

Read the detailed analysis: [I Spent $104 in a Single AI Coding Session. Then I Audited All 514 of Mine.](blog/i-spent-104-dollars-in-one-ai-session.md)

## License

MIT
