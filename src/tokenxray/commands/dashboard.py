"""Interactive HTML dashboard with charts and recommendations."""

import importlib.resources
import json
import webbrowser
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from tokenxray.colors import C
from tokenxray.config import get_model_label
from tokenxray.parser import load_all_sessions


def _chart_js() -> str:
    """Return the vendored Chart.js UMD bundle (offline-safe)."""
    try:
        pkg = importlib.resources.files("tokenxray") / "assets" / "chart.umd.min.js"
        return pkg.read_text(encoding="utf-8")
    except Exception:
        # Fallback to CDN if asset is somehow missing
        return ""  # caller handles empty string


def run(args):
    sessions = load_all_sessions(args.path, source_filter=getattr(args, "source", None))
    if not sessions:
        print(f"{C.RED}No sessions with usage data found.{C.RESET}")
        return

    data = _collect_data(sessions)
    html = _render_html(data)

    out_path = Path("tokenxray_dashboard.html")
    out_path.write_text(html)
    print(f"{C.GREEN}Dashboard saved to {out_path.resolve()}{C.RESET}")

    webbrowser.open(out_path.resolve().as_uri())


def _collect_data(sessions):
    total_cost = sum(s["cost"]["total"] for s in sessions)
    total_turns = sum(len(s["turns"]) for s in sessions)
    total_input = sum(s["total_input"] for s in sessions)
    total_output = sum(s["total_output"] for s in sessions)
    total_cache_read = sum(s["total_cache_read"] for s in sessions)
    total_cache_create = sum(s["total_cache_create"] for s in sessions)
    total_saved = sum(s["cost"]["cache_savings"] for s in sessions)
    total_no_cache = sum(s["cost"]["total_no_cache"] for s in sessions)

    # --- Daily cost trend ---
    daily = defaultdict(
        lambda: {
            "cost": 0,
            "sessions": 0,
            "turns": 0,
            "input_cost": 0,
            "output_cost": 0,
            "cache_read_cost": 0,
            "cache_create_cost": 0,
        }
    )
    for s in sessions:
        if s.get("start_time"):
            day = s["start_time"].strftime("%Y-%m-%d")
            daily[day]["cost"] += s["cost"]["total"]
            daily[day]["sessions"] += 1
            daily[day]["turns"] += len(s["turns"])
            daily[day]["input_cost"] += s["cost"]["input"]
            daily[day]["output_cost"] += s["cost"]["output"]
            daily[day]["cache_read_cost"] += s["cost"]["cache_read"]
            daily[day]["cache_create_cost"] += s["cost"]["cache_create"]

    sorted_days = sorted(daily.keys())
    daily_series = {
        "labels": sorted_days,
        "cost": [round(daily[d]["cost"], 2) for d in sorted_days],
        "sessions": [daily[d]["sessions"] for d in sorted_days],
        "turns": [daily[d]["turns"] for d in sorted_days],
        "cost_per_turn": [
            round(daily[d]["cost"] / daily[d]["turns"], 2)
            if daily[d]["turns"] > 0
            else 0
            for d in sorted_days
        ],
    }

    # 7-day moving average
    ma7 = []
    costs = daily_series["cost"]
    for i in range(len(costs)):
        window = costs[max(0, i - 6) : i + 1]
        ma7.append(round(sum(window) / len(window), 2))
    daily_series["ma7"] = ma7

    # --- Turn bucket distribution ---
    buckets = [
        ("1-10", lambda s: len(s["turns"]) <= 10),
        ("11-30", lambda s: 11 <= len(s["turns"]) <= 30),
        ("31-50", lambda s: 31 <= len(s["turns"]) <= 50),
        ("51-100", lambda s: 51 <= len(s["turns"]) <= 100),
        ("100+", lambda s: len(s["turns"]) > 100),
    ]
    turn_dist = {"labels": [], "sessions": [], "cost": [], "avg_cost": []}
    for label, filt in buckets:
        seg = [s for s in sessions if filt(s)]
        seg_cost = sum(s["cost"]["total"] for s in seg)
        turn_dist["labels"].append(label)
        turn_dist["sessions"].append(len(seg))
        turn_dist["cost"].append(round(seg_cost, 2))
        turn_dist["avg_cost"].append(round(seg_cost / len(seg), 2) if seg else 0)

    # --- Model distribution ---
    model_cost = defaultdict(float)
    model_sessions = defaultdict(int)
    for s in sessions:
        label = "Unknown"
        for m in s.get("models_used", []):
            lbl = get_model_label(m)
            if lbl != "unknown":
                label = lbl
                break
        model_cost[label] += s["cost"]["total"]
        model_sessions[label] += 1

    model_dist = {
        "labels": list(model_cost.keys()),
        "cost": [round(model_cost[lbl], 2) for lbl in model_cost],
        "sessions": [model_sessions[lbl] for lbl in model_cost],
    }

    # --- Project breakdown (top 15) ---
    project_cost = defaultdict(lambda: {"cost": 0, "sessions": 0, "turns": 0})
    for s in sessions:
        p = s["project"]
        # Clean up long project paths
        if p.startswith("-Users-"):
            parts = p.split("-")
            p = parts[-1] if len(parts) > 1 else p
        project_cost[p]["cost"] += s["cost"]["total"]
        project_cost[p]["sessions"] += 1
        project_cost[p]["turns"] += len(s["turns"])

    top_projects = sorted(project_cost.items(), key=lambda x: -x[1]["cost"])[:15]
    projects = {
        "labels": [p[0] for p in top_projects],
        "cost": [round(p[1]["cost"], 2) for p in top_projects],
        "sessions": [p[1]["sessions"] for p in top_projects],
    }

    # --- Tool usage (top 12) ---
    tool_totals = defaultdict(int)
    for s in sessions:
        for tool, count in s["tool_calls"].items():
            tool_totals[tool] += count

    top_tools = sorted(tool_totals.items(), key=lambda x: -x[1])[:12]
    tools = {
        "labels": [t[0] for t in top_tools],
        "counts": [t[1] for t in top_tools],
    }

    # --- Cache efficiency over time ---
    cache_series = {"labels": [], "hit_rate": [], "savings": []}
    for d in sorted_days:
        dd = daily[d]
        total_in = dd["input_cost"] + dd["cache_read_cost"] + dd["cache_create_cost"]
        hit_rate = (dd["cache_read_cost"] / total_in * 100) if total_in > 0 else 0
        cache_series["labels"].append(d)
        cache_series["hit_rate"].append(round(hit_rate, 1))
        cache_series["savings"].append(
            round(dd["input_cost"] - dd["cache_read_cost"], 2)
        )

    # --- Session heatmap (day of week × hour) ---
    heatmap = [[0] * 24 for _ in range(7)]
    for s in sessions:
        if s.get("start_time"):
            dow = s["start_time"].weekday()  # 0=Mon
            hour = s["start_time"].hour
            heatmap[dow][hour] += s["cost"]["total"]

    heatmap_data = []
    for dow in range(7):
        for hour in range(24):
            if heatmap[dow][hour] > 0:
                heatmap_data.append(
                    {"x": hour, "y": dow, "v": round(heatmap[dow][hour], 2)}
                )

    # --- Top 10 expensive sessions ---
    top_sessions = []
    for s in sorted(sessions, key=lambda s: -s["cost"]["total"])[:10]:
        p = s["project"]
        if p.startswith("-Users-"):
            parts = p.split("-")
            p = parts[-1] if len(parts) > 1 else p
        model_label = "unknown"
        for m in s.get("models_used", []):
            lbl = get_model_label(m)
            if lbl != "unknown":
                model_label = lbl
                break
        top_sessions.append(
            {
                "id": s["id"],
                "project": p,
                "turns": len(s["turns"]),
                "cost": round(s["cost"]["total"], 2),
                "model": model_label,
            }
        )

    # --- Cost breakdown by type ---
    cost_breakdown = {
        "labels": ["Input", "Output", "Cache Read", "Cache Create"],
        "values": [
            round(sum(s["cost"]["input"] for s in sessions), 2),
            round(sum(s["cost"]["output"] for s in sessions), 2),
            round(sum(s["cost"]["cache_read"] for s in sessions), 2),
            round(sum(s["cost"]["cache_create"] for s in sessions), 2),
        ],
    }

    # --- Recommendations ---
    recommendations = _generate_recommendations(sessions, total_cost)

    # --- Weekly trend ---
    weekly = defaultdict(lambda: {"cost": 0, "sessions": 0, "turns": 0})
    for s in sessions:
        if s.get("start_time"):
            week = s["start_time"].strftime("%Y-W%W")
            weekly[week]["cost"] += s["cost"]["total"]
            weekly[week]["sessions"] += 1
            weekly[week]["turns"] += len(s["turns"])

    sorted_weeks = sorted(weekly.keys())
    weekly_series = {
        "labels": sorted_weeks,
        "cost": [round(weekly[w]["cost"], 2) for w in sorted_weeks],
        "sessions": [weekly[w]["sessions"] for w in sorted_weeks],
        "cost_per_turn": [
            round(weekly[w]["cost"] / weekly[w]["turns"], 2)
            if weekly[w]["turns"] > 0
            else 0
            for w in sorted_weeks
        ],
    }

    return {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "summary": {
            "total_sessions": len(sessions),
            "total_turns": total_turns,
            "total_cost": round(total_cost, 2),
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_cache_read": total_cache_read,
            "total_cache_create": total_cache_create,
            "cache_savings": round(total_saved, 2),
            "cache_savings_pct": round(total_saved / total_no_cache * 100, 1)
            if total_no_cache > 0
            else 0,
            "avg_cost_per_turn": round(total_cost / total_turns, 2)
            if total_turns > 0
            else 0,
            "avg_cost_per_session": round(total_cost / len(sessions), 2)
            if sessions
            else 0,
        },
        "daily": daily_series,
        "weekly": weekly_series,
        "turn_distribution": turn_dist,
        "model_distribution": model_dist,
        "projects": projects,
        "tools": tools,
        "cache_series": cache_series,
        "heatmap": heatmap_data,
        "top_sessions": top_sessions,
        "cost_breakdown": cost_breakdown,
        "recommendations": recommendations,
    }


