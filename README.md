# HVAC Copilot

HVAC Copilot runs Gemma 4 E4B on a Mac via Cactus and exposes two field interfaces that share the same assistant runtime:

- A browser webapp for Mac Chrome and iPhone Safari.
- A Rokid glasses app that streams camera + mic over WebRTC to the Mac.

Both flows use the same HVAC tools and KB. Most behavior is on-device. The only networked path is the explicit `search_online_hvac` escalation tool, and the UI calls that out with a visible `🌐` banner.

## Docs

- `README.md`: setup and repo map.
- `HANDOFF.md`: latest browser/mac-webapp handoff and demo notes.
- `rokid.md`: latest Rokid workflow, tuning, and troubleshooting notes.

## Repo Map

```text
src/
├── main.py                 FastAPI entrypoint for browser + Rokid
├── assistant_runtime.py    Shared Gemma/tool-call runtime
├── rokid_bridge.py         Mac-side WebRTC bridge for Rokid
├── speech_io.py            Silero VAD + faster-whisper + Kokoro
├── tools.py                HVAC tool dispatcher
├── online_search.py        Explicit online escalation tool
├── kb_store.py             Keyword-scored KB loader/search
├── findings_store.py       Per-session findings/safety/scope state
├── session_log.py          JSONL session logging
└── config.py               Env-backed configuration

web/                        Browser UI
rokid/                      Android app for the Rokid glasses
shared/hvac_tools.json      Frozen 6-tool contract
kb/                         18 curated HVAC entries
tests/                      Unit + smoke tests
```

## Prereqs

- macOS on Apple Silicon.
- Python environment at `cactus/venv`.
- The Cactus repo cloned into `cactus/` and built for Python.
- Gemma 4 E4B weights available at `cactus/weights/gemma-4-e4b-it/`.
- `espeak-ng` installed on the Mac for Kokoro speech output:

```bash
brew install espeak-ng
```

- Optional: Android Studio / JDK 17 if you want to build the Rokid app.
- Optional: Reddit credentials for the online escalation tool. If you do not set them, the app falls back to anonymous Reddit JSON search.

## Python Setup

Most people can start with defaults. `.env` is optional unless you want to override models, speech settings, or add Reddit credentials.

```bash
cp .env.example .env
cactus/venv/bin/pip install -r requirements.txt
```

## Run The Mac Server

```bash
cactus/venv/bin/python -m uvicorn src.main:app --host 0.0.0.0 --port 8000
```

Useful endpoints once the server is up:

- Browser UI: `http://127.0.0.1:8000/`
- Health: `http://127.0.0.1:8000/healthz`
- Recent log events: `http://127.0.0.1:8000/logs/recent?n=100`
- Log summary: `http://127.0.0.1:8000/logs/summary`
- Rokid SDP endpoint: `http://<MAC_IP>:8000/session`

Quick sanity check:

```bash
curl -s http://127.0.0.1:8000/healthz
```

## Browser Flow

Open `http://127.0.0.1:8000/` in Chrome on the Mac.

- Use text input, browser speech recognition, or both.
- Enable the browser camera if you want multimodal turns.
- Tool activity, session state, safety alerts, Rokid status, and online-search banners all appear in the same UI.

For the detailed browser/iPhone demo path, LAN HTTPS notes, and current behavior assumptions, use `HANDOFF.md`.

## Rokid Flow

Create `rokid/local.properties`:

```properties
BRIDGE_SESSION_URL=http://<MAC_IP>:8000/session
```

Build the app:

```bash
cd rokid
./gradlew :app:assembleDebug
```

Then install the debug build on the glasses and grant camera + microphone permissions.

Once the Mac server is running:

- Keep the Rokid app in the foreground.
- The app will connect to the configured `BRIDGE_SESSION_URL`.
- The browser UI will show Rokid connection state, preview, speech debug, and the last heard/replied text.

For speech tuning, latency traces, and Rokid troubleshooting, use `rokid.md`.

## Online Escalation

`search_online_hvac` is preserved on this branch and is available from both browser and Rokid conversations.

- It is only for explicit “look online / check Reddit / field reports” requests or rare equipment.
- Every call is visible in the UI.
- With `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET`, the server uses the authenticated fetcher.
- Without those vars, it falls back to anonymous Reddit JSON search.

## Tests

Fastest smoke test:

```bash
cactus/venv/bin/python -m pytest tests/test_tools.py -q
```

Full Python test suite:

```bash
cactus/venv/bin/python -m pytest tests/ -q
```

Live WebSocket smoke test against a running server:

```bash
cactus/venv/bin/python tests/smoke_ws.py "Carrier 58STA intermittent cooling clicking"
```

## Key Files

- `src/main.py`: HTTP, WebSocket, and Rokid endpoints.
- `src/assistant_runtime.py`: shared turn loop, tool dispatch, and browser/Rokid event fanout.
- `src/rokid_bridge.py`: WebRTC session handling, preview stream, and assistant-audio return path.
- `src/speech_io.py`: speech segmentation, transcription, and synthesis.
- `src/online_search.py`: explicit online HVAC escalation.
- `shared/hvac_tools.json`: 6-tool schema contract.

## License

MIT
