# HVAC Copilot — Engineering Handoff

**Purpose:** full-context pickup for any engineer or AI agent continuing this branch. Zero hallucination — every claim here maps to a file, command, or commit you can verify.

---

## §1 Snapshot

- **Branch:** `mac-webapp`
- **Date written:** 2026-04-19
- **Last pushed commit:** `9885542` — `feat: 448px camera + live MovinCool demo script + honest doc numbers`
- **Local tip (pre-handoff commit):** `1a9208c` — `feat(tools): online escalation via Amogh's Reddit fetcher + ranker`
- **Uncommitted at write-time:** `shared/hvac_tools.json` + `src/main.py` — prompt-relaxation tweaks for the `search_online_hvac` tool (will be committed before push)
- **Running service:** HTTPS on `https://0.0.0.0:8443` via `uvicorn src.main:app --ssl-keyfile ./172.20.10.2+2-key.pem --ssl-certfile ./172.20.10.2+2.pem`
- **Remote demo URL (iPhone over hotspot):** `https://172.20.10.2:8443/`
- **Tests:** 65/65 pass (`cactus/venv/bin/python -m pytest tests/ -q`)
- **What works today:** browser voice + vision UI on Mac Chrome, same UI on iPhone Safari over iPhone Personal Hotspot, 6 HVAC tools, streaming token output, progressive TTS, barge-in, spacebar cancel, session log + `/logs/*` endpoints, live Reddit escalation via anonymous JSON fallback.
- **What does not work / has landmines:** see §12.

---

## §2 Product & pitch

HVAC Copilot is an on-device voice + vision coach for HVAC field technicians. It runs Google's **Gemma 4 E4B** via **Cactus Python** on a MacBook Pro M4 (CPU). The tech speaks a symptom, optionally points the camera at the unit, and the model retrieves from an 18-entry curated HVAC knowledge base, calls structured tools (`query_kb`, `log_finding`, `flag_safety`, `flag_scope_change`, `close_job`), and if needed escalates to live HVAC forum threads via a 6th tool (`search_online_hvac`). Hackathon: **YC × Cactus × Google DeepMind — Voice Agents on Gemma 4, April 2026**.

On-device pitch: everything except the one explicit online-escalation tool runs locally. The escalation tool fires only on explicit user ask or rare units, always with a 🌐 UI badge, and is the only network path. See [SUBMISSION.md](SUBMISSION.md) for judge-facing framing.

---

## §3 Repo tree (annotated)

```text
.
├── HANDOFF.md                    ← you are here
├── HANDOFF_IOS_LEGACY.md         frozen iOS pivot notes (reference)
├── README.md                     public-facing quickstart + architecture
├── SUBMISSION.md                 hackathon submission write-up
├── requirements.txt              Python deps (see §11 for what's actually installed)
├── .env.example                  secret shape (real .env is gitignored)
│
├── src/                          Python backend
│   ├── main.py                   FastAPI + WebSocket server, 826 lines — LIVE PATH
│   ├── tools.py                  HVACToolDispatcher, 6 tool handlers, 196 lines — LIVE PATH
│   ├── kb_store.py               keyword-scored KB over 18 JSON files, 139 lines — LIVE PATH
│   ├── findings_store.py         per-session in-memory state, 110 lines — LIVE PATH
│   ├── online_search.py          NEW — Reddit escalation shim, PRAW or JSON, 155 lines — LIVE PATH
│   ├── session_log.py            JSONL event logger, 125 lines — LIVE PATH
│   ├── config.py                 env var loader (cfg singleton), 77 lines — LIVE PATH
│   ├── cactus_engine.py          thin Cactus wrapper (used by CLI agent, not server) — ARCHIVAL
│   ├── agent.py                  standalone CLI loop (not on the server path) — ARCHIVAL
│   ├── voice_handler.py          mic capture for CLI (browser handles mic for server) — ARCHIVAL
│   ├── cloud_fallback.py         Gemini fallback (off by default, preserved) — ARCHIVAL
│   │
│   ├── hvac_tools.py             teammate Amogh's class-based HVACToolkit — PARALLEL STACK
│   ├── kb_engine.py              teammate's MiniLM SentenceTransformer KB — PARALLEL STACK
│   ├── db.py                     teammate's SQLite persistence — PARALLEL STACK
│   ├── embeddings.py             teammate's offline embedding builder — PARALLEL STACK
│   ├── reddit_fetcher.py         teammate's PRAW Reddit fetcher (imported by online_search.py)
│   ├── web_ranker.py             teammate's ranking pipeline — PARALLEL STACK
│   ├── progressive_search.py     teammate's tier-escalation — PARALLEL STACK
│   └── demo_runner.py            teammate's offline demo runner — PARALLEL STACK
│
├── web/                          browser client (single-page)
│   ├── index.html                81 lines — IDs consumed by app.js
│   ├── app.js                    752 lines — WS client, mic, camera, TTS, barge-in
│   └── styles.css                397 lines — dark theme, mobile CSS block @ 700px
│
├── shared/
│   ├── hvac_tools.json           frozen tool contract (6 tools) — §7
│   └── kb_schema.json            KB entry shape reference
│
├── kb/                           18 HVAC entries + 1 index (kb_index.json is ignored at load)
│   ├── american_standard_silver14_compressor_relay.json
│   ├── american_standard_silver_thermostat.json
│   ├── bryant_123a_fan_limit_switch.json
│   ├── carrier_24acc6_fan_motor.json
│   ├── carrier_58sta_capacitor.json
│   ├── generic_gas_furnace_gas_smell.json
│   ├── goodman_gsx13_refrigerant.json
│   ├── goodman_gsx14_low_refrigerant.json
│   ├── kb_index.json             (EXCLUDED from load)
│   ├── lennox_ml180_ignitor.json
│   ├── lennox_xc21_txv.json
│   ├── mitsubishi_minisplit_comm_fault.json
│   ├── movincool_climate_pro_x14.json
│   ├── rheem_ra14_breaker_trip.json
│   ├── rheem_rgph_blower.json
│   ├── trane_xr14_contactor.json
│   ├── trane_xv80_pressure_switch.json
│   ├── york_ycd_condensate_clog.json
│   └── york_ycjd_compressor.json
│
├── tests/                        65 tests total, all pass
│   ├── test_tools.py             13 tests — HVAC dispatcher
│   ├── test_reddit_fetcher.py    teammate's PRAW-level tests (mocked)
│   ├── test_web_ranker.py        teammate's ranker tests
│   ├── test_progressive_search.py  teammate's tier tests
│   ├── test_agent.py             CLI agent tests
│   ├── test_cactus_engine.py     engine wrapper tests
│   ├── smoke_ws.py               single-query WS probe (not auto-collected by pytest)
│   └── smoke_hvac.py             8-case live-server benchmark (not auto-collected)
│
├── demo/                         4 demo scripts (markdown) + backup JSONs
├── docs/                         ARCHITECTURE.md (Mermaid diagrams), idea.md (product vision)
├── archive/ios-abandoned/        retired Swift scaffold
├── cactus/                       external dep, gitignored — venv + weights live here
├── 172.20.10.2+2.pem             LAN cert (gitignored via *.pem)
├── 172.20.10.2+2-key.pem         LAN cert private key (gitignored)
└── logs/                         session JSONL files (gitignored)
```

