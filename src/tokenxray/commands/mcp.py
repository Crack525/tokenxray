"""MCP tool usage audit — which servers are dead weight?"""

import json
import subprocess
import os
from collections import defaultdict
from pathlib import Path

from tokenxray.colors import C
from tokenxray.display import fmt_cost, fmt_tokens, bar
from tokenxray.parser import load_all_sessions

# Approximate tokens per tool schema (based on real measurements: ~15K tokens / 84 tools)
TOKENS_PER_TOOL_SCHEMA = 185


def _read_mcp_servers():
    """Read configured MCP servers from ~/.claude.json."""
    claude_json = Path.home() / ".claude.json"
    if not claude_json.exists():
        return {}
    try:
        with open(claude_json) as f:
            data = json.load(f)
        return data.get("mcpServers", {})
    except Exception:
        return {}


def _enumerate_server_tools(server_config, timeout=5):
    """Try to enumerate available tools from an MCP server via stdio JSON-RPC.
    Returns list of tool names, or None if enumeration fails."""
    cmd = server_config.get("command")
    args = server_config.get("args", [])
    env_overrides = server_config.get("env", {})

    if not cmd:
        return None

    full_cmd = [cmd] + (args or [])
    full_env = os.environ.copy()
    full_env.update(env_overrides or {})

    # MCP JSON-RPC: initialize then tools/list
    init_req = json.dumps({
        "jsonrpc": "2.0", "id": 0, "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "tokenxray", "version": "1.0"},
        },
    }) + "\n"
    list_req = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {},
    }) + "\n"

    proc = None
    try:
        proc = subprocess.Popen(
            full_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=full_env,
            text=True,
        )
        stdout, _ = proc.communicate(input=init_req + list_req, timeout=timeout)

        for line in stdout.strip().split("\n"):
            if not line:
                continue
            try:
                resp = json.loads(line)
                if resp.get("id") == 1:
                    tools = resp.get("result", {}).get("tools", [])
                    return [t["name"] for t in tools if t.get("name")]
            except json.JSONDecodeError:
                continue
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError, PermissionError, OSError):
        return None
    finally:
        if proc:
            try:
                proc.kill()
            except Exception:
                pass


def _avg_input_price(sessions) -> float:
    """Return average input price ($/MTok) across sessions, or Sonnet default if unknown."""
    total_cost = sum(s.get("cost", {}).get("input", 0.0) for s in sessions)
    total_tokens = sum(s.get("total_input", 0) for s in sessions)
    if total_tokens > 0:
        return total_cost / total_tokens * 1e6
    return 3.0  # Sonnet default fallback


def run(args):
    sessions = load_all_sessions(args.path, source_filter="claude")
    if not sessions:
        print(f"{C.RED}No Claude Code sessions found.{C.RESET}")
        return

    mcp_servers = _read_mcp_servers()
    enumerate_tools = getattr(args, "enumerate_tools", False)

    avg_input_price = _avg_input_price(sessions)

    # Aggregate tool usage across all sessions
    server_tool_calls = defaultdict(lambda: defaultdict(int))  # server -> tool -> total calls
    server_session_count = defaultdict(int)                    # server -> session count
    sessions_with_any_mcp = 0
    first_mcp_time = None  # earliest session that ever called an MCP tool

    for s in sessions:
        session_servers = set()
        for tool_name, count in s["tool_calls"].items():
            if not tool_name.startswith("mcp__"):
                continue
            parts = tool_name.split("__", 2)
            if len(parts) < 3:
                continue
            server, tool = parts[1], parts[2]
            server_tool_calls[server][tool] += count
            session_servers.add(server)

        if session_servers:
            sessions_with_any_mcp += 1
            for server in session_servers:
                server_session_count[server] += 1
            st = s.get("start_time")
            if st and (first_mcp_time is None or st < first_mcp_time):
                first_mcp_time = st

    # Only count sessions from after MCP was first configured (avoids inflating
    # dead-weight estimates with old sessions that predate any MCP usage).
    if first_mcp_time is not None:
        sessions = [
            s for s in sessions
            if s.get("start_time") is None or s["start_time"] >= first_mcp_time
        ]

    if not sessions:
        print(f"{C.DIM}No sessions found after MCP first use. Nothing to audit.{C.RESET}")
        return

    # Optionally enumerate available tools from live MCP servers
    server_available_tools = {}
    if enumerate_tools and mcp_servers:
        print(f"{C.DIM}  Enumerating tools from MCP servers...{C.RESET}")
        for server_name, server_cfg in mcp_servers.items():
            tools = _enumerate_server_tools(server_cfg)
            if tools is not None:
                server_available_tools[server_name] = tools

    _display(sessions, mcp_servers, server_tool_calls, server_session_count,
             sessions_with_any_mcp, server_available_tools, avg_input_price)


