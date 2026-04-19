#!/usr/bin/env python3
"""
Analyse a HVAC Copilot session log (JSONL).

Usage:
    cactus/venv/bin/python tools/analyse_log.py logs/session_XXXX.jsonl

Prints:
  - Per-turn table (user message, tools fired, TTFT, decode tps, prefill tokens, total ms)
  - Aggregate p50/p90/p95 TTFT + decode tps + prefill tokens
  - Slowest 3 turns with their event chain
  - Pattern flags (growing TTFT, image token stacking, multi-pass turns)
"""

from __future__ import annotations

import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path


def load_events(path: Path) -> list[dict]:
    events = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return events


def group_by_turn(events: list[dict]) -> list[dict]:
    """A turn = msg_in … turn_end (or turn_error). Carry the events in between."""
    turns = []
    current = None
    for e in events:
        k = e.get("kind")
        if k == "msg_in":
            current = {"start": e, "events": [e], "tool_calls": []}
        elif current is not None:
            current["events"].append(e)
            if k == "tool_call":
                current["tool_calls"].append(e)
            if k == "turn_end":
                current["end"] = e
                current["status"] = "ok"
                turns.append(current)
                current = None
            elif k == "turn_error":
                current["end"] = e
                current["status"] = "error"
                current["error"] = e.get("error")
                turns.append(current)
                current = None
    return turns


def first_complete_end(turn: dict) -> dict | None:
    for e in turn["events"]:
        if e.get("kind") == "complete_end":
            return e
    return None


def pct(values: list[float], p: float) -> float | None:
    if not values:
        return None
    xs = sorted(values)
    k = max(0, min(len(xs) - 1, int(round((p / 100) * (len(xs) - 1)))))
    return round(xs[k], 1)


def fmt_ms(v) -> str:
    if v is None or not isinstance(v, (int, float)):
        return "-"
    return f"{v / 1000:.1f}s" if v >= 1000 else f"{v:.0f}ms"


def fmt_num(v, places=0) -> str:
    if v is None or not isinstance(v, (int, float)):
        return "-"
    return f"{v:.{places}f}"


def user_preview_from_turn(turn: dict, max_len=34) -> str:
    # The user text lives in the msg_in event's stored payload? We didn't log it
    # verbatim to keep the log light; fall back to kind + has_audio/image flags.
    s = turn["start"]
    bits = []
    if s.get("has_image"):
        bits.append("img")
    if s.get("has_audio"):
        bits.append("aud")
    if s.get("text_len"):
        bits.append(f"{s.get('text_len')}ch")
    kind = s.get("kind") or "?"
    return f"[{kind}:{'/'.join(bits) or 'empty'}]"


def print_per_turn_table(turns: list[dict]) -> None:
    hdr = f"{'#':>3} {'sid':<8} {'user':<24} {'pass':>4} {'ttft':>6} {'decode':>7} {'prefill':>8} {'tools':<30} {'total':>6}"
    print(hdr)
    print("-" * len(hdr))
    for i, t in enumerate(turns, 1):
        ce = first_complete_end(t)
        end = t.get("end") or {}
        sid = t["start"].get("sid", "-")
        tools = ",".join(tc.get("name", "?") for tc in t["tool_calls"]) or "-"
        if t["status"] == "error":
            print(f"{i:>3} {sid:<8} {user_preview_from_turn(t):<24} {'-':>4} {'-':>6} {'-':>7} {'-':>8} {'ERR':<30} {'-':>6}")
            continue
        ttft = ce.get("ttft_ms") if ce else None
        decode = ce.get("decode_tps") if ce else None
        prefill_toks = ce.get("prefill_tokens") if ce else None
        total = end.get("total_ms")
        passes = end.get("passes", "-")
        print(
            f"{i:>3} {sid:<8} {user_preview_from_turn(t):<24} {passes:>4} "
            f"{fmt_ms(ttft):>6} {fmt_num(decode, 1):>7} {fmt_num(prefill_toks, 0):>8} "
            f"{tools[:30]:<30} {fmt_ms(total):>6}"
        )