---

## §4 System architecture

**Deep version with 8 Mermaid diagrams, tech stack, decisions: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).** Summary below.


```
┌──────────────────────────────────────────────────────────────────────────┐
│  Browser  (Chrome on Mac  OR  iOS Safari on iPhone over hotspot)         │
│                                                                          │
│  • Web Speech API         STT + TTS                (no audio over WS)   │
│  • MediaDevices.getUserMedia  mic + environment-camera @ 1 fps          │
│  • Canvas.toDataURL       448-px JPEG keyframe, base64                  │
│  • WebSocket              wss://{host}/ws/session                       │
│  • UI  transcript · tool-activity · session · safety banner ·           │
│        online banner · voice selector · camera pane                     │
└─────────────────────────────────┬────────────────────────────────────────┘
                                  │  JSON:  {type: text|multimodal|cancel|reset|ping,
                                  │          content, jpeg_b64}
                                  ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  FastAPI + uvicorn          src/main.py                                  │
│                                                                          │
│  • /healthz                 model_loaded, kb_entries                     │
│  • /logs/summary            p50/p95 TTFT, tool histogram                 │
│  • /logs/recent?n=100       tail of the JSONL                            │
│  • /logs/download           raw JSONL                                    │
│  • /ws/session              Session class — per-connection state         │
│                                                                          │
│  Session:                                                                │
│    messages[]   chat history (stripped of file refs + tool messages)    │
│    dispatcher   HVACToolDispatcher (src/tools.py)                       │
│    findings    FindingsStore (in-memory)                                │
│    cancel_flag  threaded cancel for cactus_stop()                       │
│                                                                          │
│  SYSTEM_PROMPT  ~850 tokens — 6 tool-trigger rules + anti-hallucination  │
│  GEN_OPTIONS    max_tokens=220, temperature=cfg.TEMPERATURE              │
└─────────────────────────────────┬────────────────────────────────────────┘
                                  │  cactus_complete(messages_json, options,
                                  │                  tools_json, on_token)
                                  ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  Cactus Python FFI      cactus_init / complete / stop / reset / prefill  │
│  Gemma 4 E4B weights    cactus/weights/gemma-4-e4b-it/                   │
│  Device                  CPU only (no ANE — no mlpackage for E4B yet)    │
│                                                                          │
│  Prefilled at startup:   SYSTEM_PROMPT via cactus_prefill (~7 s)         │
│  Per-turn prefill:       ~935 tokens text-only, ~1400 with image        │
│  Decode:                  ~17 tok/s                                       │
└─────────────────────────────────┬────────────────────────────────────────┘
                                  │  tokens streamed via on_token callback
                                  │  + final result contains function_calls[]
                                  ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  HVACToolDispatcher     src/tools.py                                     │
│                                                                          │
│   query_kb           → KBStore.search        (src/kb_store.py)           │
│   log_finding        → FindingsStore.add_finding                         │
│   flag_safety        → FindingsStore.add_safety  (halts session)         │
│   flag_scope_change  → FindingsStore.add_scope_change                    │
│   close_job          → FindingsStore.close_job   (emits JSON)            │
│   search_online_hvac → online_search.search   (src/online_search.py)    │
│                         ├─ PRAW path (if REDDIT_CLIENT_ID in env)       │
│                         └─ JSON fallback (anonymous, 5 s timeout)       │
└──────────────────────────────────────────────────────────────────────────┘
```

