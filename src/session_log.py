"""
Structured event log for HVAC Copilot sessions.

One JSONL file per server run at `logs/session_<unix_ts>_<pid>.jsonl`.
Each event is one line: {"ts": <epoch_s>, "kind": "...", ...fields}.

Public API:
    log_event(kind, **fields)   — append one event
    recent_events(n)            — tail the current file
    summary()                   — aggregate stats on the current file
    log_file_path()             — for the download endpoint
    log_file_name()             — for content-disposition

This is sync + line-buffered on purpose. File writes are microseconds;
an async queue would add latency without buying anything at session scale.
"""

from __future__ import annotations

import json
import logging
import os
import statistics
import time
from collections import Counter
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parent.parent
_LOG_DIR = _REPO_ROOT / "logs"
_LOG_DIR.mkdir(exist_ok=True)

_START_TS = int(time.time())
_LOG_PATH = _LOG_DIR / f"session_{_START_TS}_{os.getpid()}.jsonl"
_fp = _LOG_PATH.open("a", buffering=1, encoding="utf-8")  # line-buffered for live tail

logger.info(f"Session log: {_LOG_PATH}")


def log_event(kind: str, **fields: Any) -> None:
    """Append a single event. Never raises — logging must not break the server."""
    try:
        evt = {"ts": time.time(), "kind": kind, **fields}
        _fp.write(json.dumps(evt, default=str) + "\n")
    except Exception as e:
        logger.warning(f"log_event({kind}) failed: {e}")


def log_file_path() -> Path:
    return _LOG_PATH


def log_file_name() -> str:
    return _LOG_PATH.name


def _read_all_events() -> list[dict]:
    try:
        _fp.flush()
    except Exception:
        pass
    out: list[dict] = []
    try:
        with _LOG_PATH.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except FileNotFoundError:
        return []
    return out


def recent_events(n: int = 100) -> list[dict]:
    events = _read_all_events()
    if n <= 0:
        return events
    return events[-n:]


def summary() -> dict[str, Any]:
    """Aggregate stats computed from the current log file."""
    events = _read_all_events()
    turn_ends = [e for e in events if e.get("kind") == "turn_end"]
    completes = [e for e in events if e.get("kind") == "complete_end"]
    errors = [e for e in events if e.get("kind") == "turn_error"]
    tool_calls = [e for e in events if e.get("kind") == "tool_call"]
    rokid_traces = [e for e in events if e.get("kind") == "rokid_trace"]

    def _pct(values: list[float], p: float) -> float | None:
        if not values:
            return None
        values = sorted(values)
        k = max(0, min(len(values) - 1, int(round((p / 100) * (len(values) - 1)))))
        return round(values[k], 1)

    ttfts = [c["ttft_ms"] for c in completes if isinstance(c.get("ttft_ms"), (int, float))]
    decodes = [c["decode_tps"] for c in completes if isinstance(c.get("decode_tps"), (int, float))]
    prefill_toks = [c["prefill_tokens"] for c in completes if isinstance(c.get("prefill_tokens"), (int, float))]
    totals = [t["total_ms"] for t in turn_ends if isinstance(t.get("total_ms"), (int, float))]

    return {
        "log_file": str(_LOG_PATH),
        "event_count": len(events),
        "turn_count": len(turn_ends),
        "error_count": len(errors),
        "tool_call_count": len(tool_calls),
        "rokid_trace_count": len(rokid_traces),
        "tool_histogram": dict(Counter(t.get("name") for t in tool_calls if t.get("name"))),
        "ttft_ms": {
            "avg": round(statistics.mean(ttfts), 1) if ttfts else None,
            "p50": _pct(ttfts, 50),
            "p90": _pct(ttfts, 90),
            "p95": _pct(ttfts, 95),
            "min": round(min(ttfts), 1) if ttfts else None,
            "max": round(max(ttfts), 1) if ttfts else None,
        },
        "decode_tps_avg": round(statistics.mean(decodes), 2) if decodes else None,
        "prefill_tokens_median": statistics.median(prefill_toks) if prefill_toks else None,
        "turn_total_ms_avg": round(statistics.mean(totals), 1) if totals else None,
        "recent_rokid_traces": rokid_traces[-5:],
    }
