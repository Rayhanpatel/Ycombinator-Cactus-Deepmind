"""
Live-server smoke test for the Rokid bridge endpoints.

Not picked up by pytest — file name doesn't match test_*.py — because it
requires a running `uvicorn src.main:app` on 127.0.0.1:8000.

Checks:
  GET  /api/rokid/state      → returns a JSON blob with a `connected` flag
  GET  /api/rokid/preview/latest.jpg  → returns 200 when connected, 404/503 when not

Does NOT open a WebRTC peer — that belongs in an integration test with the
Android app. The purpose here is to verify the routes wire up and the
RokidBridgeManager initialises without the Rokid app running.

Usage:
    # In one terminal:
    cactus/venv/bin/python -m uvicorn src.main:app --host 127.0.0.1 --port 8000

    # In another:
    cactus/venv/bin/python tests/smoke_rokid.py
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request


BASE = "http://127.0.0.1:8000"


def _get(path: str) -> tuple[int, bytes]:
    req = urllib.request.Request(BASE + path, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read() or b""


def main() -> int:
    failures: list[str] = []

    # 1. /api/rokid/state should always answer with a JSON payload
    status, body = _get("/api/rokid/state")
    if status != 200:
        failures.append(f"/api/rokid/state → {status}")
    else:
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as e:
            failures.append(f"/api/rokid/state returned non-JSON: {e}")
            payload = {}
        # The bridge reports connection state via `session_active` and
        # `connection_state`. Both should be present whether or not a peer
        # is currently connected.
        missing = [k for k in ("session_active", "connection_state") if k not in payload]
        if missing:
            failures.append(f"/api/rokid/state missing keys: {missing}")
        else:
            print(
                f"[state] session_active={payload['session_active']} "
                f"connection_state={payload['connection_state']} "
                f"ice={payload.get('ice_connection_state')} "
                f"speech_backend_ready={payload.get('speech_backend_ready')}"
            )

    # 2. /api/rokid/preview/latest.jpg should respond (200 with JPEG, or 404/503 when no peer)
    status, body = _get("/api/rokid/preview/latest.jpg")
    if status not in (200, 404, 503):
        failures.append(f"/api/rokid/preview/latest.jpg → unexpected {status}")
    else:
        print(f"[preview] status={status} bytes={len(body)}")

    if failures:
        print("\nFAIL:")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("\nOK — Rokid bridge endpoints wired up.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