**Three-pass tool loop:** `Session.run_turn` calls `_complete_once` up to 3 times per user turn. Pass 1 gets the first completion; if it contains `function_calls`, the dispatcher runs them, their results are appended as `role: tool` messages, pass 2 runs. Loop exits as soon as a pass returns no tool calls, or cap is hit.

**Fallback parser:** Gemma 4 sometimes emits tool calls in `name(args)` form and sometimes in `<|tool_call>call: name{args}<tool_call|>` form. `src/main.py` has regex-based parsers (`_TOOL_CALL_PAREN`, `_TOOL_CALL_CURLY`) that catch both when the C-side parser misses. See `_parse_fallback_tool_calls`.

---

## §5 Runtime flow (turn-by-turn)

### A) Text-only turn
1. Browser: user types into `#text-input`, submits.
2. `app.js:sendUtterance("text")` → `ws.send({type:"text", content:"..."})`.
3. `main.py:ws_session` receives → `session.add_user_text(content)` → `session.run_turn()`.
4. `_complete_once` calls `cactus_complete` in the thread-pool executor; tokens stream via `on_token` → `session.send({type:"token", token})`.
5. Browser: `app.js` case `"token"` → `appendToAssistant(tok)` → `stripHiddenMarkers` → progressive TTS queues full sentences.
6. Cactus returns final result → if `function_calls` present, dispatcher runs them → next pass.
7. Final pass: `session.send({type:"assistant_end", text, stats})`.
8. Browser: case `"assistant_end"` → `finishAssistant` → flushes any remaining TTS.

### B) Multimodal turn (text + camera keyframe)
1. Browser: camera enabled, 1 fps loop writes `pendingFrameB64`.
2. On submit: `ws.send({type:"multimodal", content, jpeg_b64: pendingFrameB64})`.
3. Server: decodes base64, writes JPEG to `/tmp/hvac_<ts>.jpg`, adds to user message as `images: ["/tmp/hvac_<ts>.jpg"]`.
4. Same cactus_complete call path as text; Gemma 4 sees text + image in ONE forward pass.

### C) Online escalation
1. User says something like *"Look online for field reports of a Carrier 58STA short cycling"*.
2. Gemma 4 emits `search_online_hvac(query="Carrier 58STA short cycling")`.
3. Dispatcher → `online_search.search()`. Inside:
   - If `REDDIT_CLIENT_ID` + `REDDIT_CLIENT_SECRET` in env AND `praw` importable → delegates to `RedditFetcher.search()` (PRAW path).
   - Else → `requests.get` loops over `["HVAC", "hvacadvice", "Refrigeration"]` hitting `https://www.reddit.com/r/<sub>/search.json`.
4. Wrapped in `ThreadPoolExecutor` with hard 5-second wall-clock timeout.
5. Returns `{"ok": true/false, "source", "results": [{title, text, url, score, depth}, …]}`.
6. Server wraps as `tool_call` event → UI renders **amber 🌐 card** with Reddit titles + a one-time top-of-page banner *"Online search used — query sent to reddit.com"*.

---

## §6 File inventory

### Live-serving path (what uvicorn actually imports)

| File | Lines | Role |
|------|-------|------|
| `src/main.py` | 826 | FastAPI app, `Session` class, WS handler, cactus lifecycle, 3-pass tool loop, fallback parsers, HTTP endpoints. |
| `src/tools.py` | 196 | `HVACToolDispatcher` with 6 `_tool_*` handlers; loads schemas from `shared/hvac_tools.json`. |
| `src/kb_store.py` | 139 | `KBStore` — loads `kb/*.json` (excludes `kb_index.json`), keyword-scored search, dual-schema tokenizer (flat + rich), strips `embedding`/`symptoms_embedding` before returning. |
| `src/findings_store.py` | 110 | `FindingsStore` — per-session `findings[]`, `safety_alerts[]`, `scope_changes[]`, `is_stopped`, `closure`. |
| `src/online_search.py` | 155 | `search(query)` — PRAW primary, requests-based JSON fallback, ThreadPoolExecutor timeout 5 s. |
| `src/session_log.py` | 125 | `log_event(kind, **fields)` writes JSONL to `logs/session_<ts>_<pid>.jsonl`. Endpoints: `/logs/recent`, `/logs/summary`, `/logs/download`. |
| `src/config.py` | 77 | `cfg` singleton — env loader for `CACTUS_LLM_MODEL`, `MAX_TOKENS`, `TEMPERATURE`, `REDDIT_CLIENT_ID`, etc. |
| `shared/hvac_tools.json` | 166 | OpenAI-format function schemas for the 6 tools. |