def _generate_recommendations(sessions, total_cost):
    recs = []

    # Marathon check
    marathons = [s for s in sessions if len(s["turns"]) > 100]
    marathon_cost = sum(s["cost"]["total"] for s in marathons)
    if marathons and total_cost > 0 and marathon_cost / total_cost > 0.5:
        avg_turns = sum(len(s["turns"]) for s in marathons) / len(marathons)
        savings = marathon_cost * 0.30
        recs.append(
            {
                "severity": "critical",
                "title": "Marathon sessions are burning your wallet",
                "detail": (
                    f"{len(marathons)} sessions with 100+ turns cost "
                    f"${marathon_cost:,.0f} ({marathon_cost / total_cost * 100:.0f}% of total). "
                    f"Average: {avg_turns:.0f} turns per session."
                ),
                "action": f"Split sessions at 50-80 turns. Potential savings: ~${savings:,.0f}.",
                "savings": round(savings, 0),
            }
        )

    # Cache creation
    total_cc = sum(s["cost"]["cache_create"] for s in sessions)
    cc_pct = total_cc / total_cost * 100 if total_cost > 0 else 0
    if cc_pct > 30:
        recs.append(
            {
                "severity": "high",
                "title": f"Cache creation is {cc_pct:.0f}% of total cost",
                "detail": (
                    f"${total_cc:,.0f} in cache creation fees (25% premium over input). "
                    f"Triggered whenever new content enters context."
                ),
                "action": "Shorter prompts, partial file reads, concise responses reduce cache creation.",
                "savings": round(total_cc * 0.20, 0),
            }
        )

    # Model choice
    opus = [s for s in sessions if any("opus" in m for m in s["models_used"])]
    if opus:
        opus_cost = sum(s["cost"]["total"] for s in opus)
        sonnet_eq = opus_cost / 5
        savings = opus_cost - sonnet_eq
        if savings > 10:
            recs.append(
                {
                    "severity": "medium",
                    "title": f"Opus is {opus_cost / total_cost * 100:.0f}% of spend",
                    "detail": (
                        f"${opus_cost:,.0f} on Opus across {len(opus)} sessions. "
                        f"Same work on Sonnet would cost ~${sonnet_eq:,.0f}."
                    ),
                    "action": "Use Sonnet for routine tasks, Opus for complex reasoning.",
                    "savings": round(savings, 0),
                }
            )

    # Subagents
    agents = [s for s in sessions if s["project"] == "subagents"]
    if agents:
        agent_cost = sum(s["cost"]["total"] for s in agents)
        pct = agent_cost / total_cost * 100 if total_cost > 0 else 0
        if pct > 10:
            recs.append(
                {
                    "severity": "high",
                    "title": f"Subagents: ${agent_cost:,.0f} ({pct:.0f}% of total)",
                    "detail": f"{len(agents)} subagent sessions with independent contexts.",
                    "action": "Prefer Grep/Read/Glob over Agent for simple lookups.",
                    "savings": round(agent_cost * 0.30, 0),
                }
            )

    # Weekly burn rate
    timed = [s for s in sessions if s.get("start_time") and s.get("end_time")]
    if timed:
        now = (
            datetime.now(timed[0]["start_time"].tzinfo)
            if timed[0]["start_time"].tzinfo
            else datetime.now()
        )
        recent = [
            s
            for s in timed
            if s["end_time"]
            and (
                now - s["end_time"].replace(tzinfo=now.tzinfo if now.tzinfo else None)
            ).days
            < 7
        ]
        if recent:
            cost_7d = sum(s["cost"]["total"] for s in recent)
            monthly = cost_7d / 7 * 30
            if monthly > 50:
                recs.append(
                    {
                        "severity": "info",
                        "title": f"Projected: ${monthly:,.0f}/month",
                        "detail": f"Last 7 days: ${cost_7d:,.0f} across {len(recent)} sessions.",
                        "action": "Apply recommendations above to reduce burn rate.",
                        "savings": 0,
                    }
                )

    return recs


