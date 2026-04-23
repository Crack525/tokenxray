# TokenXRay Changelog

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