### Browser

| File | Lines | Role |
|------|-------|------|
| `web/index.html` | 81 | DOM: `#status`, `#transcript`, `#composer`, `#mic-btn`, `#stop-btn`, `#cam`, `#tool-log`, `#online-banner`, `#safety-banner`, `#voice-select`. |
| `web/app.js` | 752 | WebSocket client, Web Speech API STT/TTS, barge-in, spacebar cancel, camera capture (448 px JPEG at 1 fps), progressive sentence-level TTS, hidden-marker stripping for `<|channel>thought` + `<|tool_call>`, iOS voice-list polling. |
| `web/styles.css` | 397 | dark theme, mobile CSS at `@media (max-width: 700px)`, `.tool-entry.online` amber card, `.online-banner`. |

### Parallel stack (merged from `origin/hvac-copilot`, only `reddit_fetcher.py` on live path via `online_search.py`)

| File | Role |
|------|------|
| `src/reddit_fetcher.py` | `RedditFetcher` (PRAW, read-only). Subs list: HVAC, hvacadvice, Refrigeration, askanelectrician, AskElectricians. |
| `src/web_ranker.py` | `WebRanker` + `WebDoc` dataclass. Full ranking pipeline (cosine + expertise + depth + affirmations). Not used on live path. |
| `src/progressive_search.py` | Tier system (KB_ONLY → FORUMS_SHALLOW → FORUMS_DEEP). Not used on live path. |
| `src/kb_engine.py` | MiniLM SentenceTransformer KB with `warmup()` + FIFO cache. Not used on live path; requires `sentence-transformers` which is **not installed**. |
| `src/hvac_tools.py` | `HVACToolkit` class-based dispatcher, depends on `db.py`. Not used on live path. |
| `src/db.py` | SQLite persistence. Not used on live path. |
| `src/embeddings.py` | Offline embedding builder. Not used on live path. |
| `src/demo_runner.py` | Teammate's offline demo runner. Not used on live path. |

### Archival (preserved, not on live path)

| File | Reason kept |
|------|-------------|
| `src/cactus_engine.py` | Thin wrapper, used by `agent.py` CLI. |
| `src/agent.py` | Standalone CLI session loop (not FastAPI). |
| `src/voice_handler.py` | Mic capture for CLI; browser handles mic for the server. |
| `src/cloud_fallback.py` | Gemini fallback path, disabled by design. |

---

## §7 Tool contract

All 6 schemas in `shared/hvac_tools.json`, loaded by `src/tools.py::_load_hvac_schemas()`. Dispatcher method name is `_tool_<name>`.

### 1. `query_kb(query, equipment_model?, top_k=3)` → `KBStore.search`
Keyword-scored over 18 entries. Strips embeddings from results. Returns top_k hits with `id`, `score`, `diagnosis`, brand, model, symptoms, parts.

### 2. `log_finding(location, issue, severity, part_number?, notes?)` → `FindingsStore.add_finding`
`severity ∈ {info, minor, major, critical}`.

### 3. `flag_safety(hazard, immediate_action, level)` → `FindingsStore.add_safety`
`level ∈ {caution, stop}`. Level=`stop` sets `is_stopped=True`, fires red banner.

### 4. `flag_scope_change(original_scope, new_scope, reason, estimated_extra_time_minutes?)` → `FindingsStore.add_scope_change`

### 5. `close_job(summary, parts_used[], follow_up_required, follow_up_notes?)` → `FindingsStore.close_job`
Emits structured resolution JSON. Snapshot returned in session state.

### 6. `search_online_hvac(query)` → `online_search.search`
The one network tool. See §5 case C. Current description (as of the last uncommitted tweak): *"Search online HVAC technician forums (r/HVAC, r/hvacadvice, r/Refrigeration) for field reports, community discussion, or uncommon equipment. Call this whenever the user asks to look online, check Reddit, find field reports, or asks about a rare unit not in the KB."*

System-prompt rule 6 (also uncommitted at write-time): *"ANY time the tech says 'look online', 'check Reddit', 'look it up', 'any field reports', 'search the forums', or similar phrasing — CALL search_online_hvac with a tight 5-10 word query. Do NOT ask clarifying questions first. Do NOT say you cannot browse — you can, via this tool."*

---

## §8 Data stores

### KBStore (`src/kb_store.py`)
- Loads all `kb/*.json` at startup, excludes `kb_index.json`.
- Dual-schema tokenizer: handles both the original flat format (`symptoms[].keywords[]`) and Amogh's richer format (`common_applications`, `common_faults`, `references`, pre-computed `embedding`/`symptoms_embedding`).
- `search(query, equipment_model=None, top_k=3)` returns keyword-match hits. **Strips any `embedding`, `symptoms_embedding`, or `_*` fields** before returning (commit `25b0499` — previously dumped 384-dim floats into model context).
- `entry_count` — 18.

