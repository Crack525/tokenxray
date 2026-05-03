"""Memory hit rate — which injected crossmem memories were actually used."""

import json
import re
from collections import defaultdict
from datetime import datetime

from tokenxray.colors import C
from tokenxray.config import DATA_DIR
from tokenxray.parser import find_session_files

INJECTION_LOG = DATA_DIR / "memory_injections.jsonl"
_WORD_RE = re.compile(r"[a-z0-9]+")


def _words(text: str) -> set[str]:
    return set(_WORD_RE.findall(text.lower()))


def _load_injections() -> list[dict]:
    if not INJECTION_LOG.exists():
        return []
    records = []
    with INJECTION_LOG.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                r["_ts"] = datetime.fromisoformat(r["ts"].replace("Z", "+00:00"))
                records.append(r)
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
    return records


def _index_sessions(session_files: list[str]) -> list[dict]:
    """Return list of {file, start_time, end_time} without full parse (fast scan)."""
    index = []
    for filepath in session_files:
        start = end = None
        try:
            with open(filepath) as fh:
                for raw in fh:
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        entry = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    ts_str = entry.get("timestamp")
                    if not ts_str:
                        continue
                    try:
                        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    except ValueError:
                        continue
                    if start is None:
                        start = dt
                    end = dt
        except OSError:
            continue
        if start and end:
            index.append({"file": filepath, "start": start, "end": end})
    return index


def _get_assistant_text_after(filepath: str, after_ts: datetime) -> str:
    """Read raw JSONL and collect all assistant text blocks after a timestamp."""
    parts = []
    try:
        with open(filepath) as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    entry = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if entry.get("type") != "assistant":
                    continue
                ts_str = entry.get("timestamp")
                if not ts_str:
                    continue
                try:
                    dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                except ValueError:
                    continue
                if dt <= after_ts:
                    continue
                msg = entry.get("message", {})
                for block in msg.get("content", []):
                    if isinstance(block, dict) and block.get("type") == "text":
                        parts.append(block.get("text", ""))
    except OSError:
        pass
    return " ".join(parts)


def _memory_keywords(mem: dict) -> set[str]:
    """Extract searchable words from a memory record."""
    combined = f"{mem.get('keywords', '')} {mem.get('snippet', '')}"
    words = _words(combined)
    # strip very short tokens
    return {w for w in words if len(w) > 2}


def run(_args) -> None:
    injections = _load_injections()
    if not injections:
        print(
            f"{C.yellow('No injection log found.')}\n"
            f"crossmem writes to {INJECTION_LOG} when memories are injected.\n"
            "Ensure crossmem >= 1.5.0 is installed and the prompt-search hook is active."
        )
        return

    # Include subagent sessions — crossmem hooks fire inside subagents too
    session_files = find_session_files(include_subagents=True)
    if not session_files:
        print(C.yellow("No Claude session files found."))
        return

    print(f"Scanning {len(session_files)} sessions (incl. subagents) against {len(injections)} injections…")
    session_index = _index_sessions(session_files)

    # Aggregate per memory id: {id: {snippet, injections, hits}}
    stats: dict[int, dict] = defaultdict(lambda: {"snippet": "", "keywords": set(), "injections": 0, "hits": 0})
    unmatched = 0  # injections with no session in range (e.g. very recent or orphaned)

    for record in injections:
        inj_ts = record["_ts"]

        # Find the session whose time range contains this injection
        session = next(
            (s for s in session_index if s["start"] <= inj_ts <= s["end"]),
            None,
        )
        if session is None:
            unmatched += len(record.get("memories", []))
            continue

        assistant_text = _get_assistant_text_after(session["file"], inj_ts)
        if not assistant_text:
            continue
        response_words = _words(assistant_text)

        for mem in record.get("memories", []):
            mid = mem.get("id")
            if mid is None:
                continue
            s = stats[mid]
            s["snippet"] = mem.get("snippet", "")[:80]
            kw = _memory_keywords(mem)
            s["keywords"] |= kw
            s["injections"] += 1
            # Hit = at least 2 keyword tokens appear in the assistant response
            overlap = kw & response_words
            if len(overlap) >= 2:
                s["hits"] += 1

    if not stats:
        print(C.yellow("No matched injections found in session files."))
        print("Sessions may have ended before injection timestamps, or log is very recent.")
        return

    # Sort by hit rate ascending (pruning candidates first)
    rows = []
    for mid, s in stats.items():
        rate = s["hits"] / s["injections"] if s["injections"] else 0
        rows.append((mid, s, rate))
    rows.sort(key=lambda x: x[2])

    total_injections = sum(s["injections"] for _, s, _ in rows)
    total_hits = sum(s["hits"] for _, s, _ in rows)
    overall_rate = total_hits / total_injections if total_injections else 0

    print()
    print(f"{C.bold('Memory Hit Rate')}  —  {total_hits}/{total_injections} injections used  ({overall_rate:.0%} overall)")
    print()

    header = f"{'ID':>4}  {'Injections':>10}  {'Hits':>4}  {'Rate':>6}  Snippet"
    print(C.dim(header))
    print(C.dim("─" * 80))

    for mid, s, rate in rows:
        rate_str = f"{rate:.0%}"
        if rate < 0.2:
            rate_col = C.red(rate_str)
            flag = " ← prune?"
        elif rate >= 0.6:
            rate_col = C.green(rate_str)
            flag = ""
        else:
            rate_col = C.yellow(rate_str)
            flag = ""
        snippet = s["snippet"] or "(no snippet)"
        print(f"{mid:>4}  {s['injections']:>10}  {s['hits']:>4}  {rate_col:>6}  {snippet}{flag}")

    print()
    low = sum(1 for _, _, r in rows if r < 0.2)
    if low:
        print(
            f"{C.yellow(str(low))} memor{'y' if low == 1 else 'ies'} hit rate < 20% — consider reviewing or deleting them "
            f"with {C.bold('crossmem forget <id>')}."
        )
    else:
        print(C.green("All memories show healthy hit rates."))
    if unmatched:
        print(C.dim(f"{unmatched} injection(s) had no matching session — likely very recent or from a session that ended before the next response."))
