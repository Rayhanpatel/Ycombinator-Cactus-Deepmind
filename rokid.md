# Rokid HVAC Copilot

This repo now contains a complete Mac-hosted Rokid workflow:

- `rokid/` is the Android app that runs on the Rokid glasses.
- `src/main.py` is the Mac Python server.
- `web/` is the browser operator UI for transcript, tool activity, and Rokid preview.

This is the only flow described here. Older iOS or other archived experiments are out of scope for this document.

## Overview

The app turns the Rokid glasses into the field interface for HVAC Copilot.

- The glasses send live camera and microphone audio to the Mac over WebRTC.
- The Mac server performs turn detection, English transcription, Gemma/Cactus reasoning, tool calls, and text-to-speech.
- The assistant reply is spoken back through the Rokid glasses speaker.
- If the browser UI is open, it also shows the live transcript, tool activity, session state, and Rokid preview.

Current assumptions:

- The Python server runs on macOS only.
- Speech is English-only.
- The Mac is the local hub for both the web UI and the Rokid bridge endpoint.

## Architecture

### Components

- `rokid/app/src/main/java/com/example/rokidiosbridge/MainActivity.kt`
  Handles permissions, reconnects, and the wearable HUD.
- `rokid/app/src/main/java/com/example/rokidiosbridge/RokidBridgePeer.kt`
  Creates the WebRTC offer, publishes camera + mic, receives assistant audio, and handles the control data channel.
- `src/main.py`
  FastAPI entrypoint. Hosts the web UI, browser WebSocket, Rokid `/session` endpoint, and Rokid state/preview APIs.
- `src/rokid_bridge.py`
  Mac-side Rokid WebRTC bridge. Terminates the peer connection, keeps the latest preview frame, runs speech I/O, and streams synthesized audio back to the glasses.
- `src/speech_io.py`
  Speech pipeline for Rokid mode: Silero VAD, `faster-whisper`, and Kokoro.
- `src/assistant_runtime.py`
  Shared assistant session/runtime used by both browser and Rokid turns.

### Data flow

1. The Rokid app opens a WebRTC session to `POST /session` on the Mac.
2. The app sends:
   - video track from the glasses camera
   - audio track from the glasses microphone
   - control messages over the `bridge-control` data channel
3. The Mac server:
   - keeps a preview JPEG/MJPEG stream for the web UI
   - resamples audio to 16 kHz mono
   - runs Silero VAD to detect user turn boundaries
   - transcribes finalized utterances with `faster-whisper`
   - runs the existing Gemma/Cactus HVAC assistant and tool loop
   - synthesizes the reply with Kokoro
   - sends the synthesized audio back as a remote WebRTC audio track
4. The Rokid app plays the remote assistant audio and shows short status/display text in the HUD.
5. The browser UI, if open, mirrors the same transcript and session updates.

### Speech stack

For Rokid mode the Mac server uses:

- VAD: `silero-vad`
- STT: `faster-whisper` with `small.en`
- TTS: Kokoro with American English `lang_code="a"` and voice `af_heart`

The browser UI still has its original browser speech features, but the Rokid flow does not depend on them.

## Setup

### 1. Install Mac prerequisites

On the Mac that runs the Python server:

```bash
brew install espeak-ng
```

Then install Python dependencies into the same Python environment that will run the server.

This project assumes the server is started from `cactus/venv`, so install into that env explicitly:

```bash
cactus/venv/bin/pip install -r requirements.txt
```

That installs the Rokid bridge and speech dependencies, including `aiortc`, Silero VAD, `faster-whisper`, and Kokoro.

Do not rely on plain `pip install -r requirements.txt` unless `pip` already points at `cactus/venv`. If the server runs from one interpreter and the Rokid packages were installed into another, `POST /session` will fail with `503 Service Unavailable`.

Optional verification from the repo root:

```bash
cactus/venv/bin/python -c "from src.main import rokid_bridge; import json; print(json.dumps(rokid_bridge.snapshot(), indent=2))"
```

Before you connect the glasses, that output should show:

- `"available": true`
- `"speech_backend_ready": true` after startup prewarm completes, or at least no import-related dependency error

### 2. Start the Mac server

From the repo root:

```bash
cactus/venv/bin/python -m uvicorn src.main:app --host 0.0.0.0 --port 8000
```

When the server is up:

- Web UI: `http://127.0.0.1:8000/`
- Rokid session endpoint: `http://<MAC_IP>:8000/session`

The Rokid state shown in `/healthz` or the browser UI will report whether the speech backend is ready.

### 3. Configure the Rokid Android app

Create:

```text
rokid/local.properties
```

with:

```properties
BRIDGE_SESSION_URL=http://<MAC_IP>:8000/session
```

Use the Mac's LAN IP address reachable from the glasses. If you run the server on a different port, update the URL to match.

`local.properties` is intentionally ignored by git in this repo.

### 4. Build and install the Rokid app

From the repo root:

```bash
cd rokid
./gradlew :app:assembleDebug
```

Then open the `rokid/` project in Android Studio, install it on the glasses, and grant:

- camera permission
- microphone permission

### 5. Open the browser UI

Open:

```text
http://127.0.0.1:8000/
```

The UI now has a dedicated Rokid panel that shows:

- connection status
- ICE state
- control channel state
- speech state
- latest Rokid preview stream
- last transcribed user utterance
- last assistant reply

## Using the app

### On the glasses

- Launch the app.
- Keep it in the foreground.
- The app automatically tries to connect to the configured Mac bridge URL.
- Press `Enter` or the center touchpad button to force a reconnect if needed.

The HUD shows:

- backend URL
- connection state
- short status text such as listening/thinking
- compact assistant/user text
- recent logs

### On the Mac

- Start the server first.
- Open the browser UI if you want live monitoring.
- Wait for the Rokid panel to show an active session and preview.

### Conversation behavior

- The glasses microphone is always-on from the app side.
- The Mac server decides turn boundaries with VAD.
- When speech starts while the assistant is talking, the server treats it as barge-in and stops current TTS/generation before processing the new utterance.
- Assistant replies are played on the Rokid speaker.
- If the browser UI is open, it also receives the same assistant events.

## Important files

- `rokid/app/build.gradle.kts`
  Reads `BRIDGE_SESSION_URL` from `rokid/local.properties`.
- `rokid/app/src/main/AndroidManifest.xml`
  Declares camera, mic, network, and wake-lock permissions.
- `src/main.py`
  Main app server.
- `src/rokid_bridge.py`
  Rokid WebRTC bridge and audio-return path.
- `src/speech_io.py`
  Speech pipeline used for Rokid mode.
- `web/index.html`
  Browser UI layout including the Rokid panel.

## Troubleshooting

- If `POST /session` returns `503 Service Unavailable`, the usual cause is that the Python env running the server is missing Rokid dependencies such as `aiortc` or `silero-vad`. Re-run `cactus/venv/bin/pip install -r requirements.txt`, then restart the server from `cactus/venv/bin/python`.
- If the glasses connect but there is no assistant speech, verify `brew install espeak-ng` was run and check `/healthz` or the browser Rokid panel for `speech_backend_error`.
- If the HUD says the backend URL is missing, check `rokid/local.properties`.
- If the browser shows Rokid unavailable, inspect `/healthz` and the server logs for dependency errors.
- If the glasses never connect, confirm the Mac and glasses are on the same reachable network and that the configured `BRIDGE_SESSION_URL` points to the Mac's actual LAN IP.
- If you changed the server port, update both the server launch command and `BRIDGE_SESSION_URL`.