### FindingsStore (`src/findings_store.py`)
Per-session in-memory dataclass store. Fields:
- `findings: list[Finding]` — location/issue/severity/part_number/notes/timestamp
- `safety_alerts: list[SafetyAlert]` — hazard/immediate_action/level/timestamp
- `scope_changes: list[ScopeChange]`
- `closure: ClosureRecord | None`
- `is_stopped: bool` — set by `flag_safety` level=stop
- `snapshot()` returns a JSON-serializable dict for `/ws/session` state broadcasts

### SessionLog (`src/session_log.py`)
JSONL file at `logs/session_<unix_ts>_<pid>.jsonl`. Event types emitted from `main.py`:
- `ws_connect`, `ws_disconnect`
- `msg_in` (kind, text_len, has_audio, has_image)
- `complete_start`, `complete_end` (ttft_ms, decode_tps, prefill_tokens, decode_tokens, response_len, n_function_calls)
- `tool_call` (name, args_preview, result_preview, exec_ms)
- `turn_end` (passes, total_ms, history_len, final_text_len)
- `turn_error`
- `prefill_startup`

Analyser CLI at `tools/analyse_log.py` prints per-turn table + aggregates (p50/p90/p95 TTFT, avg decode, tool histogram).

---

## §9 WebSocket protocol

**URL:** `wss://<host>/ws/session` (over HTTPS) or `ws://<host>/ws/session` (over HTTP).

### Client → server messages

| type | extra fields | handled at |
|------|--------------|------------|
| `text` | `content: string` | `main.py:724` |
| `audio` | (reserved, not wired in current build) | `main.py:731` |
| `multimodal` | `content: string`, `jpeg_b64: string` (data URL), optional `pcm_b64` | `main.py:743` |
| `reset` | — | `main.py:758` — clears history + findings |
| `cancel` | — | `main.py:764` — sets cancel flag + `cactus_stop` |
| `ping` | — | `main.py:777` — heartbeat |

### Server → client messages

| type | extra fields | emitted at |
|------|--------------|------------|
| `ready` | `kb_entries?: number` | `main.py:701, 762` |
| `token` | `token: string` | `main.py:552, 556` — streamed during decode |
| `tool_call` | `name, arguments, result` | `main.py:614` — after dispatcher runs |
| `session` | `state: FindingsSnapshot` | `main.py:401` — after any finding/safety change |
| `assistant_end` | `text, stats: {ttft_ms, decode_tps, …}` | `main.py:669` — end of turn |
| `error` | `message: string` | `main.py:708, 747, 781, 789, 804, 819` |
| `pong` | — | `main.py:778` |

Browser dispatch in `app.js:426` (switch on `msg.type`): `ready`, `token`, `tool_call`, `session`, `assistant_end`, `error`, `pong`.

---

## §10 Deployment

### Prereqs (not in the repo; set up separately)

- Cactus repo cloned into `cactus/` at repo root (gitignored).
- `cactus build --python` completed — produces `cactus/venv/` and the compiled Python bindings.
- Gemma 4 E4B weights at `cactus/weights/gemma-4-e4b-it/` (via `scripts/download_models.sh`).

### Mac Chrome (localhost HTTP)

```bash
cactus/venv/bin/pip install -r requirements.txt
cactus/venv/bin/python -m uvicorn src.main:app --host 127.0.0.1 --port 8000 --log-level info
# open http://127.0.0.1:8000/ in Chrome
```

Model loads in ~6 s. System-prompt prefill ~7 s. Total cold-start ~13 s.

### iPhone over Personal Hotspot (HTTPS)

Bypasses venue-wifi client isolation by putting both devices on the iPhone's private hotspot LAN (`172.20.10.0/28`).

```bash
# 1. iPhone: Settings → Personal Hotspot ON. Join Mac to it.
ipconfig getifaddr en0                # should be 172.20.10.X
MAC_IP=$(ipconfig getifaddr en0)

# 2. Generate a locally-trusted cert
brew install mkcert && mkcert -install
mkcert "$MAC_IP" localhost 127.0.0.1  # produces 172.20.10.X+2.pem + -key.pem

# 3. AirDrop $(mkcert -CAROOT)/rootCA.pem to iPhone
#    On iPhone: Settings → Profile Downloaded → Install
#    Then Settings → General → About → Certificate Trust Settings → toggle on

# 4. Serve HTTPS
cactus/venv/bin/python -m uvicorn src.main:app \
  --host 0.0.0.0 --port 8443 \
  --ssl-keyfile ./"$MAC_IP"+2-key.pem \
  --ssl-certfile ./"$MAC_IP"+2.pem \
  --log-level info

# 5. iPhone Safari → https://$MAC_IP:8443/
```

For natural TTS on iPhone: Settings → Accessibility → Read & Speak → Voices → English → download e.g. **Samantha (Enhanced)**. Siri-tier "Premium" voices (Zoe, Voice 1–5) are reserved by iOS and not exposed to Web Speech API.

### Browser UI tour
Mic button toggles hands-free (continuous Web Speech SR with 1.2 s silence submit). Stop button cancels in-flight generation + TTS. Spacebar also cancels when not focused on an input. Reset button clears history + findings. Voice dropdown selects `SpeechSynthesisVoice`.

