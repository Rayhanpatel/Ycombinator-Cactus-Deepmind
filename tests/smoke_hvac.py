"""
HVAC smoke benchmark — runs 8 curated HVAC prompts against a live server
and reports which expected tool fired + TTFT + decode speed.

Run the server in another terminal first:
    cactus/venv/bin/python -m uvicorn src.main:app --host 127.0.0.1 --port 8000

Then:
    cactus/venv/bin/python tests/smoke_hvac.py

Not picked up by pytest — the file name doesn't start with `test_` — because it
requires a running server and the 8 GB model, which is not something we want
in the normal test run.
"""

import asyncio
import json
import sys
import time

import websockets


WS_URI = "ws://127.0.0.1:8000/ws/session"

# Each case: the prompt we send, the tool we EXPECT to see called, and a short
# substring we expect in that tool's arguments (loose verification, not brittle).
CASES: list[dict[str, str]] = [
    {
        "id": "carrier_capacitor",
        "prompt": "I'm seeing intermittent cooling on a Carrier 58STA. There's a clicking right before it shuts off, started 3 days ago.",
        "expected_tool": "query_kb",
        "expected_arg_substring": "Carrier",
    },
    {
        "id": "trane_contactor",
        "prompt": "Trane XR14 outdoor unit won't start, I hear humming from the contactor.",
        "expected_tool": "query_kb",
        "expected_arg_substring": "Trane",
    },
    {
        "id": "lennox_ignitor",
        "prompt": "Lennox ML180 furnace — no heat, igniter glows but no flame.",
        "expected_tool": "query_kb",
        "expected_arg_substring": "Lennox",
    },
    {
        "id": "gas_smell_safety",
        "prompt": "I'm smelling a strong rotten-egg smell near this gas furnace.",
        "expected_tool": "flag_safety",
        "expected_arg_substring": "gas",
    },
    {
        "id": "mitsubishi_minisplit",
        "prompt": "Mitsubishi mini-split, indoor unit is blinking error lights and the outdoor won't run.",
        "expected_tool": "query_kb",
        "expected_arg_substring": "Mitsubishi",
    },
    {
        "id": "goodman_refrigerant",
        "prompt": "Goodman GSX14, cooling is weak and I see ice building up on the suction line outside.",
        "expected_tool": "query_kb",
        "expected_arg_substring": "Goodman",
    },
    {
        "id": "scope_change",
        "prompt": "While I'm here swapping the capacitor, the contactor looks pitted and worn, needs replacing too, maybe 15 more minutes.",
        "expected_tool": "flag_scope_change",
        "expected_arg_substring": "contactor",
    },
    {
        "id": "close_job",
        "prompt": "Replaced the run capacitor, 45 microfarad, unit cooling at 38 degrees at the vent, 25 minutes on site. Job is done.",
        "expected_tool": "close_job",
        "expected_arg_substring": "capacitor",
    },
]


async def run_case(case: dict[str, str]) -> dict:
    prompt = case["prompt"]
    expected_tool = case["expected_tool"]
    expected_sub = case["expected_arg_substring"].lower()

    t_start = time.time()
    ttft_ms: float | None = None
    decode_tps: float | None = None
    tools_fired: list[str] = []
    tool_args_blobs: list[str] = []
    got_first_token = False

    async with websockets.connect(WS_URI) as ws:
        await ws.send(json.dumps({"type": "text", "content": prompt}))
        while True:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=90)
            except asyncio.TimeoutError:
                return {**case, "status": "timeout"}
            evt = json.loads(raw)
            kind = evt.get("type")
            if kind == "token" and not got_first_token:
                got_first_token = True
                ttft_ms = (time.time() - t_start) * 1000
            elif kind == "tool_call":
                tools_fired.append(evt.get("name", ""))
                tool_args_blobs.append(json.dumps(evt.get("arguments") or {}))
            elif kind == "assistant_end":
                decode_tps = evt.get("decode_tps")
                break
            elif kind == "error":
                return {**case, "status": f"error: {evt.get('message')}"}

    tool_match = expected_tool in tools_fired
    arg_match = any(expected_sub in b.lower() for b in tool_args_blobs)

    return {
        **case,
        "status": "ok",
        "tools_fired": tools_fired,
        "tool_match": tool_match,
        "arg_match": arg_match,
        "ttft_ms": round(ttft_ms or 0, 1),
        "decode_tps": round(decode_tps or 0, 2),
    }


async def main() -> int:
    print(f"HVAC smoke: {len(CASES)} cases against {WS_URI}\n")
    print(f"{'case':<26} {'expected':<20} {'fired':<40} {'tool':<5} {'arg':<5} {'TTFT':>7} {'tok/s':>6}")
    print("-" * 120)

    results = []
    pass_count = 0
    for c in CASES:
        r = await run_case(c)
        results.append(r)
        status = r.get("status", "?")
        if status != "ok":
            print(f"{r['id']:<26} {r['expected_tool']:<20} ({status})")
            continue
        fired = ",".join(r["tools_fired"]) or "(none)"
        tool_ok = "✓" if r["tool_match"] else "✗"
        arg_ok = "✓" if r["arg_match"] else "✗"
        print(f"{r['id']:<26} {r['expected_tool']:<20} {fired[:38]:<40} {tool_ok:<5} {arg_ok:<5} {r['ttft_ms']:>7.1f} {r['decode_tps']:>6.2f}")
        if r["tool_match"]:
            pass_count += 1

    print("-" * 120)
    total = len(CASES)
    print(f"\nTool-match: {pass_count}/{total} ({100*pass_count/total:.0f}%)")
    arg_pass = sum(1 for r in results if r.get("arg_match"))
    print(f"Arg-match:  {arg_pass}/{total} ({100*arg_pass/total:.0f}%)")
    ok = [r for r in results if r.get("status") == "ok"]
    if ok:
        avg_ttft = sum(r["ttft_ms"] for r in ok) / len(ok)
        avg_dec = sum(r["decode_tps"] for r in ok) / len(ok)
        print(f"Avg TTFT: {avg_ttft:.0f} ms  ·  Avg decode: {avg_dec:.1f} tok/s")

    return 0 if pass_count >= total * 0.75 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