def _display(sessions, mcp_servers, server_tool_calls, server_session_count,
             sessions_with_any_mcp, server_available_tools, avg_input_price=3.0):
    total = len(sessions)
    zero_mcp = total - sessions_with_any_mcp
    all_servers = sorted(set(list(mcp_servers.keys()) + list(server_tool_calls.keys())))

    print()
    print(f"{C.BOLD}{C.CYAN}TokenXRay — MCP Tool Audit{C.RESET}  {C.DIM}(Claude Code sessions only){C.RESET}")
    print(f"{C.DIM}{'─' * 70}{C.RESET}")
    print(
        f"  Configured servers: {C.BOLD}{len(mcp_servers)}{C.RESET}  |  "
        f"Sessions analyzed: {C.BOLD}{total}{C.RESET}  |  "
        f"Sessions with MCP calls: {C.BOLD}{sessions_with_any_mcp}{C.RESET} "
        f"({sessions_with_any_mcp / total * 100:.1f}%)"
    )

    # ── Dead-weight section ───────────────────────────────────────────────────
    if zero_mcp > 0 and mcp_servers:
        print()
        print(f"  {C.RED}{C.BOLD}Schema Dead Weight{C.RESET}")
        print(f"  {C.DIM}{'─' * 50}{C.RESET}")

        # Estimate tool counts per server
        est_tools = {}
        for server in mcp_servers:
            if server in server_available_tools:
                est_tools[server] = len(server_available_tools[server])
            elif server in server_tool_calls:
                # Lower bound: tools we've actually seen called
                est_tools[server] = len(server_tool_calls[server])
            else:
                est_tools[server] = 0

        total_est = sum(est_tools.values())
        tokens_per_session = total_est * TOKENS_PER_TOOL_SCHEMA
        wasted_tokens = zero_mcp * tokens_per_session
        wasted_cost = (wasted_tokens / 1e6) * avg_input_price

        note = "" if server_available_tools else f"  {C.DIM}(tool count from call history — run --enumerate-tools for exact count){C.RESET}"
        print(
            f"  {zero_mcp} of {total} sessions ({zero_mcp / total * 100:.0f}%) "
            f"loaded MCP schemas but called {C.BOLD}zero{C.RESET} MCP tools."
        )
        if note:
            print(note)
        print(
            f"  Estimated schema load: ~{total_est} tools × {TOKENS_PER_TOOL_SCHEMA} tokens "
            f"= {fmt_tokens(tokens_per_session)} per session"
        )
        if wasted_cost > 0.001:
            print(
                f"  {C.RED}Dead-session schema waste: ~{fmt_tokens(wasted_tokens)} tokens "
                f"≈ {fmt_cost(wasted_cost)}{C.RESET}"
            )

    # ── Per-server breakdown ──────────────────────────────────────────────────
    for server_name in all_servers:
        tools_called = server_tool_calls.get(server_name, {})
        sess_count = server_session_count.get(server_name, 0)
        avail_tools = server_available_tools.get(server_name)  # None if not enumerated
        in_config = server_name in mcp_servers

        total_calls = sum(tools_called.values())
        n_called = len(tools_called)
        n_avail = len(avail_tools) if avail_tools is not None else None

        sess_pct = sess_count / total * 100 if total > 0 else 0
        config_tag = f"{C.GREEN}configured{C.RESET}" if in_config else f"{C.YELLOW}history only{C.RESET}"

        print()
        print(f"  {C.BOLD}SERVER: {server_name}{C.RESET}  [{config_tag}]")
        print(f"  {C.DIM}{'─' * 50}{C.RESET}")

        # Usage summary line
        avail_str = f"/{n_avail}" if n_avail is not None else ""
        never_str = ""
        if n_avail is not None and n_avail > n_called:
            never_str = f"  |  {C.RED}never called: {n_avail - n_called}{C.RESET}"
        print(
            f"  Used in {sess_count}/{total} sessions ({sess_pct:.1f}%)  |  "
            f"Total calls: {total_calls}  |  Tools called: {n_called}{avail_str}{never_str}"
        )

        if not tools_called:
            print(f"  {C.RED}No calls recorded — this server may be pure dead weight.{C.RESET}")
            continue

        # Tool call table
        print()
        max_calls = max(tools_called.values())
        for tool, count in sorted(tools_called.items(), key=lambda x: x[1], reverse=True):
            pct = count / total_calls * 100
            print(
                f"    {tool:<45} {count:>5} calls  "
                f"({pct:>4.0f}%)  {C.BLUE}{bar(count, max_calls, 20)}{C.RESET}"
            )

        # Never-called tools (only when we have full enumeration)
        if avail_tools is not None:
            called_set = set(tools_called.keys())
            dead = [t for t in avail_tools if t not in called_set]
            if dead:
                print()
                print(f"  {C.RED}Never called ({len(dead)} tools):{C.RESET}")
                # Print in rows of 3
                for i in range(0, len(dead), 3):
                    row = dead[i:i + 3]
                    print(f"    {C.DIM}{',  '.join(row)}{C.RESET}")

    # ── Recommendations ───────────────────────────────────────────────────────
    print()
    print(f"  {C.BOLD}Recommendations{C.RESET}")
    print(f"  {C.DIM}{'─' * 50}{C.RESET}")

    recs_shown = 0

    if zero_mcp / total > 0.7 and mcp_servers:
        print(
            f"  {C.RED}[!!!]{C.RESET} {zero_mcp / total * 100:.0f}% of sessions never touch MCP tools.\n"
            f"        Use a project-level .mcp.json to enable MCP only in work directories,\n"
            f"        not globally for every session."
        )
        recs_shown += 1

    unused_servers = [s for s in mcp_servers if server_session_count.get(s, 0) == 0]
    if unused_servers:
        print(
            f"  {C.YELLOW}[!! ]{C.RESET} Servers with zero calls: {', '.join(unused_servers)}\n"
            f"        Consider removing from global config if not actively used."
        )
        recs_shown += 1

    for server_name in all_servers:
        if server_name not in server_available_tools:
            continue
        avail = server_available_tools[server_name]
        called = set(server_tool_calls.get(server_name, {}).keys())
        dead_count = len([t for t in avail if t not in called])
        if dead_count > 0:
            savings_tokens = dead_count * TOKENS_PER_TOOL_SCHEMA * total
            savings_cost = (savings_tokens / 1e6) * avg_input_price
            print(
                f"  {C.BLUE}[!  ]{C.RESET} {server_name}: {dead_count} tools never called.\n"
                f"        Removing them would save ~{fmt_tokens(savings_tokens)} tokens "
                f"(~{fmt_cost(savings_cost)}) over your session history."
            )
            recs_shown += 1

    if not server_available_tools and mcp_servers:
        print(
            f"  {C.DIM}[inf] Run `tokenxray --mcp --enumerate-tools` to get exact tool counts\n"
            f"        and identify never-called tools per server.{C.RESET}"
        )
        recs_shown += 1

    if recs_shown == 0:
        print(f"  {C.GREEN}MCP usage looks healthy — no major dead-weight found.{C.RESET}")

    print()
