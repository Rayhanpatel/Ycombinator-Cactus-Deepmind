# HVAC Copilot — Hackathon Build Plan

**Hackathon:** YC × Cactus × Google DeepMind — Voice Agents on Gemma 4
**Team:** 3 people
**Repo:** https://github.com/Rayhanpatel/Ycombinator-Cactus-Deepmind
**Date compiled:** 2026-04-18

---

## 1. The pitch in one paragraph

Senior HVAC techs are retiring faster than juniors can replace them. We put a senior tech in your earbuds. A field worker points their iPhone camera at a failing unit, speaks the symptom, and Gemma 4 — running fully on-device via Cactus — coaches them through the fix. It sees the unit, hears the symptom, retrieves matching past cases from a knowledge base, and generates a structured resolution record at the end. Every fix makes the next one better. 100% on-device, no cloud, no data leaves the phone.

**Demo flow (90s):** tech points phone at a mock HVAC unit → says "I'm seeing intermittent cooling on a Carrier 58STA with a clicking sound before shutoff" → Gemma 4 responds in voice with the top hypothesis (failed run capacitor), retrieves a matching past case, walks through the fix stepwise, then structures the tech's spoken closing notes into a resolution JSON.

---

## 2. Why this wins the hackathon

**Judging criteria = relevance/realness (50%) + MVP quality (50%)**

| Criterion | How we score |
|---|---|
| Real problem | $50B HVAC service market. Labor shortage is real. First-time-fix rate is a metric field service companies obsess over. |
| Enterprise appeal | Clear B2B SaaS. Per-seat pricing. Privacy story (audio+video never leaves device) sells to regulated verticals. |
| Uses Gemma 4 | Native voice + vision + tool calling in one forward pass. This is the ONE thing Gemma 4 can do that FunctionGemma 270M (which every previous hackathon winner used) could not. |
| Voice-first | Core interaction is voice. Not a bolted-on feature. |

**Our unfair advantage vs the 7 past hackathon projects we analyzed** (FatBoss, Mingle, TrailSense, Warriors PA, CactusRoute, CloudNein, Cactus Commander): they all ran text-only FunctionGemma 270M with a `on-device → confidence gate → Gemini cloud` pattern. We are shipping **native multimodal in one model** — no Whisper pipeline, no separate vision encoder, no cloud fallback needed for the core loop.

---

## 3. Current state

What is already done and committed:

- Cactus SDK cloned and built locally (`cactus/`, Python bindings compiled to `libcactus.dylib`)
- Authenticated with Cactus CLI (live key in `.env`)
- Gemma 4 E4B downloaded (~6.44 GB) — INT4 Apple-optimized weights
- `test_gemma4.py` runs end-to-end on M4 Pro CPU:
  - Model load: 6.7 s
  - Time to first token: 217 ms
  - Decode speed: 28 tok/s
  - Confidence: 0.97
- Python scaffold committed: `src/agent.py`, `src/cactus_engine.py`, `src/cloud_fallback.py`, `src/voice_handler.py`, `src/tools.py`, `src/config.py`

What we explicitly skipped:
- **NPU mlpackage generation** (would need HF token + `--reconvert`, 30+ min, not worth it — CPU perf is already great)
- **`cactus build --apple` local build** (XCFramework step failed even with full Xcode). We bypass this via Swift Package Manager.

---

## 4. Product scope — what we ARE building

A single-screen worker app: "On-Site mode" from the field-service concept in `idea.md`.

**Tech points phone, speaks, gets coached, closes the job.** That's it.

| Feature | In MVP? |
|---|---|
| Voice input (mic) | Yes |
| Camera input (keyframe per second) | Yes |
| Streaming voice/text response | Yes |
| 5 HVAC-specific tools | Yes |
| Hand-authored KB (10 Carrier/Trane/Lennox cases) | Yes |
| Semantic KB retrieval | Yes |
| Structured resolution record (SQLite + JSON export) | Yes |
| Pre-baked demo scenarios (3) | Yes |
| Safety classifier (Gemma 4 does it, same forward pass) | Yes |
| **Customer-side app** | **NO** — tell the story verbally in the pitch |
| **Dispatch / marketplace / auth / payments / maps** | **NO** |
| **Cloud fallback** | **Optional**, off by default for "100% on-device" demo narrative |

---

## 5. Platform decision — iOS-first with a 2-hour go/no-go gate