---

## §11 Environment + secrets

### .env keys (all optional; defaults listed)

| key | default | used in |
|-----|---------|---------|
| `CACTUS_LLM_MODEL` | `google/gemma-4-E4B-it` | `src/config.py` |
| `MAX_TOKENS` | `512` (capped to 220 in main.py) | `src/main.py` |
| `TEMPERATURE` | `0.7` | `src/main.py` |
| `REDDIT_CLIENT_ID` | `""` | `src/online_search.py` (triggers PRAW path if set) |
| `REDDIT_CLIENT_SECRET` | `""` | same |
| `REDDIT_USER_AGENT` | `cactus-hvac-agent/0.1 (by u/anonymous)` | same |
| `ENABLE_CLOUD_FALLBACK` | `true` (unused; no fallback wired on server path) | `src/config.py` |

### What's in requirements.txt vs what's actually installed

| dep | requirements.txt | `cactus/venv/` | live path? |
|-----|------------------|----------------|------------|
| fastapi, uvicorn, websockets, python-multipart | yes | yes | yes |
| python-dotenv, requests | (transitive / implicit) | yes | yes |
| praw | yes | **yes (7.8.1)** | yes (optional upgrade for search) |
| sentence-transformers | yes | **NO** | no (`kb_engine.py` not on live path) |
| sounddevice, soundfile, pyaudio, numpy | yes | partial | archival (CLI agent) |

### Files gitignored but present on disk
- `172.20.10.2+2.pem`, `172.20.10.2+2-key.pem` — LAN certs (regenerate per-LAN)
- `.env` — copy from `.env.example`
- `logs/session_*.jsonl` — one per server run
- `data/findings.db` — SQLite (teammate's stack; not used on live path)
- `cactus/` — entire dir

---

## §12 Known risks & landmines

Ranked by demo-day severity.

### 🔥 1. Cactus SIGSEGV on mid-stream WebSocket disconnect
**Severity:** demo-killing. **Status:** no fix committed.
**Repro:** Start generation, close Safari tab OR iPhone backgrounds the app OR hotspot blips.
**What happens:** `starlette.websockets.WebSocketDisconnect` → error handler calls `cactus_reset()` → Cactus C++ side segfaults inside cleanup → uvicorn process exits 139 → entire server dies.
**Witnessed:** once mid-session today at ~05:50, once earlier at the same pattern.
**Mitigation proposal (NOT YET APPLIED):** wrap `cactus_reset()` in `try: ... except BaseException: pass` in `main.py` error paths; additionally, check `self.ws.client_state` before calling `cactus_reset` and skip if WS is already closed.
**Workaround for live demo:** instruct user NOT to close the Safari tab mid-reply; use the Stop button to cancel cleanly.

### ⚠️ 2. Gemma 4 E4B tool-use fragility
**Severity:** makes the online tool occasionally refuse or hallucinate.
**Symptom:** model replies *"I cannot browse Reddit"* even though the tool schema is present, OR fabricates Reddit results without calling the tool.
**Root cause:** Gemma 4 weights the tool description and system-prompt language heavily. Scary words ("ESCALATION ONLY", "NEVER chain") made it refuse to call the tool at all.
**Current mitigation:** tool description rewritten to *"Safe to call — this is the tool's normal use"*; system-prompt rule 6 is a direct imperative; added *"Never fabricate tool results"* guard. These changes are **uncommitted** at handoff time but will be the first commit.
**Residual risk:** context rot over many turns (5+) reverts the model to refusal mode. Fix: click **Reset session** between tests.

### ⚠️ 3. Multi-turn TTFT climb
**Severity:** demo-quality, not demo-killing.
**Measured:** turn 1 ~ 4 s TTFT, turn 10 ~ 20 s+.
**Cause:** conversation history + the assistant's own echoes of KB content accumulate in prefill.
**Partial fixes landed:** strip `tool`-role messages from history (commit `7d82464`), strip 384-dim embedding vectors from KB results (`25b0499`).
**What was NOT done:** trim SYSTEM_PROMPT or tool schemas (Phase 6 attempt caused a Cactus crash, rolled back).
**Workaround:** click Reset session between distinct scenarios.

### ⚠️ 4. Reddit credentials gated by Nov 2025 policy
**Severity:** not blocking — our JSON fallback works.
**Context:** Reddit discontinued self-service API keys in November 2025. New dev accounts must apply via Reddit Developer Support and wait ~7 days.
**What works now:** anonymous JSON at `https://www.reddit.com/r/<sub>/search.json` — live-tested today, returned real hits in 814 ms.
**Upgrade path:** when creds are approved, paste into `.env` and restart. `online_search.py::_praw_available()` auto-promotes to PRAW path for richer comment-tree data.

### ⚠️ 5. No ANE acceleration for Gemma 4 E4B
**Severity:** affects latency only; everything functions.
**Symptom:** every startup logs `[WARN] [npu] [gemma4] model.mlpackage not found; using CPU prefill`.
**Cause:** Cactus-Compute has not published the ANE-compiled `.mlpackage` for the E4B transformer yet (encoders-only `.mlpackage` is available). Not our code.
**Ceiling:** ~7 ms per prefill token on M4 Pro CPU. Cannot be reduced until Cactus ships ANE.

### 📼 6. No backup demo video recorded
Plan called for recording Demo A on Mac Chrome via text-path as the final safety net. Never done. If the live demo implodes, there is no submittable fallback.

### 🔒 7. LAN certs at repo root
`*.pem` is in `.gitignore` (commit `864b36b`), so they won't be pushed. They are physically at the repo root (`172.20.10.2+2.pem`, `...-key.pem`). LAN-only, safe on the Mac, but be aware they exist.

### 9. Two parallel Python stacks
Ours (functional, keyword KB) and Amogh's (class-based, MiniLM KB, SQLite). **Only the functional stack is on the live server path.** Amogh's stack is only entered via `src/online_search.py` importing `src/reddit_fetcher.py::RedditFetcher`. Anyone refactoring needs to understand both coexist and NOT to replace our working stack. See §6 annotations.

### 10. `sentence-transformers` in requirements.txt but not installed
Pulling it in would add ~300 MB of torch + MiniLM. It is not required on the live path. Document this for anyone running `pip install -r requirements.txt` fresh.

### 11. iOS native path retired
`archive/ios-abandoned/` preserved. Cactus iOS XCFramework had open bugs at hackathon date. Do not resume without confirming Cactus's Apple SDK has stabilized.

---

## §13 Recent changes (last 10 commits)

```
1a9208c  feat(tools): online escalation via Amogh's Reddit fetcher + ranker
bc736ec  merge: Amogh's web-ranker + Reddit fetcher + progressive search
864b36b  feat(web): iOS Safari support + mobile layout
9885542  feat: 448px camera + live MovinCool demo script + honest doc numbers
7d82464  fix: strip tool-role messages + hide thought/tool-call markers in UI
25b0499  fix(kb): strip 384-dim embedding vectors from query_kb results
bce253c  feat(kb): pull teammate's 8 new KB entries + dual-schema tokenizer
9ce2429  feat(web): real barge-in mid-TTS + spacebar kill switch (Phase 5a)
0dfee37  feat(web): pick the best available TTS voice + voice selector dropdown
b73e9de  feat: Stop button + cactus_stop + max_tokens cap
```

Amogh's parallel-stack commits on this branch were brought in via the merge at `bc736ec`:
```
896bd70  query optimizer
8a476c5  scrapper weight ranking
d32c1f0  feat(kb): add MovinCool Climate Pro X14 entry + server-room demo scenario
5a2bb09  hvac db update
```

---

## §14 Decision log

**Why Mac Python over iOS Swift.** Cactus's iOS XCFramework / SPM distribution had open link-time and Swift-interop bugs at hackathon date. The same Cactus binary runs via Python on the Mac cleanly. The on-device pitch is preserved (Mac is still the user's hardware). iOS port becomes a thin-client swap when Cactus's Apple SDK stabilizes.