def _render_html(data):
    # P10: escape </script> to prevent premature tag close in embedded JSON
    data_json = json.dumps(data).replace("</", "<\\/")
    chart_js = _chart_js()
    chart_script_tag = (
        f"<script>{chart_js}</script>"
        if chart_js
        else (
            '<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"></script>'
        )
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>TokenXRay Dashboard</title>
{chart_script_tag}
<style>
  :root {{
    --bg: #0d1117; --surface: #161b22; --border: #30363d;
    --text: #e6edf3; --text-dim: #8b949e; --accent: #58a6ff;
    --green: #3fb950; --yellow: #d29922; --red: #f85149; --orange: #db6d28;
    --purple: #bc8cff; --pink: #f778ba;
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
    background: var(--bg); color: var(--text); line-height: 1.5;
    padding: 24px; max-width: 1400px; margin: 0 auto;
  }}
  h1 {{ font-size: 28px; margin-bottom: 4px; }}
  h2 {{ font-size: 18px; color: var(--accent); margin-bottom: 12px; }}
  .subtitle {{ color: var(--text-dim); font-size: 14px; margin-bottom: 24px; }}
  .grid {{ display: grid; gap: 20px; margin-bottom: 24px; }}
  .grid-4 {{ grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); }}
  .grid-2 {{ grid-template-columns: repeat(auto-fit, minmax(400px, 1fr)); }}
  .grid-3 {{ grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); }}
  .card {{
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 8px; padding: 20px;
  }}
  .stat-card {{ text-align: center; }}
  .stat-value {{ font-size: 32px; font-weight: 700; color: var(--accent); }}
  .stat-label {{ font-size: 13px; color: var(--text-dim); margin-top: 4px; }}
  .stat-sub {{ font-size: 12px; color: var(--text-dim); margin-top: 2px; }}
  .chart-card {{ min-height: 320px; }}
  .chart-card canvas {{ max-height: 300px; }}
  .rec-card {{ border-left: 4px solid var(--border); }}
  .rec-card.critical {{ border-left-color: var(--red); }}
  .rec-card.high {{ border-left-color: var(--orange); }}
  .rec-card.medium {{ border-left-color: var(--yellow); }}
  .rec-card.info {{ border-left-color: var(--accent); }}
  .rec-title {{ font-weight: 600; margin-bottom: 6px; }}
  .rec-detail {{ color: var(--text-dim); font-size: 13px; margin-bottom: 6px; }}
  .rec-action {{ color: var(--green); font-size: 13px; }}
  .rec-savings {{ color: var(--yellow); font-size: 13px; font-weight: 600; margin-top: 4px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
  th {{ text-align: left; color: var(--text-dim); font-weight: 500; padding: 8px 12px;
       border-bottom: 1px solid var(--border); }}
  td {{ padding: 8px 12px; border-bottom: 1px solid var(--border); }}
  tr:hover td {{ background: rgba(88, 166, 255, 0.05); }}
  .cost-high {{ color: var(--red); font-weight: 600; }}
  .cost-med {{ color: var(--yellow); }}
  .cost-low {{ color: var(--green); }}
  .heatmap-grid {{
    display: grid; grid-template-columns: 50px repeat(24, 1fr); gap: 2px;
    font-size: 11px;
  }}
  .heatmap-cell {{
    aspect-ratio: 1; border-radius: 3px; display: flex;
    align-items: center; justify-content: center; font-size: 10px;
  }}
  .heatmap-label {{ display: flex; align-items: center; color: var(--text-dim); font-size: 11px; }}
  .section-header {{ margin: 32px 0 16px; }}
  .footer {{
    text-align: center; color: var(--text-dim); font-size: 12px;
    margin-top: 40px; padding-top: 20px; border-top: 1px solid var(--border);
  }}
  .tabs {{ display: flex; gap: 8px; margin-bottom: 16px; }}
  .tab {{
    padding: 6px 16px; border-radius: 6px; cursor: pointer;
    background: var(--surface); border: 1px solid var(--border);
    color: var(--text-dim); font-size: 13px; transition: all 0.2s;
  }}
  .tab.active {{ background: var(--accent); color: var(--bg); border-color: var(--accent); }}
  .tab:hover {{ border-color: var(--accent); }}
</style>
</head>
<body>

<h1>TokenXRay Dashboard</h1>
<p class="subtitle">Generated {data["generated"]} &mdash; {data["summary"]["total_sessions"]} sessions analyzed</p>

<!-- Summary Cards -->
<div class="grid grid-4" id="summaryCards"></div>

<!-- Daily Spend + Cost/Turn -->
<div class="grid grid-2">
  <div class="card chart-card">
    <h2>Daily Spend</h2>
    <canvas id="dailyCost"></canvas>
  </div>
  <div class="card chart-card">
    <h2>Cost per Turn (Daily)</h2>
    <canvas id="costPerTurn"></canvas>
  </div>
</div>

<!-- Weekly Trend + Turn Distribution -->
<div class="grid grid-2">
  <div class="card chart-card">
    <h2>Weekly Trend</h2>
    <canvas id="weeklyCost"></canvas>
  </div>
  <div class="card chart-card">
    <h2>Session Length vs Cost</h2>
    <canvas id="turnDist"></canvas>
  </div>
</div>

<!-- Cost Breakdown + Model Distribution -->
<div class="grid grid-3">
  <div class="card chart-card">
    <h2>Cost by Type</h2>
    <canvas id="costBreakdown"></canvas>
  </div>
  <div class="card chart-card">
    <h2>Model Distribution</h2>
    <canvas id="modelDist"></canvas>
  </div>
  <div class="card chart-card">
    <h2>Top Tools</h2>
    <canvas id="toolUsage"></canvas>
  </div>
</div>

<!-- Projects -->
<div class="card chart-card" style="margin-bottom: 24px;">
  <h2>Cost by Project</h2>
  <canvas id="projectCost" style="max-height: 400px;"></canvas>
</div>

<!-- Activity Heatmap -->
<div class="card" style="margin-bottom: 24px;">
  <h2>Activity Heatmap (cost by day &times; hour)</h2>
  <div id="heatmapContainer" class="heatmap-grid" style="margin-top: 12px;"></div>
</div>

<!-- Top Sessions Table -->
<div class="card" style="margin-bottom: 24px;">
  <h2>Top 10 Most Expensive Sessions</h2>
  <table>
    <thead><tr><th>Session</th><th>Project</th><th>Turns</th><th>Cost</th><th>Model</th></tr></thead>
    <tbody id="topSessionsBody"></tbody>
  </table>
</div>

<!-- Recommendations -->
<h2 class="section-header" style="color: var(--accent); font-size: 20px;">Recommendations</h2>
<div class="grid grid-2" id="recsContainer"></div>

<div class="footer">
  TokenXRay &mdash; See where your AI coding tokens actually go.
  &bull; <a href="https://github.com/Crack525/tokenxray" style="color: var(--accent);">GitHub</a>
  &bull; pip install tokenxray
</div>

<script>
const D = {data_json};

Chart.defaults.color = '#8b949e';
Chart.defaults.borderColor = '#30363d';
Chart.defaults.font.family = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif";

const COLORS = ['#58a6ff','#3fb950','#d29922','#f85149','#bc8cff','#f778ba','#db6d28','#79c0ff','#56d364','#e3b341','#ff7b72','#d2a8ff'];

// --- Summary Cards ---
document.getElementById('summaryCards').innerHTML = `
  <div class="card stat-card">
    <div class="stat-value">$${{D.summary.total_cost.toLocaleString()}}</div>
    <div class="stat-label">Total Cost</div>
    <div class="stat-sub">$${{D.summary.avg_cost_per_session.toFixed(2)}}/session avg</div>
  </div>
  <div class="card stat-card">
    <div class="stat-value">${{D.summary.total_sessions.toLocaleString()}}</div>
    <div class="stat-label">Sessions</div>
    <div class="stat-sub">${{D.summary.total_turns.toLocaleString()}} total turns</div>
  </div>
  <div class="card stat-card">
    <div class="stat-value">$${{D.summary.cache_savings.toLocaleString()}}</div>
    <div class="stat-label">Cache Savings</div>
    <div class="stat-sub">${{D.summary.cache_savings_pct}}% saved by caching</div>
  </div>
  <div class="card stat-card">
    <div class="stat-value">$${{D.summary.avg_cost_per_turn.toFixed(2)}}</div>
    <div class="stat-label">Avg Cost/Turn</div>
    <div class="stat-sub">across all sessions</div>
  </div>
`;

// --- Daily Cost Chart ---
new Chart(document.getElementById('dailyCost'), {{
  type: 'bar',
  data: {{
    labels: D.daily.labels,
    datasets: [
      {{ label: 'Daily Cost', data: D.daily.cost, backgroundColor: '#58a6ff44', borderColor: '#58a6ff', borderWidth: 1 }},
      {{ label: '7-day Avg', data: D.daily.ma7, type: 'line', borderColor: '#f85149', borderWidth: 2, pointRadius: 0, fill: false }},
    ]
  }},
  options: {{
    responsive: true, plugins: {{ legend: {{ position: 'top' }} }},
    scales: {{ y: {{ beginAtZero: true, ticks: {{ callback: v => '$' + v }} }} }}
  }}
}});

// --- Cost per Turn ---
new Chart(document.getElementById('costPerTurn'), {{
  type: 'line',
  data: {{
    labels: D.daily.labels,
    datasets: [{{ label: '$/turn', data: D.daily.cost_per_turn, borderColor: '#3fb950', borderWidth: 2, pointRadius: 1, fill: {{ target: 'origin', alpha: 0.1 }} }}]
  }},
  options: {{
    responsive: true, plugins: {{ legend: {{ display: false }} }},
    scales: {{ y: {{ beginAtZero: true, ticks: {{ callback: v => '$' + v.toFixed(2) }} }} }}
  }}
}});

// --- Weekly Cost ---
new Chart(document.getElementById('weeklyCost'), {{
  type: 'bar',
  data: {{
    labels: D.weekly.labels,
    datasets: [
      {{ label: 'Weekly Cost', data: D.weekly.cost, backgroundColor: '#bc8cff44', borderColor: '#bc8cff', borderWidth: 1 }},
      {{ label: '$/turn', data: D.weekly.cost_per_turn, type: 'line', borderColor: '#d29922', borderWidth: 2, pointRadius: 2, yAxisID: 'y1' }},
    ]
  }},
  options: {{
    responsive: true,
    scales: {{
      y: {{ beginAtZero: true, ticks: {{ callback: v => '$' + v }} }},
      y1: {{ position: 'right', beginAtZero: true, grid: {{ drawOnChartArea: false }}, ticks: {{ callback: v => '$' + v.toFixed(2) }} }}
    }}
  }}
}});

// --- Turn Distribution ---
new Chart(document.getElementById('turnDist'), {{
  type: 'bar',
  data: {{
    labels: D.turn_distribution.labels,
    datasets: [
      {{ label: 'Sessions', data: D.turn_distribution.sessions, backgroundColor: '#58a6ff88', yAxisID: 'y' }},
      {{ label: 'Total Cost', data: D.turn_distribution.cost, backgroundColor: '#f8514988', yAxisID: 'y1' }},
    ]
  }},
  options: {{
    responsive: true,
    scales: {{
      y: {{ beginAtZero: true, title: {{ display: true, text: 'Sessions' }} }},
      y1: {{ position: 'right', beginAtZero: true, grid: {{ drawOnChartArea: false }},
             ticks: {{ callback: v => '$' + v }}, title: {{ display: true, text: 'Cost' }} }}
    }}
  }}
}});

// --- Cost Breakdown Doughnut ---
new Chart(document.getElementById('costBreakdown'), {{
  type: 'doughnut',
  data: {{
    labels: D.cost_breakdown.labels,
    datasets: [{{ data: D.cost_breakdown.values, backgroundColor: COLORS.slice(0, 4), borderWidth: 0 }}]
  }},
  options: {{
    responsive: true, cutout: '55%',
    plugins: {{ legend: {{ position: 'bottom' }},
      tooltip: {{ callbacks: {{ label: ctx => ctx.label + ': $' + ctx.parsed.toLocaleString() }} }}
    }}
  }}
}});

// --- Model Distribution ---
new Chart(document.getElementById('modelDist'), {{
  type: 'doughnut',
  data: {{
    labels: D.model_distribution.labels,
    datasets: [{{ data: D.model_distribution.cost, backgroundColor: COLORS, borderWidth: 0 }}]
  }},
  options: {{
    responsive: true, cutout: '55%',
    plugins: {{ legend: {{ position: 'bottom' }},
      tooltip: {{ callbacks: {{ label: ctx => ctx.label + ': $' + ctx.parsed.toLocaleString() + ' (' + D.model_distribution.sessions[ctx.dataIndex] + ' sessions)' }} }}
    }}
  }}
}});

// --- Tool Usage ---
new Chart(document.getElementById('toolUsage'), {{
  type: 'bar',
  data: {{
    labels: D.tools.labels,
    datasets: [{{ data: D.tools.counts, backgroundColor: COLORS, borderWidth: 0 }}]
  }},
  options: {{
    responsive: true, indexAxis: 'y',
    plugins: {{ legend: {{ display: false }} }},
    scales: {{ x: {{ beginAtZero: true }} }}
  }}
}});

// --- Project Cost ---
new Chart(document.getElementById('projectCost'), {{
  type: 'bar',
  data: {{
    labels: D.projects.labels,
    datasets: [{{ data: D.projects.cost, backgroundColor: COLORS.concat(COLORS), borderWidth: 0 }}]
  }},
  options: {{
    responsive: true, indexAxis: 'y',
    plugins: {{ legend: {{ display: false }},
      tooltip: {{ callbacks: {{ label: ctx => '$' + ctx.parsed.x.toLocaleString() + ' (' + D.projects.sessions[ctx.dataIndex] + ' sessions)' }} }}
    }},
    scales: {{ x: {{ beginAtZero: true, ticks: {{ callback: v => '$' + v }} }} }}
  }}
}});

// --- Heatmap ---
(function() {{
  const container = document.getElementById('heatmapContainer');
  const days = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
  const maxV = Math.max(...D.heatmap.map(h => h.v), 1);

  // Header row
  container.innerHTML = '<div></div>';
  for (let h = 0; h < 24; h++) {{
    container.innerHTML += `<div class="heatmap-label" style="justify-content:center;">${{h}}</div>`;
  }}

  for (let dow = 0; dow < 7; dow++) {{
    container.innerHTML += `<div class="heatmap-label">${{days[dow]}}</div>`;
    for (let hour = 0; hour < 24; hour++) {{
      const cell = D.heatmap.find(h => h.x === hour && h.y === dow);
      const v = cell ? cell.v : 0;
      const intensity = v > 0 ? Math.max(0.15, v / maxV) : 0.03;
      const bg = v > 0 ? `rgba(88,166,255,${{intensity.toFixed(2)}})` : 'rgba(48,54,61,0.3)';
      const text = v > 10 ? '$' + Math.round(v) : '';
      container.innerHTML += `<div class="heatmap-cell" style="background:${{bg}}" title="${{days[dow]}} ${{hour}}:00 — $${{v.toFixed(0)}}">${{text}}</div>`;
    }}
  }}
}})();

// --- Top Sessions Table ---
(function() {{
  const tbody = document.getElementById('topSessionsBody');
  D.top_sessions.forEach(s => {{
    const cls = s.cost > 500 ? 'cost-high' : s.cost > 50 ? 'cost-med' : 'cost-low';
    const tr = document.createElement('tr');
    const cells = [
      [s.id, 'font-family:monospace', null],
      [s.project, null, null],
      [s.turns.toLocaleString(), null, null],
      ['$' + s.cost.toLocaleString(), null, cls],
      [s.model, null, null],
    ];
    cells.forEach(([text, style, className]) => {{
      const td = document.createElement('td');
      td.textContent = text;
      if (style) td.setAttribute('style', style);
      if (className) td.className = className;
      tr.appendChild(td);
    }});
    tbody.appendChild(tr);
  }});
}})();

// --- Recommendations ---
(function() {{
  const container = document.getElementById('recsContainer');
  if (D.recommendations.length === 0) {{
    const card = document.createElement('div');
    card.className = 'card';
    card.innerHTML = '<p style="color: var(--green);">No major issues found. Your token usage looks healthy!</p>';
    container.appendChild(card);
    return;
  }}
  D.recommendations.forEach(r => {{
    const card = document.createElement('div');
    card.className = `card rec-card ${{r.severity}}`;
    const title = document.createElement('div');
    title.className = 'rec-title'; title.textContent = r.title;
    const detail = document.createElement('div');
    detail.className = 'rec-detail'; detail.textContent = r.detail;
    const action = document.createElement('div');
    action.className = 'rec-action'; action.textContent = r.action;
    card.appendChild(title); card.appendChild(detail); card.appendChild(action);
    if (r.savings > 0) {{
      const sav = document.createElement('div');
      sav.className = 'rec-savings';
      sav.textContent = `Potential savings: ~$${{r.savings.toLocaleString()}}`;
      card.appendChild(sav);
    }}
    container.appendChild(card);
  }});
}})();
</script>
</body>
</html>"""