**Target: native iOS app in Swift + SwiftUI on iPhone 16 Pro, via Cactus Swift Package Manager.**

### Why iOS is viable (we verified against current Cactus docs)

- Swift is the officially recommended SDK for production iOS voice agents on Cactus
- Swift Package Manager distribution works: `.package(url: "https://github.com/cactus-compute/cactus", from: "1.0.0")` — we do NOT need to run `cactus build --apple` locally (which failed for us)
- Apple NPU/ANE acceleration shipped in Jan 2026 — **5-11× faster than CPU** on iPhone/Mac
- Gemma 4 has day-one Cactus support; 0.3s from end of 30s voice clip to first token
- Multimodal + tools work in Swift: same `"images": [...]`, `"audio": [...]` message format, `cactusPrefill()` / `cactusComplete()` accept tool JSON
- Minimum: iOS 13.0+, Xcode 14.0+, Swift 5.7+
- iPhone 16 Pro has 8GB RAM — enough headroom for Gemma 4 E4B (~4.5 GB)

### Honest risks

- Swift SDK docs are thinner than Python's
- No official example iOS app in the repo — we read `Cactus.swift` directly
- No one on the team has confirmed SwiftUI experience
- 6 GB weight download on first launch needs a progress screen

### The go/no-go gate

**Hour 0–2 — Person 1 runs the Swift spike solo:**
1. New Xcode project, SwiftUI, iOS 17 target
2. Add Cactus via SPM
3. Download Gemma 4 E4B weights (or bundle in for hackathon — 6 GB is fine as app assets for a demo)
4. One screen: button → load model → text prompt → show response

**Decision at T+2h:**
- If it runs on the iPhone 16 Pro → commit to native iOS, Persons 2 and 3 continue as below
- If it doesn't → pivot immediately to web fallback (Vite+React in Safari on iPhone 16 Pro, backend on Mac via LAN WebSocket). Work done by Persons 2 and 3 is platform-agnostic and ports cleanly.

Persons 2 and 3 build in parallel during the spike. Their work does not depend on the platform choice.

---

## 6. Architecture

### Target: native iOS

```
┌─────────────────────────────────────────────────────────────┐
│  iPhone 16 Pro  (SwiftUI + Cactus via SPM)                  │
│                                                             │
│   ┌────────────┐  ┌────────────┐  ┌─────────────────────┐  │
│   │ AVFoundation│  │ AVCaptureSession│  HUD:             │  │
│   │ mic 16kHz  │  │ camera 1 fps   │  • transcript       │  │
│   │ PCM buffers│  │ JPEG keyframes │  • hypothesis card  │  │
│   └──────┬─────┘  └─────┬──────────┘  • findings list    │  │
│          │              │             • safety banner    │  │
│          ▼              ▼             • Close Job panel  │  │
│    /tmp/utt_N.wav   /tmp/frame_N.jpg                     │  │
│          │              │                                │  │
│          └──────┬───────┘                                │  │
│                 ▼                                        │  │
│   CactusModel.complete(                                  │  │
│     messages: [{role, content, images, audio}],          │  │
│     tools: HVAC_TOOLS,                                   │  │
│     onToken: stream to UI                                │  │
│   )                                                      │  │
│                 │                                        │  │
│                 ▼                                        │  │
│         Gemma 4 E4B on ANE (NPU)                         │  │
│                 │                                        │  │
│                 ▼                                        │  │
│   Response { text, function_calls[], confidence }        │  │
│                 │                                        │  │
│                 ▼                                        │  │
│   ToolDispatcher                                         │  │
│      ├─ query_kb       → embedded JSON KB               │  │
│      ├─ log_finding    → Core Data / SQLite             │  │
│      ├─ flag_safety    → hard-interrupt UI              │  │
│      ├─ flag_scope_change                               │  │
│      └─ close_job      → structured JSON export         │  │
└─────────────────────────────────────────────────────────────┘
```

### Fallback: web + Mac backend (if Swift spike fails at T+2h)

```
┌────────────────────────────────┐        ┌─────────────────────────────┐
│  iPhone 16 Pro — Safari        │  LAN   │  Mac M4 Pro                 │
│  Vite + React PWA              │ ◀────▶ │  FastAPI + Cactus Python    │
│  getUserMedia (mic + camera)   │   WS   │  Gemma 4 E4B (CPU 28 tok/s) │
│  WebSocket client              │        │  Same tool dispatcher       │
└────────────────────────────────┘        └─────────────────────────────┘
```

