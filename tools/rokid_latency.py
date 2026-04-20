#!/usr/bin/env python3
"""
Extract per-hop Rokid glasses latency from session JSONL logs.

Usage:
    cactus/venv/bin/python tools/rokid_latency.py logs/session_XXXX.jsonl
    cactus/venv/bin/python tools/rokid_latency.py logs/       # all *.jsonl under logs/

The Rokid bridge already emits a `rokid_trace` event at the end of every turn
(see src/rokid_bridge.py:RokidTurnTrace.summary). This script reads those events
and prints:

  - A per-turn table with each hop's latency (mic → STT → Gemma → TTS → audio)
  - Aggregate p50/p90 for every hop
  - The slowest turn, end-to-end, with its full breakdown

Hops that the trace measures (all in ms):

    speech_to_finalize_ms       mic start → VAD end-of-utterance detection
    stt_ms                      faster-whisper transcription
    submit_to_assistant_ms      Gemma 4 turn (incl. tool loop)
    tts_synth_ms                Kokoro TTS synthesis of the reply
    assistant_to_audio_enqueue_ms  last tool call → first audio byte enqueued
    audio_playback_ms           synthesized audio wall-clock duration
    speech_to_audio_enqueue_ms  end-to-end: user stops talking → audio starts
    speech_to_audio_finish_ms   end-to-end: user stops talking → audio ends
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

HOPS = [
    "speech_to_finalize_ms",
    "stt_ms",
    "submit_to_assistant_ms",
    "tts_synth_ms",
    "assistant_to_audio_enqueue_ms",
    "audio_playback_ms",
    "speech_to_audio_enqueue_ms",
    "speech_to_audio_finish_ms",
]


def iter_traces(path: Path):
    files = [path] if path.is_file() else sorted(path.glob("**/*.jsonl"))
    for f in files:
        with f.open() as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    evt = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if evt.get("event") == "rokid_trace":
                    yield f.name, evt


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    root = Path(argv[1])
    if not root.exists():
        print(f"No such path: {root}")
        return 1

    traces = list(iter_traces(root))
    if not traces:
        print("No rokid_trace events found. Either no Rokid sessions have run, "
              "or the logs are in a different place. Default: logs/")
        return 0

    print(f"Found {len(traces)} Rokid turn trace(s) across {len(set(f for f,_ in traces))} file(s).\n")

    # Per-turn table
    print(f"{'turn_id':16} {'outcome':10} " + " ".join(f"{h[:22]:>22}" for h in HOPS))
    print("-" * (16 + 1 + 10 + 1 + 23 * len(HOPS)))
    rows = []
    for _, evt in traces:
        turn_id = (evt.get("turn_id") or "?")[-14:]
        outcome = (evt.get("outcome") or "?")[:10]
        cells = []
        for h in HOPS:
            v = evt.get(h)
            cells.append(f"{v:>22.1f}" if isinstance(v, (int, float)) else f"{'—':>22}")
        print(f"{turn_id:16} {outcome:10} " + " ".join(cells))
        rows.append(evt)

    # Aggregate p50/p90 per hop
    print("\nPer-hop latency distribution (ms):")
    print(f"  {'hop':30} {'n':>4} {'p50':>8} {'p90':>8} {'min':>8} {'max':>8}")
    for h in HOPS:
        values = [r[h] for r in rows if isinstance(r.get(h), (int, float))]
        if not values:
            print(f"  {h:30} {'0':>4}  (no data)")
            continue
        p50 = statistics.median(values)
        p90 = statistics.quantiles(values, n=10)[-1] if len(values) >= 2 else values[0]
        print(f"  {h:30} {len(values):>4} {p50:>8.1f} {p90:>8.1f} {min(values):>8.1f} {max(values):>8.1f}")

    # Slowest turn, end to end
    e2e = [r for r in rows if isinstance(r.get("speech_to_audio_finish_ms"), (int, float))]
    if e2e:
        worst = max(e2e, key=lambda r: r["speech_to_audio_finish_ms"])
        print(f"\nSlowest turn end-to-end: {worst.get('turn_id')} "
              f"({worst['speech_to_audio_finish_ms']:.1f} ms total)")
        print(f"  transcript: {(worst.get('transcript') or '')[:100]!r}")
        print(f"  reply:      {(worst.get('assistant_text') or '')[:100]!r}")
        for h in HOPS:
            v = worst.get(h)
            if isinstance(v, (int, float)):
                print(f"    {h:30} {v:>8.1f} ms")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