**Why keyword KB over embedding KB.** 18 entries. Keyword search is <1 ms. Embedding-based search requires SentenceTransformers (~300 MB dep, ~10 s cold-start, ~40 ms per query even warm). No quality benefit at this scale. Amogh's `kb_engine.py` is preserved but not on the live path.

**Why Reddit JSON fallback as primary, not PRAW.** Reddit's Nov 2025 Responsible Builder Policy retired self-service API keys. New apps need ~7 days manual review. JSON endpoint is public, works anonymously, same data at a slightly lower rate limit. PRAW path is ready and auto-promotes when credentials land.

**Why functional dispatcher (`HVACToolDispatcher`) over class-based (`HVACToolkit`).** Our tests (`tests/test_tools.py`) are written against the functional interface. Two of the legacy shims (`execute_tool`, `handle_function_calls`) are needed by `src/agent.py` CLI. Simpler mental model for a demo.

**Why multimodal via file paths, not inline base64 content blocks.** Cactus docs show `images: ["/path"]` + `audio: ["/path"]` at the message level as the canonical Gemma 4 path. Lower JSON-parse overhead than streaming 500 KB of base64 per turn. `voice-sight` branch uses the inline path — we deliberately chose not to port it.

**Why voice I/O is browser-side, not server-side.** Web Speech API STT + TTS run in the browser for free. A server-side Whisper + cloud-TTS would add 500 ms–2 s per turn and break barge-in responsiveness. Pattern adopted from Wine_Voice_AI (see their `internal_doc/wine-voice-ai-workspace-build-history-and-interview-master-note.md`).

**Why keep Amogh's parallel stack merged but unused.** Credit preservation, tests landed in-repo, upgrade path open if we want to swap KB later. Cost of keeping: zero imports on the hot path.

---

## §15 Open tasks / roadmap