Demo narrative stays clean: "today the model runs on the Mac for demo speed; Cactus ships the same Gemma 4 as an iOS XCFramework, so this moves to the device at production."

---

## 7. Work split — 3 people, parallel tracks

### Person 1 — "The Brain"
**Swift spike + model integration.** If iOS works, owns the CactusModel wrapper, session manager, streaming callbacks, tool-call dispatch. If iOS fails, owns FastAPI backend instead.

- **Hour 0–2 (solo):** Swift spike. Go/no-go decision at T+2h.
- **Hour 2–4:** Wire camera + mic buffers into `CactusModel.complete`. Stream tokens to UI. Parse `function_calls` and dispatch.
- **Hour 4–6:** Tool-result round trips. Session state (running findings list). Safety interrupt path.
- **Hour 6–8:** Integration with P2 and P3. Latency profiling. Graceful errors.
- **Stack:** Swift, SwiftUI, Cactus SPM. Fallback: Python 3.12, FastAPI, websockets.
- **Fallback if blocked:** strip to text-only demo (mic only, no camera, or camera only, no mic). Either alone still demos the unfair advantage.

### Person 2 — "The Face"
**UI + media capture.**

- **Hour 0–2:** Scaffold SwiftUI screens — `OnSiteView`, `HUDOverlay`, `FindingsList`, `CloseJobView`. Mock data everywhere. Static, no model yet.
- **Hour 2–4:** Wire `AVCaptureSession` (camera, 1 fps keyframe to JPEG), `AVAudioEngine` (mic, 16kHz PCM, VAD chunking to WAV). Write to `/tmp/`.
- **Hour 4–6:** Hook up to P1's CactusModel wrapper. Render streaming tokens as transcript. Render tool calls as HUD updates.
- **Hour 6–8:** Polish — waveform, camera preview overlay, transitions, tap-to-talk button, Close Job dictation sheet.
- **Stack:** SwiftUI, AVFoundation, Combine. Fallback: Vite + React, `getUserMedia`, WebSocket client.
- **Fallback if blocked:** simple stacked divs, no animations, no waveform. Functional > pretty.

### Person 3 — "The Domain"
**Tools + KB + demo scripts.** Can run entirely without the model.

- **Hour 0–2:** Write `HVAC_TOOLS` JSON schemas (5 tools, see section 9). Author first 3 KB entries (Carrier 58STA capacitor, Trane XR14 contactor, Lennox furnace ignitor) in JSON.
- **Hour 2–4:** Implement all 5 tool handlers with mock inputs. Write 7 more KB entries for 10 total. Compute MiniLM embeddings offline, bake into JSON.
- **Hour 4–6:** `query_kb` with cosine similarity. `log_finding` → SQLite. `close_job` → structured JSON export to Files / Downloads.
- **Hour 6–8:** Write 3 pre-baked demo scripts (section 10). Dry-run each 5× with real tech phrasing. Build a failure recovery cheat sheet (what to say if model gets confused mid-demo).
- **Stack:** Swift (Codable structs, SQLite.swift) or Python (sqlite3, sentence-transformers). Does not matter — tool logic is pure data.
- **Fallback if blocked:** 3 KB entries instead of 10. One demo scenario instead of 3.

### Integration gates — hard deadlines

| Time | Gate | If missed |
|---|---|---|
| **T+2h** | Swift spike decision | Pivot to web immediately |
| **T+4h** | Text-only end-to-end: type a prompt → model → tool call → tool result → render | All three stop and debug together |
| **T+6h** | Audio OR vision working in a real `cactusComplete` call | Ship with whichever works |
| **T+8h** | Full scenario recorded as backup video | Live demo becomes optional |

---

## 8. Contracts — freeze these first (15 min, together)

One file: `Schemas.swift` (or `src/schemas.py`). Everyone works from this.

### 8.1 Session state

```swift
struct SessionState: Codable {
    var messages: [Message]          // conversation so far
    var findings: [Finding]          // things logged this session
    var currentHypothesis: Hypothesis? // top-ranked KB match
    var safetyLevel: SafetyLevel      // green | yellow | red
    var isListening: Bool
}

struct Message: Codable {
    let role: String                 // "user" | "assistant" | "tool"
    let content: String
    let images: [String]?            // file paths
    let audio: [String]?             // file paths
}
```

### 8.2 Tool schemas (OpenAI format, 5 tools total)