def print_aggregate(turns: list[dict]) -> None:
    ttfts = []
    decodes = []
    prefill_toks = []
    totals = []
    tool_hist = Counter()
    errors = 0
    for t in turns:
        if t["status"] == "error":
            errors += 1
            continue
        ce = first_complete_end(t)
        end = t.get("end") or {}
        if ce and isinstance(ce.get("ttft_ms"), (int, float)):
            ttfts.append(ce["ttft_ms"])
        if ce and isinstance(ce.get("decode_tps"), (int, float)):
            decodes.append(ce["decode_tps"])
        if ce and isinstance(ce.get("prefill_tokens"), (int, float)):
            prefill_toks.append(ce["prefill_tokens"])
        if isinstance(end.get("total_ms"), (int, float)):
            totals.append(end["total_ms"])
        for tc in t["tool_calls"]:
            n = (tc.get("name") or "").strip()
            if n:
                tool_hist[n] += 1

    print("\nAGGREGATE")
    print("-" * 60)
    print(f"  turns:           {len(turns)} ({errors} errors)")
    if ttfts:
        print(f"  TTFT avg:        {statistics.mean(ttfts) / 1000:.2f}s")
        print(f"  TTFT p50/p90/p95: {pct(ttfts, 50)/1000:.2f}s / {pct(ttfts, 90)/1000:.2f}s / {pct(ttfts, 95)/1000:.2f}s")
        print(f"  TTFT min/max:    {min(ttfts) / 1000:.2f}s / {max(ttfts) / 1000:.2f}s")
    if decodes:
        print(f"  decode tok/s:    avg {statistics.mean(decodes):.1f}, p50 {pct(decodes, 50)}")
    if prefill_toks:
        print(f"  prefill tokens:  median {statistics.median(prefill_toks):.0f}, max {max(prefill_toks):.0f}")
    if totals:
        print(f"  turn total_ms:   avg {statistics.mean(totals) / 1000:.2f}s, p95 {pct(totals, 95)/1000:.2f}s")
    if tool_hist:
        print(f"  tools fired:     {dict(tool_hist)}")


def print_slowest(turns: list[dict], n: int = 3) -> None:
    ok = [t for t in turns if t["status"] == "ok"]
    def total(t):
        end = t.get("end") or {}
        return end.get("total_ms") or 0
    ok.sort(key=total, reverse=True)
    if not ok:
        return
    print(f"\nSLOWEST {min(n, len(ok))} TURNS")
    print("-" * 60)
    for t in ok[:n]:
        end = t.get("end") or {}
        ce = first_complete_end(t) or {}
        print(f"  turn {end.get('turn_idx', '?')} sid={t['start'].get('sid','?')}  total={fmt_ms(end.get('total_ms'))}  "
              f"ttft={fmt_ms(ce.get('ttft_ms'))}  prefill_toks={ce.get('prefill_tokens')}  "
              f"passes={end.get('passes')}  tools={[tc.get('name') for tc in t['tool_calls']]}")


def print_flags(turns: list[dict]) -> None:
    flags = []
    ok = [t for t in turns if t["status"] == "ok"]
    # Growing TTFT (last 3 turns avg > first 3 avg by >20%)
    ttfts = []
    for t in ok:
        ce = first_complete_end(t)
        if ce and isinstance(ce.get("ttft_ms"), (int, float)):
            ttfts.append(ce["ttft_ms"])
    if len(ttfts) >= 6:
        early = statistics.mean(ttfts[:3])
        late = statistics.mean(ttfts[-3:])
        if late > early * 1.2:
            flags.append(f"TTFT growing over session: early {early/1000:.2f}s → late {late/1000:.2f}s (+{(late/early - 1)*100:.0f}%)")

    # Prefill token spike (any turn >1.5× median)
    prefill = [first_complete_end(t).get("prefill_tokens") for t in ok if first_complete_end(t) and first_complete_end(t).get("prefill_tokens")]
    if len(prefill) >= 3:
        med = statistics.median(prefill)
        spikes = [p for p in prefill if p > med * 1.5]
        if spikes:
            flags.append(f"{len(spikes)} turn(s) had prefill > 1.5× median ({med:.0f}): {spikes}")

    # Multi-pass turns
    multi = [t for t in ok if (t.get("end") or {}).get("passes", 1) >= 2]
    if multi:
        flags.append(f"{len(multi)} turn(s) took 2+ passes (tool-call follow-ups)")

    if flags:
        print("\nFLAGS")
        print("-" * 60)
        for f in flags:
            print(f"  • {f}")


def main():
    if len(sys.argv) < 2:
        # Default: most recent log in logs/
        log_dir = Path(__file__).resolve().parent.parent / "logs"
        candidates = sorted(log_dir.glob("session_*.jsonl"))
        if not candidates:
            print("No log file given and no logs/session_*.jsonl found.", file=sys.stderr)
            sys.exit(1)
        path = candidates[-1]
        print(f"(no arg given, using {path})\n")
    else:
        path = Path(sys.argv[1])

    events = load_events(path)
    turns = group_by_turn(events)

    print(f"Log file:     {path}")
    print(f"Events:       {len(events)}")
    print(f"Turns:        {len(turns)}\n")

    print_per_turn_table(turns)
    print_aggregate(turns)
    print_slowest(turns)
    print_flags(turns)


if __name__ == "__main__":
    main()
