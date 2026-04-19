"""
Live-server smoke test for the HVAC Copilot WS endpoint.

Not picked up by pytest — file name doesn't match test_*.py — because it
requires a running `uvicorn src.main:app` on 127.0.0.1:8000 and a loaded
8 GB model, which is not something we want in the normal test run.

Use for demo prep: exercises one turn, prints streamed tokens, tool calls,
session state, and final timing stats.

Usage:
    # In one terminal:
    cactus/venv/bin/python -m uvicorn src.main:app --host 127.0.0.1 --port 8000

    # In another:
    cactus/venv/bin/python tests/smoke_ws.py "Carrier 58STA intermittent cooling, clicking"
    cactus/venv/bin/python tests/smoke_ws.py "I smell rotten eggs near this furnace"
"""

import asyncio
import json
import sys
import time

import websockets


async def one_turn(msg: str) -> None:
    uri = "ws://127.0.0.1:8000/ws/session"
    async with websockets.connect(uri) as ws:
        print(f">>> {msg}")
        await ws.send(json.dumps({"type": "text", "content": msg}))

        saw_first_token = False
        token_count = 0
        t_start = time.time()

        while True:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=60)
            except asyncio.TimeoutError:
                print("(timeout waiting for server)")
                return
            evt = json.loads(raw)
            kind = evt.get("type")

            if kind == "ready":
                continue
            if kind == "token":
                if not saw_first_token:
                    saw_first_token = True
                    print(f"[first token @ {time.time() - t_start:.2f}s]")
                print(evt["token"], end="", flush=True)
                token_count += 1
            elif kind == "tool_call":
                print(f"\n\n[TOOL] {evt['name']}({json.dumps(evt['arguments'])[:120]})")
                r = evt.get("result", {})
                if isinstance(r, dict):
                    if "results" in r:
                        for hit in r["results"]:
                            print(f"   ↳ {hit.get('id')} score={hit.get('score')} dx={hit.get('diagnosis','')[:80]}")
                    else:
                        print(f"   ↳ {json.dumps(r)[:200]}")
                print()
            elif kind == "session":
                st = evt["state"]
                print(
                    f"[SESSION] findings={len(st['findings'])} "
                    f"safety={len(st['safety_alerts'])} "
                    f"scope={len(st['scope_changes'])} "
                    f"stopped={st['is_stopped']}"
                )
            elif kind == "assistant_end":
                print(
                    f"\n\n[end] tokens={token_count} "
                    f"ttft={evt.get('ttft_ms')}ms "
                    f"decode={evt.get('decode_tps')}tok/s"
                )
                break
            elif kind == "error":
                print(f"\n[ERROR] {evt.get('message')}")
                break
            else:
                print(f"\n[{kind}] {evt}")


if __name__ == "__main__":
    query = sys.argv[1] if len(sys.argv) > 1 else "what is 2+2?"
    asyncio.run(one_turn(query))