```json
[
  {"type":"function","function":{"name":"query_kb","description":"Search past HVAC cases by symptom","parameters":{"type":"object","properties":{"system_brand":{"type":"string"},"system_model":{"type":"string"},"symptoms":{"type":"array","items":{"type":"string"}}},"required":["symptoms"]}}},
  {"type":"function","function":{"name":"log_finding","description":"Log an observation about the unit","parameters":{"type":"object","properties":{"location":{"type":"string"},"issue":{"type":"string"},"severity":{"type":"string","enum":["low","medium","high","critical"]},"dimensions":{"type":"string"}},"required":["location","issue","severity"]}}},
  {"type":"function","function":{"name":"flag_safety","description":"Flag a safety hazard — hard stops coaching","parameters":{"type":"object","properties":{"hazard_type":{"type":"string","enum":["electrical","gas","fire","co","flooding","other"]},"severity":{"type":"string","enum":["medium","high"]},"description":{"type":"string"}},"required":["hazard_type","severity"]}}},
  {"type":"function","function":{"name":"flag_scope_change","description":"Flag additional work beyond the original ticket","parameters":{"type":"object","properties":{"description":{"type":"string"},"additional_parts":{"type":"array","items":{"type":"string"}},"additional_time_minutes":{"type":"integer"}},"required":["description"]}}},
  {"type":"function","function":{"name":"close_job","description":"Generate a structured resolution record","parameters":{"type":"object","properties":{"diagnosis":{"type":"string"},"fix_applied":{"type":"string"},"parts_used":{"type":"array","items":{"type":"object","properties":{"name":{"type":"string"},"quantity":{"type":"integer"}}}},"time_on_site_minutes":{"type":"integer"},"first_time_fix":{"type":"boolean"}},"required":["diagnosis","fix_applied","parts_used","time_on_site_minutes"]}}}
]
```

### 8.3 KB entry schema

```json
{
  "entry_id": "carrier_58sta_capacitor_001",
  "system": {"type": "HVAC split system", "brand": "Carrier", "model_family": "58STA", "specific_models": ["58STA090", "58STA120"]},
  "symptoms": [
    {"description": "intermittent cooling loss", "keywords": ["intermittent", "cooling", "warm air"]},
    {"description": "clicking sound before shutoff", "keywords": ["clicking", "click", "tick"]}
  ],
  "symptoms_embedding": [/* 384-dim MiniLM-L6-v2 */],
  "diagnosis": "Failed run capacitor",
  "probability_prior": 0.55,
  "tests_to_confirm": ["Measure capacitance with meter (expect 45 uF ± 6%)", "Visual inspection for bulging or leaking"],
  "fix": {
    "description": "Replace run capacitor",
    "parts": [{"name": "Run capacitor", "spec": "45 uF, 370V", "quantity": 1}],
    "steps": [
      "Kill power at disconnect",
      "Remove service panel",
      "Discharge old capacitor with insulated screwdriver",
      "Photograph wire positions before disconnect",
      "Swap capacitor matching wire positions",
      "Restore panel and power",
      "Verify cooling at supply vent (should read 15-20°F below return temp)"
    ],
    "typical_time_minutes": 25
  },
  "safety_notes": ["Capacitors hold charge — discharge before handling", "Verify power is off with meter, not just breaker"]
}
```

---

## 9. Knowledge base — contents

10 hand-authored entries covering realistic HVAC scenarios. Source material: manufacturer service manuals, HVAC-Talk forum threads, Reddit r/HVAC. One author pass, one tech review pass if we can pull a friend with field experience.

| # | System | Symptom cluster | Likely cause |
|---|---|---|---|
| 1 | Carrier 58STA | Intermittent cooling + clicking before shutdown | Failed run capacitor |
| 2 | Trane XR14 | Unit won't start, humming from contactor | Pitted/stuck contactor |
| 3 | Lennox ML180 (furnace) | No heat, glowing igniter, no flame | Bad flame sensor or ignitor |
| 4 | Goodman GSX14 | Cooling weak, ice on suction line | Low refrigerant (leak) |
| 5 | Rheem RA14 | Breaker trips on startup | Failed compressor or shorted wiring |
| 6 | York YCD | Water pooling in furnace area | Clogged condensate drain |
| 7 | American Standard Silver 14 | Fan runs, compressor doesn't | Failed compressor start relay |
| 8 | Bryant 123A | Blower won't stop | Fan limit switch stuck closed |
| 9 | Mitsubishi mini-split | Blinking error light | Communication fault, check indoor-outdoor wiring |
| 10 | Generic gas furnace | Gas smell near unit | **SAFETY: flag_safety, evacuate, call utility** |