### Before submission (ranked)
1. **Commit the prompt-relaxation tweaks** that are currently uncommitted (shared/hvac_tools.json + src/main.py).
2. **Patch the Cactus SIGSEGV** (Known Risk #1) — ~10 min, high ROI.
3. **Record backup Demo A video** on Mac Chrome via text path — your action.
4. **Tag the submission commit** as `v0.1-hackathon`.

### After submission
1. Submit Reddit Developer Support application for PRAW credentials (~7 days).
2. Install `sentence-transformers` and benchmark `kb_engine.py` vs `kb_store.py` on the 18-entry corpus — decide whether to retire one.
3. iOS port once Cactus Apple SDK stabilizes.
4. Customer-facing companion app (see [docs/idea.md](docs/idea.md)).
5. KB flywheel — every `close_job` output indexed back into the KB, fine-tune at 10k records.

---

## §16 Testing

### Unit tests
```bash
cactus/venv/bin/python -m pytest tests/ -q
# Expected (as of 1a9208c + uncommitted tweaks): 65 passed
```

Breakdown (approximate, per last collection):
- `test_tools.py` — 13 tests — HVAC dispatcher paths including online escalation.
- `test_reddit_fetcher.py` — PRAW-level tests, fully mocked.
- `test_web_ranker.py` — 13 tests — ranking, expertise, depth, affirmations.
- `test_progressive_search.py` — tier escalation.
- `test_agent.py`, `test_cactus_engine.py` — CLI engine wrapper tests.

### Smoke tests (live server required)
```bash
# Boot a server first on :8000 or :8443, then:
cactus/venv/bin/python tests/smoke_ws.py "Carrier 58STA intermittent cooling clicking"
# → exercises one WS round-trip end-to-end

cactus/venv/bin/python tests/smoke_hvac.py
# → 8-case benchmark against the live server, prints tool-match table + timing
```

### Live-browser verification checklist
- `curl -k https://127.0.0.1:8443/healthz` returns `{"ok": true, "kb_entries": 18, "model_loaded": true}`.
- Browser at URL: status pill goes green, KB badge shows 18.
- Mac Chrome text path: *"Carrier 58STA intermittent cooling clicking"* → `query_kb` tool-card → model summarizes the Carrier entry.
- Mac Chrome online path: *"Check Reddit for field reports of York HH8 heat pump wiring issues"* → amber 🌐 tool-card → first-fire banner → model summarizes top threads.
- iPhone Safari same URL: all above work. Orange mic indicator in Dynamic Island during hands-free.

---

## §17 Glossary

- **TTFT** — time to first token. From user message arrival at Cactus → first decoded token.
- **Prefill** — tokenizing + KV-cache-filling the input (system prompt + tools + history + user message). Dominant cost on CPU at ~7 ms/token.
- **Decode** — actual token-by-token generation. ~17 tok/s on M4 Pro CPU.
- **KV cache** — Gemma 4 attention cache. `cactus_prefill()` pre-fills it with the system prompt at server startup so turn 1 doesn't pay that cost. `cactus_reset()` clears it (used between sessions or on error).
- **ANE** — Apple Neural Engine. Cactus hasn't shipped the E4B `.mlpackage` for it yet. CPU-bound until they do.
- **Sentinel tokens** — Gemma 4's `<|tool_call>`, `<|channel>thought`, etc. control markers. Our `stripHiddenMarkers` in `app.js` filters them out of the transcript + TTS stream.
- **`function_calls`** — array returned in the Cactus completion result when Gemma 4 emits tool calls. Dispatched by `HVACToolDispatcher.handle_function_calls`.
- **Multimodal message** — a single chat message with `content: string` + `images: [path]` + optional `audio: [path]`. Gemma 4 processes all three in ONE forward pass.
- **Barge-in** — user speaking mid-TTS and having the model stop speaking. Implemented in `app.js` by keeping Web Speech SR running during TTS and cancelling `speechSynthesis` on a ≥4-char transcript.
- **Enhanced voice** — Apple-provided named TTS voice (Samantha Enhanced, Susan Enhanced, Tom Enhanced). Exposed to Web Speech API on iOS. Different from Siri "Premium" voices which are system-reserved and not exposed.
- **Sub** — abbreviation for subreddit. Our curated list: `HVAC`, `hvacadvice`, `Refrigeration` (main three in `online_search.py`); plus `askanelectrician`, `AskElectricians` in Amogh's broader set in `reddit_fetcher.py`.

---

## Quickstart for an AI pickup agent

If you are an AI continuing this work, do these in order:

1. `git log --oneline -15` — confirm tip is as described in §1.
2. `cactus/venv/bin/python -m pytest tests/ -q` — confirm 65 pass.
3. `cactus/venv/bin/python -m uvicorn src.main:app --host 127.0.0.1 --port 8000 --log-level info` — boot local.
4. `curl http://127.0.0.1:8000/healthz` — confirm `model_loaded: true, kb_entries: 18`.
5. Open `http://127.0.0.1:8000/` in Chrome. Run Demo A from `demo/script_1_capacitor.md`. Confirm `query_kb` fires, summary speaks.
6. Read §12 (Known Risks) before touching `main.py`'s WS error path.
7. The ONE thing most worth fixing for demo polish is **Known Risk #1** (Cactus SIGSEGV on disconnect). It is ~10 lines of try/except in `main.py`.

If this document disagrees with the code, **trust the code**. File an update to this doc.
