<p align="center">
  <img src="assets/icon.svg" width="64" height="64" alt="TokenXRay icon">
</p>

# TokenXRay

**See where your AI coding tokens actually go.**

I spent $104 in a single Claude Code session. Then I audited all 514 of mine and found that **9% of sessions burned 92% of the money** — $11,600 out of $12,600 total. The culprit: context that grows quadratically, cache creation fees nobody mentions, and tool results that ride in context forever.

<p align="center">
  <img src="blog/tokenxray-explained.png" alt="TokenXRay — The Problem and Solution" width="800">
</p>

## Install

```bash
pip install tokenxray
tokenxray --install-hook --confirm   # one-time setup, then forget about it
```

**Zero dependencies.** Pure Python stdlib. Python 3.9+.

## How It Works

TokenXRay has two layers: **hooks** that run automatically inside Claude Code, and a **CLI** you run when you want to review your spending.

### Daily: Hooks (automatic, zero effort)

After `--install-hook`, every Claude Code session gets two hooks that run silently in the background:

1. **Cost hook** — tracks your running cost after every tool use. Shows a status line every 10 turns. Alerts when you cross $10/$25/$50/$100. At 80 turns or $30, auto-saves your session state to `.claude/checkpoint.md`.
2. **Resume hook** — when you start a new session, detects the checkpoint and alerts you with last session stats. Claude can then read `checkpoint.md` to restore context. One-shot: fires once, then gets out of the way.

Your daily workflow:
```
Open Claude Code → checkpoint detected? stats shown, Claude reads checkpoint.md
       ↓
Work normally → cost hook tracks silently in background
       ↓
Hit 80 turns or $30 → checkpoint auto-saved
       ↓
You decide: keep going or start fresh (checkpoint is saved either way)
       ↓
Start fresh → next session picks up where you left off
```

You never run `tokenxray` during a session. The hooks handle it.

```
[TokenXRay] Opus — turn 40, $12.50 total, ~$0.31/turn, ctx 85K
[TokenXRay] Consider splitting this session! (80 turns, $31.20, ctx 120K)
[TokenXRay] Auto-checkpoint saved to .claude/checkpoint.md
```

**Hard-stop mode** (opt-in): block further tool use past a ceiling so Claude is forced to wrap up. Enable in `~/.tokenxray/config.json`:

```json
{"hard_stop": true, "hard_stop_turns": 120, "hard_stop_cost": 50}
```

When either ceiling is crossed, the hook exits with code 2. Every subsequent tool call fails with the hard-stop message until you start a fresh session. Off by default — the advisory split warning still fires regardless.

### Weekly: CLI (manual review)

Run these when you want to understand your spending patterns and change habits:

```bash
tokenxray                  # Overview — where your money goes
tokenxray --diagnose       # Specific recommendations
tokenxray --session <id>   # Deep dive into one session
tokenxray --dashboard      # Interactive HTML charts
tokenxray --projects       # Cost by project
tokenxray --mcp            # MCP tool audit — find dead-weight servers
```

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

The retrospective analysis is the most valuable part. After a few `--diagnose` runs, you start naturally scoping sessions better — "I'll do the refactor, then start fresh for tests." That's where the real savings come from.

## Configuration

Customize hook thresholds in `~/.tokenxray/config.json`:

```json
{
    "split_turns": 80,
    "split_cost": 30,
    "alert_thresholds": [10, 25, 50, 100, 200, 500],
    "status_interval": 10,
    "hard_stop": false,
    "hard_stop_turns": 120,
    "hard_stop_cost": 50
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
| `--checkpoint` | Manually extract session state |
| `--mcp` | MCP tool audit — dead-weight servers, unused tools, schema cost estimate |
| `--mcp --enumerate-tools` | Spawn each configured MCP server and get exact tool counts |

## MCP Tool Audit

Every MCP server you configure globally loads its full tool schema into Claude's context on every session start — roughly **185 tokens per tool**. At 84 tools across a few servers, that's ~15K tokens per session, silently added even when you never call a single MCP tool.

```bash
tokenxray --mcp                   # Audit from call history
tokenxray --mcp --enumerate-tools # Also spawn servers to get exact tool counts
```

Output shows per-server call rates, never-called tools, and a dead-weight estimate: sessions that loaded schemas but called zero MCP tools. The fix is usually moving from global `~/.claude.json` config to project-level `.mcp.json` so servers only load where you actually use them.

## The Full Story

Read the detailed analysis: [I Spent $104 in a Single AI Coding Session. Then I Audited All 514 of Mine.](blog/i-spent-104-dollars-in-one-ai-session.md)

## License

MIT