Entry 10 is the safety demo. When Gemma 4 retrieves it, our app fires `flag_safety` and shows the red banner.

---

## 10. Pre-baked demo scenarios — 3 total

Every winner on the prior hackathon analysis did this. We script 3 known-good flows so the live demo never depends on Gemma 4 improvising.

### Demo A — The primary pitch (90 seconds, the happy path)

1. Open app, tap "Start On-Site"
2. Point camera at mock unit (printed photo of a Carrier 58STA outdoor condenser is fine)
3. Say: *"I'm seeing intermittent cooling on a Carrier 58STA. Hear that clicking right before it shuts off? Been happening for 3 days."*
4. Model sees label + hears symptom → calls `query_kb` → retrieves entry #1 → responds in voice: *"Top hypothesis is a failed run capacitor, 45 microfarad 370 volt. Two other techs reported the same pattern on this model. Kill power at the disconnect before you open the panel."*
5. Tech says: *"Capacitor's visibly bulged."*
6. Model: *"That confirms it. Swap it, restore power, verify supply vent is 15-20 degrees below return temp."*
7. Tech (after "fix"): *"Done. Cooling at 38 at the vent, 25 minutes."*
8. Tech taps Close Job, speaks: *"Replaced run capacitor, 45 microfarad. Old one was bulged. Unit cooling normally. 25 minutes."*
9. Model calls `close_job` → structured JSON appears on screen
10. End card: "100% on-device. 0 API calls. 0 bytes of audio or video left the phone."

### Demo B — The safety save (15 seconds, optional but impressive)

1. Point camera at a mocked "furnace area" photo
2. Say: *"I'm smelling gas near this furnace."*
3. Model immediately calls `flag_safety` → red banner: "STOP. Evacuate. Call gas utility. Do not operate light switches."
4. Shows gas company number from local config
5. End card: "Safety classifier runs inside the same Gemma 4 forward pass — no separate model, no latency cost."

### Demo C — The scope change (30 seconds, shows the B2B product thinking)

1. Mid-repair, tech says: *"While I'm in here, the contactor looks pitted too. Needs replacing."*
2. Model calls `flag_scope_change` → banner: "Pro found additional work. Approve?"
3. Tech taps approve (playing both roles since no customer app)
4. Model updates the running parts list and time estimate
5. End card: "In production, this sends a push to the customer. MVP shows both sides on one screen for the demo."

**Rule: if any demo breaks live, cut to the recorded backup video. No flailing.**

---

## 11. Setup instructions for teammates

### Clone and check out

```bash
git clone https://github.com/Rayhanpatel/Ycombinator-Cactus-Deepmind.git
cd Ycombinator-Cactus-Deepmind
```

### If you are on the Swift track (iOS app)

Requirements: Mac with Xcode 15+, iPhone 16 Pro (or any iPhone with iOS 17+ and Apple Silicon), Apple Developer account (free tier fine for dev builds).

```bash
# From repo root
mkdir ios && cd ios
# Open Xcode → New Project → iOS App → SwiftUI
# In Package.swift or Xcode Package Manager, add:
#   https://github.com/cactus-compute/cactus   (from 1.0.0)
```

Gemma 4 weights for iOS: download via Cactus CLI once, then bundle into the app or download on first launch. ~4.5 GB quantized.

### If you are on the Python track (fallback backend)

```bash
export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:$PATH"   # if needed
cd cactus && source venv/bin/activate
# Model is already at cactus/weights/gemma-4-e4b-it/
cd .. && python test_gemma4.py   # verify baseline
```

Python deps for the FastAPI backend (only if we pivot to web):

```bash
pip install fastapi uvicorn websockets sentence-transformers sqlite-utils
```

### API key (already in repo `.env` — gitignored)

- Cactus live key is already authenticated via `cactus auth`
- No Gemini or OpenAI key needed for the core demo

---

## 12. What we are NOT building (and how to handle questions about it)

If a judge asks, here are the honest answers:

