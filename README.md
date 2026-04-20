# HVAC Copilot

> **A senior HVAC tech in your earbuds.** Gemma 4 E4B runs 100% on-device via
> Cactus on an M4 MacBook Pro. Three clients — browser, iPhone Safari, and
> Rokid AR glasses — all share the same assistant runtime and the same 6 HVAC
> tools. On-device by default; one explicit online-escalation tool is the only
> networked path.

[![Cactus](https://img.shields.io/badge/Powered_by-Cactus-green)](https://cactuscompute.com)
[![Gemma 4 E4B](https://img.shields.io/badge/Model-Gemma_4_E4B-blue)](https://ai.google.dev/gemma)
[![YC × DeepMind](https://img.shields.io/badge/Hackathon-YC_%C3%97_DeepMind-orange)](https://events.ycombinator.com/voice-agents-hackathon26)

Built at the YC × Cactus × Google DeepMind Voice Agents Hackathon, April 19–20 2026.
Post-hackathon consolidation tag: `v1.0-consolidated`. Submission snapshot: `v0.9-hackathon-submission`.

---

## The pitch

Senior HVAC techs are retiring faster than juniors can replace them; first-time-fix
rate is the metric field service companies obsess over. HVAC Copilot puts a senior
tech on every truck: a voice + vision agent running Gemma 4 E4B on a MacBook Pro
M4 via Cactus Python. The tech describes a symptom, the model sees what the camera
sees, retrieves matching past cases from a curated 18-entry KB across 15+ brands,
coaches through the fix one step at a time, and emits a structured resolution
record at close. Zero API calls by default, zero data off device.

## Three ways to run it

Pick one — they all connect to the same Mac-side FastAPI server and speak to the
same Gemma 4 runtime via `src/assistant_runtime.py`.

### 1. Browser on Mac Chrome

```bash
# One-time setup
brew install espeak-ng                                    # Kokoro TTS backend
cactus/venv/bin/pip install -r requirements.txt

# Start the server
cactus/venv/bin/python -m uvicorn src.main:app --host 0.0.0.0 --port 8000
```

Open `http://127.0.0.1:8000/`. Browser mic (PCM16 LE) + 1 fps camera keyframes
over WebSocket. Browser-native Web Speech API for TTS.

### 2. iPhone Safari over LAN

Same server, but Safari needs HTTPS to grant mic/camera over the network. Use
`mkcert` for LAN certs, then:

```bash
mkcert <MAC_LAN_IP>                                       # generates *-key.pem + *.pem
cactus/venv/bin/python -m uvicorn src.main:app \
  --host 0.0.0.0 --port 8443 \
  --ssl-keyfile  ./<MAC_LAN_IP>+2-key.pem \
  --ssl-certfile ./<MAC_LAN_IP>+2.pem
```

On the iPhone: join the same Wi-Fi (or the Mac's Personal Hotspot), open
`https://<MAC_LAN_IP>:8443/`, tap through the cert trust prompt once. The UI
reflows for mobile (stacked composer, safe-area insets for the notch).

Full walk-through in [HANDOFF.md §1](HANDOFF.md).

### 3. Rokid AR glasses

The Kotlin Android app under [rokid/](rokid/) opens a WebRTC peer to
`POST /session` on the Mac and streams camera + mic bidirectionally. The Mac
runs Silero VAD + faster-whisper STT + Kokoro TTS and speaks replies back
through the glasses.

```bash
# Tell the glasses where the Mac is
echo "BRIDGE_SESSION_URL=http://<MAC_LAN_IP>:8000/session" > rokid/local.properties

# Build + install
cd rokid && ./gradlew :app:assembleDebug
# (install the resulting APK on the glasses via Android Studio or adb)
```

With the Rokid app in the foreground, the browser UI (if open) shows Rokid
connection state, a live MJPEG preview, speech-debug metrics, and the last
heard/replied text. Full setup + tuning notes in [rokid.md](rokid.md).

## The 6 HVAC tools

Each tool's schema lives in [shared/hvac_tools.json](shared/hvac_tools.json) and
is dispatched by [src/tools.py](src/tools.py). Five run 100% on-device; one is
an explicit, UI-visible online escalation:

- **`query_kb(query, equipment_model?)`** — keyword-scored search over the 18
  curated KB entries.
- **`log_finding(location, issue, severity, part_number?, notes?)`** — records
  a diagnosed problem.
- **`flag_safety(hazard, immediate_action, level)`** — `level=stop` halts the
  session and fires the red banner.
- **`flag_scope_change(original_scope, new_scope, reason, estimated_extra_time_minutes?)`**.
- **`close_job(summary, parts_used, follow_up_required, follow_up_notes?)`** —
  emits the structured resolution record.
- **`search_online_hvac(query)` 🌐** — escalation ONLY. Queries r/HVAC +
  r/hvacadvice + r/Refrigeration via [src/online_search.py](src/online_search.py)
  (PRAW with credentials, anonymous JSON fallback otherwise). Every call surfaces
  an amber 🌐 card in the tool-activity panel and a banner explaining that the
  query went to reddit.com. The system prompt forbids auto-chaining from
  `query_kb`.

## Architecture

```text
Browser (Chrome / iPhone Safari)
───────────────────────────────
[mic PCM16 LE]──┐
[camera 1fps]   ├── WebSocket ── /ws/session ──┐
[text input]────┘                              │
                                               │    Mac M4 Pro (FastAPI + Cactus)
                                               │    ─────────────────────────────
Rokid AR glasses                               ├──→ src/assistant_runtime.py
────────────────                               │       ├─→ Gemma 4 E4B (via src/cactus)
[H.264 video]──┐                               │       ├─→ HVACToolDispatcher
[audio RTP]    ├── WebRTC ─── POST /session ───┤       │     ├─ query_kb (kb/*.json)
[data channel] ┘   aiortc SDP                  │       │     ├─ log_finding
                                               │       │     ├─ flag_safety
                                               │       │     ├─ flag_scope_change
                                               │       │     ├─ close_job
                                               │       │     └─ search_online_hvac 🌐
                                               │       │
                                               │       └─→ src/speech_io.py  (Rokid path only)
                                               │            ├─ Silero VAD
                                               │            ├─ faster-whisper STT
                                               │            └─ Kokoro TTS
                                               │
[tokens + tool_call events + rokid_state] ←────┘
```

One shared Cactus handle; per-session `FindingsStore` + conversation history;
3-pass tool-call loop so chained calls land in a single turn. The browser path
uses Web Speech API for TTS; the Rokid path uses on-device Kokoro.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full set of Mermaid
diagrams.

## Where iOS is

Retired for now. Two retired artefacts are preserved in-tree as reference:

- [archive/ios-abandoned/](archive/ios-abandoned/) — the Cactus wiring spike
  (`CactusModel` actor, tool dispatcher, KB store, findings store).
- [archive/ios-ui-swiftui-spike/](archive/ios-ui-swiftui-spike/) — teammate
  tash-2s's SwiftUI component library (11 components + screens + theme).

The native iOS path is blocked on Cactus's Apple SDK (XCFramework / SPM)
stabilising. Once it does, the thin-client swap is: take the SwiftUI views,
drop in the Cactus actor, replace the WebSocket with a direct Cactus call.

## Measured performance

On MacBook Pro M4 Pro (CPU, no ANE — Cactus hasn't published an ANE-compiled
`model.mlpackage` for Gemma 4 E4B yet):

| Metric | Value (from session logs) |
| --- | --- |
| Model load | ~4–6 s (one-time at server start) |
| TTFT — bare model, no tools | ~217 ms |
| TTFT — full HVAC system (tools + prompt + history) | ~3.9–4.5 s |
| Decode speed | ~17 tok/s |
| Prefill tokens per turn (text, no image) | ~935 |
| Prefill tokens per turn (with 448 px keyframe) | ~1400 |
| KB retrieval over 18 entries | <1 ms |
| `tests/smoke_hvac.py` 8-case benchmark | 7/8 tool-match, 7/8 arg-match |

The bare-model 217 ms baseline is what Cactus reports when only a short system
prompt + user message are prefilled. In the HVAC app we pay the cost of 6 tool
schemas + a rules-heavy system prompt + accumulated turn history, which is what
drags TTFT to ~4 s.

### Rokid end-to-end latency

The Rokid bridge instruments every turn and emits a `rokid_trace` event at
finish — see `src/rokid_bridge.py:RokidTurnTrace.summary`. Each trace breaks
the turn into hops:

| Hop | What it measures |
| --- | --- |
| `speech_to_finalize_ms` | mic start → Silero VAD end-of-utterance |
| `stt_ms` | faster-whisper transcription |
| `submit_to_assistant_ms` | Gemma 4 turn (incl. tool-loop passes) |
| `tts_synth_ms` | Kokoro TTS synthesis |
| `assistant_to_audio_enqueue_ms` | last token → first audio byte enqueued |
| `audio_playback_ms` | synthesized audio wall-clock duration |
| `speech_to_audio_enqueue_ms` | **perceived latency**: user stops talking → audio starts |
| `speech_to_audio_finish_ms` | user stops talking → audio ends |

Live per-turn data: `GET /api/rokid/state` → `last_latency_trace`.
Aggregate over a session: `python tools/rokid_latency.py logs/session_*.jsonl`.

Numbers will be populated here once enough real turns have been recorded.

## Tests

```bash
cactus/venv/bin/python -m pytest tests/ -q                     # full suite
cactus/venv/bin/python tests/smoke_ws.py "Carrier 58STA intermittent cooling clicking"   # live WS
cactus/venv/bin/python tests/smoke_rokid.py                    # Rokid state endpoint
```

## Docs

- [README.md](README.md) — this file.
- [HANDOFF.md](HANDOFF.md) — engineering handoff, live path details, landmines.
- [rokid.md](rokid.md) — Rokid-specific setup, speech tuning, troubleshooting.
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — Mermaid diagrams + tech stack.
- [docs/idea.md](docs/idea.md) — product vision.
- [archive/voice-sight-spike/](archive/voice-sight-spike/) — retired multimodal backend spike.
- [archive/ios-ui-swiftui-spike/](archive/ios-ui-swiftui-spike/) — retired iOS SwiftUI scaffold.
- [archive/ios-abandoned/](archive/ios-abandoned/) — retired iOS Cactus wiring scaffold.

## License

MIT — see [LICENSE](LICENSE).
