# TokenXRay Changelog

## v0.3.27 — 2026-05-03 · hook version skew detection

- Embeds `TOKENXRAY_HOOK_VERSION` in deployed `cost_hook.py` at install time (baked from package version)
- `--install-hook` detects stale scripts and prints upgrade notice: `v0.3.26 → v0.3.27`
- Overview warns inline if deployed hook version lags installed package: `Run: tokenxray --install-hook --confirm`
- Exported `check_hook_skew()` for programmatic use

---

## v0.3.26 — 2026-05-03 · trajectory alert + pre-hardstop checkpoint

- Turn 40+ trajectory alert: fires when projected cost at current velocity exceeds `trajectory_warn_cost` (default $8)
- Pre-hardstop checkpoint: silent auto-save at 80% of hard-stop ceiling; `pre_stop_saved` flag prevents duplicate writes
- Checkpoint goal fix: uses first user message ≥50 chars to skip system/hook noise

---

## v0.3.25 — 2026-05-03 · subagent injection coverage

- `find_session_files()` gains `include_subagents=False` parameter — default unchanged for all existing callers
- `--memory-impact` now passes `include_subagents=True` so injections that fired inside subagent sessions (e.g. Explore/Plan agents) are correctly correlated instead of silently dropped
- Unmatched injections (no session in range) are counted and reported at the footer rather than silently ignored

---

## v0.3.24 — 2026-05-03 · `tokenxray --memory-impact`

New command: **memory hit rate analysis** — feedback loop to know which crossmem
memories the LLM agent actually used vs. silently ignored.

- Reads `~/.tokenxray/memory_injections.jsonl` (written by crossmem ≥ 1.5.0)
- Correlates each injection event to the Claude session active at that timestamp
- Checks lexical overlap between injected memory keywords/snippets and assistant
  response text that follows
- Reports per-memory: injection count, hit count, hit rate %
- Sorted ascending by hit rate — low-rate memories flagged as pruning candidates
  with a `← prune?` marker and a `crossmem forget <id>` suggestion

Requires crossmem ≥ 1.5.0 installed with the `prompt-search` hook active.

---

## v0.3.23 — 2026-04-25 · blog + README reframe

- Blog post: "I set a $10 ceiling on Claude Code. It actually stopped."
- README reframed around hard-stop as the unique differentiator

---

## v0.3.22 — 2026-04-24 · Python 3.9 compatibility + CI

- Fix f-string same-quote nesting for Python 3.9 compatibility in `doctor.py`
- Add `from __future__ import annotations` for Python 3.9
- Add GitHub Actions CI workflow — test matrix (3.9–3.13) + PyPI publish on tag

---

## v0.3.21 — 2026-04-24 · behavioral fingerprinting + CLAUDE.md generator

- `tokenxray --rules` — generates personalized CLAUDE.md rules from session history
- `tokenxray --rules-dry-run` — prints generated rules without writing

---

## v0.3.20 — 2026-04-23 · doctor cost fix

- Fix `tokenxray --doctor` showing `$0.0000` for live session cost. Hook writes
  `total_cost` key; doctor was reading `cost`. Now reads `total_cost` with `cost`
  as fallback for backward compatibility.

---

## v0.3.19 — 2026-04-23 · `tokenxray --doctor`

New diagnosis-only command that audits installation health in one shot:

- Hook scripts present at `~/.tokenxray/` (size + age)
- `pricing.json` last_updated date
- Claude Code registrations in `~/.claude/settings.json` (PostToolUse, UserPromptSubmit, PreToolUse, statusLine)
- Hook activity via `live_session.json` (last fire time + cost/turns)
- Data source session counts (Claude, Gemini, Copilot)
- One-line verdict: **healthy / installed but idle / not installed / partially configured**

No writes — safe to run anytime. 18 new tests.

---

## v0.3.18 — 2026-04-23 · pricing correction

Verified all model prices against official Anthropic + Google pricing pages on
2026-04-23 and found four stale entries. After this fix, historical session costs
will appear lower — **your actual API bill did not change**, only the displayed estimate.

- **Opus 4.6**: $15/$75 → **$5/$25** (input/output per MTok). Anthropic unified
  Opus 4.5/4.6/4.7 at the lower tier; only Opus 4 and 4.1 still use $15/$75.
  Opus 4.6 sessions now price at ~1/3 of before.
- **Haiku 4.5**: $0.80/$4 → **$1/$5** (~25% increase)
- **Gemini 2.5 Pro** cache: $0.31/$1.25 → **$0.125/$0.125** (now symmetric)
- **Gemini 2.5 Flash**: $0.15/$0.60 → **$0.30/$2.50** (2×/4× increase)

Claude Sonnet 4.6/4.5 pricing confirmed correct.

Also adds `pricing updated YYYY-MM-DD` to `--version` output and the overview
header so you can tell at a glance whether the numbers are current.

---

## v0.3.17 — 2026-04-23 · hotfix

- Fix `ImportError` crash on `tokenxray --mcp` (dead imports `calc_cost` and
  `_pick_model` removed from mcp.py)
- Add `tests/test_imports.py`: exhaustive submodule import smoke test + `--mcp`
  empty-dir short-circuit test — prevents this class of bug going forward

---

## v0.3.16 — 2026-04-23 · MCP audit + dashboard security

- **P10** XSS fix in dashboard: escape `</script>` in JSON blob; replace
  `innerHTML` with DOM methods
- **P12** Chart.js vendored as package asset (`tokenxray/assets/chart.umd.min.js`)
  with CDN fallback — dashboard works offline
- **P13** MCP audit header notes "(Claude Code sessions only)"
- **P14** MCP dead-weight cost uses actual average input price from session history
  instead of hardcoded Sonnet rate
- **P15** `duration_str()` caps at `>1d` instead of showing e.g. `47.2hrs`

---

## v0.3.15 — 2026-04-23

- Single-source `pricing.json` written at install time; hook reads via stdlib json
- `get_current_model(fallback)` uses `last_model` from JSONL
- Subagent hook shows first-call warning on stale/missing state
- Overview warns when sessions priced with `DEFAULT_PRICING`

---

## v0.3.14 — 2026-04-23 · UX polish

- `display_project_name()` + `display_model_name()` helpers; all views use
  cleaned project names
- Overview model label fixed (was "Unknown (Sonnet pricing)" due to `<synthetic>`)
- "Duration" renamed to "Elapsed"

---

## v0.3.0–v0.3.13

Checkpoint reliability, per-turn model pricing, mixed-model session cost accuracy,
subagent filtering, CSV export fixes, and regression test suite (100+ tests).

---

## v0.1.x

Core CLI: overview, session deep-dive, projects, diagnose, baseline/compare,
export, interactive HTML dashboard, configurable guardrails, auto-checkpoint.