| Question | Answer |
|---|---|
| "Where's the customer app?" | "Next piece on the roadmap. Today we demo the worker side — that's where the value concentrates. The schemas for the customer-facing brief are defined; wiring it is a week of work." |
| "Why no dispatch?" | "Manual routing for MVP is intentional. Uber-style optimization is post-PMF. Our thesis is the on-site coaching loop, not the marketplace." |
| "Where does the knowledge base grow from?" | "Every closed ticket produces a resolution record. Those get indexed back into the KB. We show the 10-entry seed; the flywheel is the pitch." |
| "Why not fine-tune Gemma?" | "Gemma 4 with good tool calls and a retrieval layer gets us 90% of fine-tuned performance at 0% of the training cost. Fine-tune after we have 10k resolution records." |
| "What about liability — AI giving bad advice?" | "Agent suggests, tech decides. We never diagnose to the customer. Pro remains the licensed decision-maker. Same liability surface as existing field service software." |
| "Why on-device?" | "Privacy (audio + video never leaves). Latency (0.3s vs 1-3s cloud). Cost (no per-query bills). Offline (techs work in basements, rooftops, rural sites)." |

---

## 13. Risks and mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Swift SPM integration fails at T+2h | Medium | Pivot to Safari/PWA on iPhone 16 Pro. P2/P3 work ports cleanly. |
| Gemma 4 multimodal call has a bug we can't fix | Low | Fall back to text-only demo with voice input via native TTS. Still shows tool calling + KB retrieval. |
| Model hallucinates mid-demo | Medium | Use pre-baked scenarios. Have recorded backup video. |
| iPhone thermal throttling during repeated inference | Low | Demo is 2-3 minutes. Not a real concern. Keep phone cool between runs. |
| WiFi on venue is bad (for fallback web path) | Medium | Use iPhone hotspot for Mac, or ethernet tether. Or demo on Mac alone. |
| Nobody on team can write Swift | **Highest** | Pivot early. The Safari fallback is not worse for a judge — it's a phone running the app, which is what they see. |
| Demo laptop dies / phone dies | Low | Record a backup demo video at T+8h. Always have it ready. |

---

## 14. Timeline — hour by hour

```
T+0  ─────── KICKOFF ───────
     All: read this doc. Freeze Schemas file together (15 min).
     P1: start Swift spike
     P2: scaffold UI with mock data
     P3: write tool schemas + first 3 KB entries

T+2  ─────── GO / NO-GO ────
     P1: does Swift spike work on iPhone?
       YES → stay native iOS
       NO  → P1 pivots to FastAPI backend, P2 pivots to Vite+React
     P2: UI screens functional with mock data
     P3: 5 tool stubs + 3 KB entries complete

T+4  ─────── TEXT END-TO-END
     P1: typing a prompt → model → tool call → tool result renders
     P2: mic and camera capturing to disk
     P3: 10 KB entries, cosine similarity working

T+6  ─────── MULTIMODAL WORKING
     P1: audio OR vision working in a real call
     P2: streaming tokens rendering, Close Job dictation panel
     P3: 3 demo scripts written, dry-running demo A

T+8  ─────── DEMO READY
     All: record backup video of Demo A end-to-end
     All: dry-run full pitch 5x
     All: pick best take for submission

T+8+  BUFFER: polish, bug fixes, Demo B, Demo C, README cleanup
```

---

## 15. Success definition

**Must-haves** (if any fails, demo fails):
- Voice input (mic → model) works
- At least one tool call round-trips (query_kb → renders KB hit)
- `close_job` produces a visible structured JSON
- Backup video recorded by T+8h

**Should-haves**:
- Vision input (camera → model) works
- Streaming token display
- Safety demo (Demo B)
- Running on physical iPhone 16 Pro

**Nice-to-haves**:
- NPU acceleration visibly faster than CPU baseline
- Scope change demo (Demo C)
- Waveform visualization
- Polished animations

---

## 16. Key references

- Cactus Python SDK: https://docs.cactuscompute.com/latest/python/
- Cactus Apple SDK: https://docs.cactuscompute.com/latest/apple/
- Choose an SDK: https://docs.cactuscompute.com/latest/docs/choose-sdk/
- Gemma 4 on Cactus: https://docs.cactuscompute.com/latest/blog/gemma4/
- Cactus GitHub: https://github.com/cactus-compute/cactus
- Hackathon starter: https://github.com/cactus-compute/voice-agents-hack
- Internal: `Internal_docs/conversation_summary.md`, `Internal_docs/idea.md` (the over-engineered version)

---

*This is the plan. Ship it.*
