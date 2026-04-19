# HVAC Copilot — Architecture

Companion to [HANDOFF.md](../HANDOFF.md). HANDOFF.md is the pickup doc; this is the *why-it's-shaped-this-way* doc. Every claim here maps to a file, command, commit, or measured number.

Eight diagrams, one tech-stack table, ten design decisions, a known-gaps list. Read top-to-bottom for full context, or jump to a diagram for one subsystem.

---

## 0. The 30-second mental model

**HVAC Copilot is a FastAPI server running on a Mac, wrapping Cactus Python which wraps a CPU-resident Gemma 4 E4B model.** A browser (Chrome on Mac or Safari on iPhone over a personal hotspot) connects via WebSocket, sends text or text+image, receives streamed tokens. The model calls six tools: five are local (KB search, finding log, safety, scope, close), one is a network escalation to Reddit forums. All voice I/O happens browser-side via Web Speech API — zero audio crosses the WebSocket. This is a deliberate split: Gemma 4 is CPU-bound at ~7 ms/prefill-token on M4 Pro, so we don't add server-side STT/TTS latency on top.

---

## Diagram A — Deployment topology

```
┌───────────────────────────────────┐         ┌─────────────────────────────────────────┐
│  iPhone (Personal Hotspot)        │   WiFi  │  MacBook Pro M4                         │
│                                   │◄───────►│                                         │
│  • Shares cellular → wifi         │   SSID: │  ip: 172.20.10.2 (iPhone-owned LAN)     │
│  • Acts as NAT router             │  Rayhan'│                                         │
│  • 172.20.10.1/28 (gateway)       │   iPhone│  Process 1: uvicorn (src.main:app)      │
│                                   │         │    ├─ listens 0.0.0.0:8443 HTTPS/wss    │
│  ┌─────────────────────────────┐ │         │    ├─ TLS cert: mkcert-signed leaf      │
│  │ Safari tab                  │ │         │    │       for 172.20.10.2 + localhost   │
│  │ https://172.20.10.2:8443/   │ │         │    └─ single FastAPI app, async event   │
│  │  • wss:// to MacBook        │◄┼────────►│        loop + ThreadPoolExecutor pool    │
│  │  • getUserMedia mic+cam     │ │         │                                         │
│  │  • Web Speech API STT+TTS   │ │         │  Process 2: Gemma 4 E4B                 │
│  │  • Canvas 448×336 JPEG @1fps│ │         │    └─ loaded in-process via Cactus FFI  │
│  └─────────────────────────────┘ │         │        CPU ONLY (no ANE mlpackage       │
│                                   │         │                   for E4B transformer) │
│                                   │         │                                         │
│                                   │         │  Filesystem:                            │
│                                   │         │    kb/*.json ........ 18 entries       │
│                                   │         │    /tmp/hvac_*.jpg .. per-turn JPEGs   │
│                                   │         │    /tmp/hvac_*.wav .. per-turn WAVs    │
│                                   │         │    logs/session_*.jsonl                │
│                                   │         │    cactus/weights/gemma-4-e4b-it/ …   │
│                                   │         │                                         │
│                                   │         │  Outbound (ONLY from search_online_     │
│                                   │         │  hvac tool):                            │
└───────────────────────────────────┘         │    reddit.com JSON endpoint (port 443) │
                                              │                                         │
                                              │  Alt deployment: Mac Chrome on          │
                                              │    http://127.0.0.1:8000  (HTTP, no TLS)│
                                              └─────────────────────────────────────────┘
```

**Why this shape:**
- iPhone hotspot beats venue wifi: AP client-isolation on conference wifi usually blocks Mac↔iPhone direct traffic. The hotspot puts both devices on a private 2-device LAN the iPhone itself NATs out.
- HTTPS required for `getUserMedia` + `wss://` on non-localhost origins. mkcert gives a locally-trusted cert with ~2 min setup.
- Single uvicorn process, single Gemma 4 handle. Concurrency inside one process is fine; the single `engine.lock` serializes Cactus calls anyway (see §D).

---

## Diagram B — Component map (who imports whom)

```
                              ┌──────────────┐
                              │ web/app.js   │  752 lines
                              │  - WS client │
                              │  - mic+cam   │
                              │  - TTS+STT   │
                              └──────┬───────┘
                                     │ wss:// /ws/session
                                     │  msgs: text|multimodal|reset|cancel|ping
                                     ▼
┌─────────────────────────────────────────────────────────────────────┐
│  src/main.py  — 826 lines — uvicorn app entry                      │
│                                                                     │
│   ┌── Session class ──┐       ┌── module-level ──┐                 │
│   │ messages[]        │       │ SYSTEM_PROMPT    │  ~850 tokens    │
│   │ dispatcher        │       │ GEN_OPTIONS      │  max_tokens=220 │
│   │ findings          │       │ TOOL_NAMES set   │                 │
│   │ sid (8-hex)       │       │ _TOOL_CALL_PAREN │  regex          │
│   │ cancel_flag       │       │ _TOOL_CALL_CURLY │  regex          │
│   └───────────────────┘       │ parse_tool_calls │                 │
│                                │   _from_text    │                 │
│                                └──────────────────┘                 │
│                                                                     │
│   Routes:  GET /          ├─ web/  (StaticFiles, html=True)        │
│            GET /healthz   │                                         │
│            GET /logs/...  │                                         │
│            WS  /ws/session│                                         │
└──────┬──────────────────┬─────────────┬──────────────┬──────────────┘
       │                  │             │              │
       ▼                  ▼             ▼              ▼
┌──────────────┐ ┌─────────────┐ ┌──────────┐ ┌─────────────────┐
│ src/tools.py │ │ src/kb_     │ │ src/     │ │ src/session_    │
│  196 lines   │ │   store.py  │ │ findings │ │   log.py        │
│              │ │  139 lines  │ │ _store.py│ │   125 lines     │
│ HVACToolDisp │ │             │ │ 110 lines│ │                 │
│ _tool_query..│ │ load 18     │ │          │ │ log_event()     │
│ _tool_log..  │ │  kb/*.json  │ │ per-sess │ │ /logs endpoints │
│ _tool_flag_..│ │ keyword-sc. │ │ state:   │ │ JSONL per run   │
│ _tool_close..│ │ dual-schema │ │ findings │ │                 │
│ _tool_search_│ │ tokenizer   │ │ safety   │ │                 │
│  online_hvac │ │ strip embed │ │ scope    │ │                 │
└──────┬───────┘ └─────────────┘ │ closure  │ └─────────────────┘
       │                         │ is_stop  │
       │                         └──────────┘
       ▼ (lazy import)
┌──────────────────┐       ┌─────────────────────────────────────────┐
│ src/online_      │       │   Amogh's parallel stack (merged,      │
│   search.py      │──────►│   only reddit_fetcher is live-path):   │
│   155 lines      │       │                                         │
│                  │       │   src/reddit_fetcher.py  ← USED        │
│ if env has keys: │       │   src/web_ranker.py                    │
│   use praw path  │       │   src/progressive_search.py            │
│ else:            │       │   src/kb_engine.py      (needs         │
│   JSON fallback  │       │    sentence-transformers, NOT loaded)  │
│                  │       │   src/hvac_tools.py     (class-based)  │
│ 5s timeout via   │       │   src/db.py, embeddings.py, demo_runner│
│ ThreadPoolExec   │       │                                         │
└──────────────────┘       └─────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│  Cactus FFI  (src.cactus from cactus/python/src/cactus.py)           │
│                                                                      │
│   cactus_init(weights_path, ...)  → handle                           │
│   cactus_prefill(handle, messages) → cache system prompt             │
│   cactus_complete(handle, messages, options, tools, on_token, pcm)   │
│                                    → { response, function_calls[],   │
│                                        ttft_ms, decode_tps, ... }    │
│   cactus_stop(handle)            ← called from different thread      │
│                                    to interrupt cactus_complete     │
│   cactus_reset(handle)           ← clears KV cache                   │
│   cactus_destroy(handle)                                             │
└──────────────────────────────────────────────────────────────────────┘
```

**Color code:**
- Unlabeled boxes are live-path code executed per WS turn.
- The "parallel stack" block is imported lazily via `online_search.py` → `reddit_fetcher.py`. Nothing else in that block runs.
- Legend: live-serving (Session path) → `main.py` → `tools.py` → {KBStore, FindingsStore} OR → `online_search.py` → `reddit_fetcher.py`.

---

## Diagram C — One text-only turn (sequence)

```
Browser (app.js)          FastAPI (main.py)        Cactus thread        Gemma 4 E4B
      │                         │                       │                    │
      │─── wss send ───────────▶│                       │                    │
      │  {type:"text", content} │                       │                    │
      │                         │                       │                    │
      │                         │ Session.add_user_text │                    │
      │                         │ strip_history_refs    │                    │
      │                         │ strip_history_tool    │                    │
      │                         │                       │                    │
      │                         │─ run_in_executor ────▶│                    │
      │                         │   cactus_complete(    │ tokenize messages  │
      │                         │     messages,         │ prefill KV cache   │
      │                         │     GEN_OPTIONS,      │ ─────────────────▶ │
      │                         │     tools_json,       │                    │
      │                         │     on_token          │                    │
      │                         │   )                   │                    │
      │                         │                       │◄── tok "I'" ───────│  (on_token fires
      │                         │◄──── call_soon_thread │                    │   on Cactus thread)
      │                         │      put_nowait(tok)  │                    │
      │                         │                       │                    │
      │                         │ async loop pulls      │                    │
      │                         │ token_queue.get()     │                    │
      │                         │                       │                    │
      │◄── wss recv ──────────│                       │                    │
      │  {type:"token", tok}    │                       │                    │
      │                         │                       │                    │
      │ appendToAssistant()     │                       │                    │
      │ stripHiddenMarkers()    │                       │                    │
      │ sentenceBuffer += delta │                       │                    │
      │ on ". " → queueSpeech() │                       │                    │
      │ SpeechSynthesisUtter.   │                       │                    │
      │                         │                       │◄── tok "ll " ──────│
      │◄────── token ──────────│                       │                    │
      │ (TTS speaks sentence    │                       │                    │
      │  as it completes)       │                       │  ...               │
      │                         │                       │                    │
      │                         │                       │◄── {response,      │
      │                         │◄── raw json ──────────│     function_calls,│
      │                         │                       │     ttft_ms, ...}  │
      │                         │                       │                    │
      │                         │ parse, log_event      │                    │
      │                         │                       │                    │
      │                         │ if function_calls:    │                    │
      │                         │   loop back to pass N+1 (see Diagram E)   │
      │                         │ else:                                     │
      │                         │                                           │
      │◄── wss recv ──────────│ {type:"assistant_end", text, stats}        │
      │ finishAssistant()       │                                           │
      │ flushSentenceBuffer(true)                                           │
      │                         │                                           │
```

**Key detail:** `on_token` runs on a Cactus C thread, not the asyncio loop. It uses `loop.call_soon_threadsafe(token_queue.put_nowait, tok)` (main.py:521) to hand the token to the event loop. The loop pulls at 50 ms poll interval and sends over WS.

---

## Diagram D — Multimodal turn (text + camera frame)

```
  Browser                                  Server                       Gemma 4
┌───────────┐                          ┌──────────┐                    ┌──────────┐
│ Camera on │                          │          │                    │          │
│ 1fps loop:│                          │          │                    │          │
│ canvas    │                          │          │                    │          │
│  .draw(   │                          │          │                    │          │
│   video)  │                          │          │                    │          │
│  .toData  │                          │          │                    │          │
│   URL(    │                          │          │                    │          │
│   "img/   │                          │          │                    │          │
│   jpeg",  │                          │          │                    │          │
│   0.7)    │──┐                       │          │                    │          │
└───────────┘  │                       │          │                    │          │
               ▼                       │          │                    │          │
        pendingFrameB64 (up-to-date JPEG base64)  │                    │          │
               │                       │          │                    │          │
               │  User types or speaks │          │                    │          │
               │  → sendUtterance(text)│          │                    │          │
               │                       │          │                    │          │
┌──────────────▼──────────────────┐    │          │                    │          │
│ ws.send(JSON.stringify({        │    │          │                    │          │
│   type: "multimodal",           │───▶│  decode  │                    │          │
│   content: "describe this",     │    │  base64  │                    │          │
│   jpeg_b64: pendingFrameB64     │    │          │                    │          │
│ }))                             │    │  fs.write│                    │          │
│                                 │    │  /tmp/   │                    │          │
│  NB: JPEG is ~15-40 KB base64.  │    │  hvac_   │                    │          │
│  448-px width, 72% quality.     │    │  <ts>.   │                    │          │
│                                 │    │  jpg     │                    │          │
│  224 was too low to OCR product │    │          │                    │          │
│  labels ("MOVINCOOL CLIMATE PRO │    │          │                    │          │
│  X14"); 448 works — commit      │    │          │                    │          │
│  9885542.                       │    │          │                    │          │
└─────────────────────────────────┘    │          │                    │          │
                                       │          │                    │          │
                                       │  append  │                    │          │
                                       │  to msgs │                    │          │
                                       │  {role:  │                    │          │
                                       │  "user", │                    │          │
                                       │  content:│                    │          │
                                       │  "...",  │                    │          │
                                       │  images: │                    │          │
                                       │  ["/tmp/ │                    │          │
                                       │   hvac_  │                    │          │
                                       │   <ts>.  │                    │          │
                                       │   jpg"]} │                    │          │
                                       │          │                    │          │
                                       │  cactus_ │                    │          │
                                       │  complete│───────────────────▶│ vision   │
                                       │          │  tokenize image +  │ encoder  │
                                       │          │  text in ONE       │ + text   │
                                       │          │  forward pass      │ one-pass │
                                       │          │                    │          │
                                       │          │◄───────────────────│  tokens  │
```

**Why file paths, not inline base64 in the message.content array:**

Two viable Cactus/Gemma 4 patterns:
- **File-path form (what we use):** `{role, content: string, images: [path]}`. Matches Cactus Python README.
- **Content-block form:** `{role, content: [{type:"image_url", image_url:{url:"data:image/jpeg;base64,..."}}, ...]}`. Works too; used in `voice-sight` branch.

We picked file-path because:
- Lower JSON-parse overhead per turn (base64 strings in messages slow down Cactus's JSON decoder and balloon memory for each turn they stay in history).
- Matches the canonical documented path.
- `_strip_history_file_refs` (main.py:462) easily scrubs file refs from history once the turn is done so old images don't waste prefill tokens.

---

## Diagram E — Three-pass tool loop + fallback parsers

```
                    Session.run_turn() entry
                             │
                             ▼
                   ┌─────────────────────┐
                   │ pass_idx = 0        │
                   │ final_text = ""     │
                   └─────────┬───────────┘
                             │
                             ▼
   ┌────────────────── PASS_LOOP ◄─────────────────────┐
   │                                                   │
   │              ┌────────────────────┐               │
   │              │ _complete_once()   │               │
   │              │   └─cactus_complete│               │
   │              │     via ThreadPool │               │
   │              │     tokens → WS    │               │
   │              └──────┬─────────────┘               │
   │                     │                             │
   │                     ▼                             │
   │         ┌─────────────────────────┐               │
   │         │ parsed.function_calls ? │               │
   │         └──────┬──────────────────┘               │
   │                │                                  │
   │         (present)  (empty)                        │
   │            │          │                           │
   │            │          │ parse_tool_calls_         │
   │            │          │ from_text(response)       │
   │            │          │                           │
   │            │          ▼                           │
   │            │   ┌────────────────────────────┐     │
   │            │   │ Regex fallback:            │     │
   │            │   │  1. _TOOL_CALL_PAREN       │     │
   │            │   │     name(arg=val, …)       │     │
   │            │   │     → _parse_kwargs_paren  │     │
   │            │   │       ast.literal_eval     │     │
   │            │   │  2. _TOOL_CALL_CURLY       │     │
   │            │   │     name{key: val, …}      │     │
   │            │   │     → _parse_kwargs_curly  │     │
   │            │   │       naive splitter       │     │
   │            │   │  Dedup by (name,args-json) │     │
   │            │   └──────┬─────────────────────┘     │
   │            │          │                           │
   │            │          ▼                           │
   │            │    calls found ?                     │
   │            │    │      │                          │
   │            │  (yes)   (no) ──────► break ─┐       │
   │            │    │                         │       │
   │            ▼    ▼                         │       │
   │      ┌──────────────────────┐             │       │
   │      │ _dispatch_calls()    │             │       │
   │      │  for each call:      │             │       │
   │      │   HVACToolDispatcher │             │       │
   │      │    .execute(name,    │             │       │
   │      │     arguments)       │             │       │
   │      │  emit tool_call WS   │             │       │
   │      │  append tool msg to  │             │       │
   │      │  self.messages       │             │       │
   │      └──────┬───────────────┘             │       │
   │             │                             │       │
   │             ▼                             │       │
   │       pass_idx += 1                       │       │
   │       if pass_idx < 3: ─────────────┐     │       │
   │       else: break ──────────────────┼─────┤       │
   │                                     │     │       │
   └─────────────────────────────────────┘     │       │
                                               │       │
                                               ▼       ▼
                                   send {type:"assistant_end", text, stats}
                                   log_event turn_end
```

**Why 3 passes max:**
- Pass 1: initial `query_kb` call.
- Pass 2: model summarizes the KB result.
- Pass 3: safety net if the model chains `log_finding` or `close_job` after summary.
- Higher caps would let pathological models loop indefinitely on a single user turn.

**Why two regex patterns:**
- Gemma 4's tool-call emission isn't fully deterministic. Both `query_kb(query="…")` (paren form) and `query_kb{query: "…"}` (curly form) appear in the wild. The Cactus C-side parser catches the paren form via sentinels; curly gets through as plain text. We extract both. Patterns at main.py:91 and main.py:100.

**`_parse_kwargs_curly` is naive by design** — it handles our schema's flat `key: value` pairs. Doesn't recurse into nested dicts. Our 6 tools don't need it.

---

## Diagram F — Online escalation branch

```
                         _tool_search_online_hvac(query)
                               │
                               ▼
                    ┌────────────────────────┐
                    │ from src.online_search │
                    │   import search        │  lazy import
                    └──────────┬─────────────┘
                               │
                               ▼
                         search(query)
                               │
                               ▼
                    ┌──────────────────────┐
                    │ _praw_available()    │
                    │  cfg.REDDIT_CLIENT_  │
                    │   ID + SECRET set?   │
                    │  import praw ok?     │
                    └──────────┬───────────┘
                               │
                        ┌──────┴──────┐
                     (yes)          (no)
                        │              │
                        ▼              ▼
                ┌─────────────┐  ┌────────────────┐
                │ _search_    │  │ _search_json() │
                │   praw()    │  │                │
                │             │  │ for sub in SUBS:
                │ praw.Reddit │  │   requests.get │
                │  (read_only)│  │   reddit.com/  │
                │             │  │   r/<sub>/     │
                │ for sub in  │  │   search.json  │
                │  SUBS:      │  │   timeout=3s   │
                │   subreddit │  │                │
                │   .search(  │  │ sort by score  │
                │    query,   │  │ trim to 5      │
                │    limit=3) │  │                │
                │             │  │                │
                │ collect     │  │ return {ok,    │
                │ WebDocs     │  │  source:"json",│
                │ → dicts     │  │  results: [...]}│
                │             │  │                │
                │ return {ok, │  │                │
                │  source:    │  │                │
                │  "praw",    │  │                │
                │  results}   │  │                │
                └──────┬──────┘  └────────┬───────┘
                       │                  │
                       └────────┬─────────┘
                                ▼
                  ┌──────────────────────────────┐
                  │ ThreadPoolExecutor wrapper   │
                  │ .submit(worker, q)           │
                  │ .result(timeout=5.0)         │
                  │                              │
                  │ on TimeoutError:             │
                  │   return {ok:false,          │
                  │           reason:"timeout"}  │
                  │ on any Exception:            │
                  │   return {ok:false, reason}  │
                  └──────────────┬───────────────┘
                                 │
                                 ▼
               dict: {ok, source, subs_queried, results: [
                      {title, text, url, score, depth}, …
                    ]}
                                 │
                                 ▼
                 (back to dispatcher → tool msg appended
                  to self.messages → next pass summarizes)
                                 │
                                 ▼
                    (UI renders amber 🌐 card,
                     first-fire banner shown)
```

**Why the hybrid shim, not just PRAW:**
- Reddit discontinued self-service API keys in November 2025 (Responsible Builder Policy). New dev accounts need ~7-day manual review.
- JSON endpoint at `reddit.com/r/<sub>/search.json` is still public, no auth, anonymous rate limit ~60 req/hour per IP. Our demo uses 1–5 calls total.
- PRAW path auto-promotes when creds land in `.env` — no restart needed beyond config change on next import.

**Why 5 s wall-clock via ThreadPoolExecutor:**
- `requests.get(timeout=3.0)` is per-connection, not wall-clock. A stalled DNS resolution or socket can exceed that.
- `concurrent.futures.ThreadPoolExecutor(...).submit(...).result(timeout=5.0)` gives us a hard wall-clock kill. The worker keeps running but the dispatcher moves on with `{ok: false, reason: "timeout"}`.

---

## Diagram G — Startup sequence

```
t=0.0 s    uvicorn spawn            │ python -m uvicorn src.main:app
             │                      │
             ▼                      │
t=0.1 s    import src.main          │ imports FastAPI, cactus, tools,
             │                      │  kb_store, findings_store, session_log
             │                      │
             ▼                      │
t=0.2 s    app = FastAPI()          │ routes registered (/, /healthz, /logs/*,
             │                      │  /ws/session)
             │                      │
             ▼                      │
t=0.3 s    KBStore.load()           │ glob kb/*.json, exclude kb_index.json
             │                      │  parse 18 entries, build index,
             │                      │  strip embedding fields
             │                      │
             ▼                      │
t=0.5 s    KB loaded: 18 entries   │ logger INFO
             │                      │
             ▼                      │
t=0.5 s    engine.load()            │ cactus_init(weights_path) opens
             │                      │  gemma-4-e4b-it model files, allocates
             │                      │  KV cache, sets up encoders
             │                      │
             ▼                      │
             (CPU prefill warning)  │ [WARN] [npu] [gemma4] model.mlpackage
             │                      │  not found; using CPU prefill
             │                      │
             ▼                      │
t=3.9 s    engine.handle ready      │ ≈ 6 s cold, ≈ 4 s warm
             │                      │
             ▼                      │
t=4.0 s    engine.prefill_system()  │ cactus_prefill(handle, SYSTEM_PROMPT)
             │                      │  precomputes KV cache for the ~850-
             │                      │  token system prompt so turn-1 TTFT
             │                      │  skips that prefill
             │                      │
             ▼                      │
t=11.5 s   System prompt prefilled │ 7.6 s — dominates boot time
             │                      │
             ▼                      │
t=11.6 s   uvicorn starts accepting │ INFO: Application startup complete
             │  HTTPS at 0.0.0.0:8443│
             │                      │
             ▼                      │
           READY — first WS can     │
           connect and message      │
```

**Why prefill the system prompt:**
- The system prompt is ~850 tokens of rules + tool triggers. Without prefill, every new WS session pays that cost on turn 1 (~6 s).
- `cactus_prefill` runs once at boot. KV cache is reused across every WS session.
- Cost: ~7.6 s at boot that would otherwise be distributed across sessions as ~6 s tax on turn 1 each. Net win: predictable TTFT once the server is up.

---

## Diagram H — iPhone hotspot + TLS chain

```
  ┌─────────────────────────┐       WiFi-AP       ┌─────────────────────────┐
  │  iPhone                 │                     │  MacBook Pro            │
  │                         │                     │                         │
  │  Personal Hotspot ON    │                     │                         │
  │  SSID: Rayhan's iPhone  │                     │  en0: 172.20.10.2       │
  │  Gateway: 172.20.10.1   │◄─── 802.11 ────────►│  GW:  172.20.10.1       │
  │                         │                     │                         │
  │  NAT → cellular                                │                         │
  │   5G → carrier CGNAT                           │                         │
  │   → Internet                                   │                         │
  │                                                │                         │
  │  Safari tab                                    │                         │
  │  https://172.20.10.2:8443/                    │                         │
  │                                                │                         │
  │   │                                            │                         │
  │   ▼                                            │                         │
  │  TLS ClientHello                               │                         │
  │   SNI: 172.20.10.2                             │                         │
  │                                                │                         │
  └────────────┬──────────────────────────────────┘                         │
               │                                   │                         │
               │  ────── TLS handshake ──────────► │                         │
               │                                   │  uvicorn --ssl-keyfile  │
               │                                   │  --ssl-certfile         │
               │                                   │                         │
               │  ◄───── cert chain ───────────── │  leaf: 172.20.10.2+2.pem│
               │                                   │    signed by mkcert CA  │
               │                                   │    SAN: 172.20.10.2 +   │
               │                                   │         localhost +     │
               │                                   │         127.0.0.1       │
  Safari validates:                                │                         │
  ┌─────────────────────────┐                      │                         │
  │ iOS trust store:        │                      │                         │
  │  ├─ built-in Apple CAs  │                      │                         │
  │  └─ user profile:       │                      │                         │
  │     mkcert rootCA.pem   │ ◄── installed via    │                         │
  │     trusted in:         │    Settings→General  │                         │
  │     General → About →   │    →About→Cert Trust │                         │
  │     Cert Trust Settings │                      │                         │
  └─────────────────────────┘                      │                         │
               │                                   │                         │
               ▼                                   │                         │
  ✓ chain valid                                    │                         │
  ✓ SAN matches IP                                 │                         │
  ✓ HTTPS established                              │                         │
               │                                   │                         │
               ▼                                   │                         │
  Upgrade: GET /ws/session → wss://                │                         │
```

**Why mkcert instead of Let's Encrypt:**
- LE needs a public-resolvable FQDN. `172.20.10.2` is a private RFC1918 address, not publicly reachable.
- mkcert generates a local root CA + signs leaf certs for arbitrary hostnames/IPs. One-time install on each device's trust store.
- Cost: `brew install mkcert && mkcert -install && mkcert 172.20.10.2 localhost 127.0.0.1` + AirDrop `rootCA.pem` to iPhone.

**Why the trust profile is required on iOS:**
- Safari's `getUserMedia` for camera + mic requires HTTPS on non-localhost origins. Self-signed untrusted → Safari blocks.
- Without profile install, you'd get a "Cannot verify server identity" blocker dialog. With install + trust toggle, Safari shows the green lock.

---

## Tech stack

| Layer | Tech | Version | Where | Why |
|-------|------|---------|-------|-----|
| OS | macOS (Darwin 25.3.0) | — | Mac host | M4 Pro is the dev machine. |
| Python | CPython | 3.12.13 (in `cactus/venv`) | `#!/usr/bin/env python3` (all .py) | Cactus Python built against this version. |
| Web framework | FastAPI | 0.136.0 | [src/main.py:29](../src/main.py#L29) | Async WebSocket + dependency injection + auto OpenAPI. |
| ASGI server | uvicorn | 0.44.0 (+ standard extras) | runtime | Industry default for FastAPI. Supports `--ssl-keyfile` / `--ssl-certfile`. |
| WebSocket protocol | websockets | 16.0 | via uvicorn[standard] | |
| Starlette | starlette | 1.0.0 | transitive via FastAPI | WebSocket + StaticFiles implementation. |
| TLS (demo cert) | mkcert | latest brew | `172.20.10.2+2.pem` + `-key.pem` | Local cert for iPhone LAN demo. |
| HTTP client | requests | 2.33.1 | [src/online_search.py](../src/online_search.py) | Anonymous Reddit JSON fallback path. |
| Reddit client | praw | 7.8.1 | [src/reddit_fetcher.py](../src/reddit_fetcher.py) | Optional upgrade path (if creds in env). |
| LLM runtime | Cactus Python | repo-local build | `cactus/python/src/cactus.py` | On-device inference, vision+audio+text+tools in one forward pass. |
| LLM | Google Gemma 4 E4B-it | instruct variant | `cactus/weights/gemma-4-e4b-it/` | Effective 4B params, strong multimodal encoder. |
| Device | CPU | — | M4 Pro | No ANE `.mlpackage` shipped for E4B transformer yet. |
| KB storage | JSON files on disk | — | `kb/*.json` (18 files) | 18 entries; zero-dep keyword search is <1 ms. |
| Session storage | in-memory dataclasses | — | `FindingsStore` | Demo has no persistence requirement. Reset on server restart. |
| Observability | JSONL file | — | `logs/session_<ts>_<pid>.jsonl` | Tail-friendly, `jq`-parsable, no DB dep. |
| Browser TTS | Web Speech API `SpeechSynthesisUtterance` | browser-native | [web/app.js:179](../web/app.js#L179) | Free, on-device on iOS (Samantha/Evan Enhanced), no cloud. |
| Browser STT | Web Speech API `webkitSpeechRecognition` | browser-native | [web/app.js:45](../web/app.js#L45) | Same reason. Safari caveat: on iOS it's on-device via Siri. |
| Camera capture | Canvas 2D + `toDataURL("image/jpeg", 0.7)` | browser-native | [web/app.js:654](../web/app.js#L654) | No external encoder lib needed. |
| Sentence segmentation | `Intl.Segmenter` | browser-native (iOS 14.5+) | [web/app.js:134](../web/app.js#L134) | Zero-dep for progressive sentence-level TTS. |
| Tests | pytest | 8.x | `tests/` | 65 tests, all green. |
| Test suite | Our `test_tools.py` + Amogh's `test_web_ranker.py`, `test_reddit_fetcher.py`, `test_progressive_search.py` | — | `tests/` | Mocked, no network needed. |

---

## Design decisions (mapped to diagrams)

### D1. Mac Python instead of iOS Swift
*(context for diagram A)*
Cactus iOS XCFramework had unresolved link-time and Swift-interop issues at hackathon date. Same Cactus binary runs via Python on Mac cleanly (`test_gemma4.py` baseline: 5.8 s load, 217 ms TTFT bare, 28 tok/s). Pitch preserved: Mac is still the user's own hardware; nothing leaves except explicit online search. iOS port becomes a thin-client swap — replace `app.js` WebSocket with a Cactus Swift SDK call — once the Apple SDK stabilizes. Swift scaffold preserved at `archive/ios-abandoned/`.

### D2. iPhone hotspot instead of venue wifi
*(diagram H)*
YC conference wifi typically enforces AP client-isolation. Mac↔iPhone direct traffic blocked. iPhone Personal Hotspot puts both devices on a private 2-device LAN the iPhone NATs out to cellular. Costs negligible cellular data (WS JSON + 1–5 JPEGs per demo). Bonus: screen-recording the demo shows no venue-wifi involvement.

### D3. Browser-side voice I/O, not server-side
*(diagram C)*
Adding server-side Whisper STT + cloud TTS would stack 500 ms–2 s onto every turn and kill barge-in responsiveness. Web Speech API is browser-native and free. On iOS Safari it's on-device via Siri. Pattern adopted from the Wine_Voice_AI team's demo notes ("treat Safari as text-first" — we went further and made voice work there too via `webkitSpeechRecognition` + auto-restart on `onend`).

### D4. File-path multimodal, not inline base64
*(diagram D)*
Both work. File-path (`images: ["/tmp/x.jpg"]`) is the canonical Cactus documented path with lower JSON-parse overhead. Inline data-URL content blocks balloon every history entry. `_strip_history_file_refs` in [src/main.py:462](../src/main.py#L462) scrubs the path once the turn's done so old images don't pay prefill on future turns.

### D5. Keyword-scored KB, not embedding KB
*(diagram B, component map)*
18 entries. Amogh's `kb_engine.py` with MiniLM SentenceTransformers would cost ~300 MB in deps + ~10 s cold-start + ~40 ms per query. Keyword matching over the 18 flat + rich-schema entries is <1 ms, zero cold-start, no dep. `sentence-transformers` is in `requirements.txt` (inherited from merge) but deliberately NOT installed in the venv.

### D6. JSON fallback primary, PRAW optional
*(diagram F)*
Reddit's Responsible Builder Policy (Nov 2025) retired self-service API keys. PRAW requires approved Reddit dev creds; ~7-day manual review. Anonymous JSON endpoint `reddit.com/r/<sub>/search.json` is public, returns the same data, usable now. PRAW path is ready and auto-promotes when creds land. Measured: JSON fallback returned 5 real Reddit hits in 814 ms end-to-end.

### D7. 3-pass tool loop
*(diagram E)*
Typical HVAC turn is `query_kb → summarize → [optionally close_job]`. 3 passes covers it without risking a runaway model looping on itself. Tighter bounds (2) cut off summarization-after-chained-tools; looser (5+) turns bugs into time-wasters.

### D8. Dual-form tool-call fallback parser
*(diagram E)*
Gemma 4 doesn't always use the `<|tool_call_start|>` sentinel; sometimes emits `name(args)` or `name{args}` as plain text. The C-side parser catches sentinel + paren. We added AST-based paren parsing and a custom curly-brace tokenizer ([main.py:129](../src/main.py#L129)) so dispatch still works. Dedup by `(name, args-json)` prevents double-firing.

### D9. Single shared Cactus handle + `engine.lock`
*(diagram B)*
One Gemma 4 model, one KV cache; we can't run two completions on the same handle concurrently. `engine.lock: asyncio.Lock` in [main.py:537](../src/main.py#L537) serializes `cactus_complete` across sessions. Two sessions = one queue; fine for a 1–2-user demo.

### D10. SessionLog as JSONL, not DB
*(diagram B)*
JSONL is append-only, tail-friendly, `jq`-parsable, zero-dep. A SQLite log would need migrations + orm. Our `tools/analyse_log.py` (CLI, not shown here) parses the JSONL and prints p50/p90/p95 TTFT. If session volume ever exceeds the hackathon scale, move to DuckDB on the same files; no code change needed for writers.

---

## Known gaps

Things this architecture *deliberately doesn't cover* — honest list for the next engineer.

1. **Cactus SIGSEGV on mid-stream WS disconnect.** Known (HANDOFF §12 #1). Error path calls `cactus_reset()`, which sometimes segfaults inside Cactus cleanup if the model is actively generating. Not documented in Cactus docs; not wrapped in try/except yet in our code.

2. **No backpressure on token queue.** If Gemma 4 decodes faster than the WS can ship tokens to a slow client (e.g. laggy iPhone over cell), `token_queue` grows unbounded. In practice: ~17 tok/s decode vs ~10 Mbps WS — not a problem today. But there's no watermark.

3. **No authentication on WS.** Anyone reaching `wss://172.20.10.2:8443/ws/session` can use the model. Private hotspot LAN is the boundary. For production, add a token.

4. **No rate-limit on `search_online_hvac`.** Reddit's anonymous endpoint is ~60 req/hour per IP. A malicious session could burn that. Demo scale is 1–5 calls; production would need a bucket.

5. **`cactus_stop` is best-effort.** The CPU-bound `cactus_complete` call running in a ThreadPoolExecutor thread can take up to ~200 ms to actually notice the stop flag. Tokens streamed in that window still reach the client.

6. **History trimming is aggressive.** We strip tool-role messages + file refs + cap message count. This loses some multi-turn context quality in exchange for bounded TTFT. The model occasionally forgets what finding it just logged. Partial fix only.

7. **No vision encoder caching.** Every multimodal turn re-encodes the JPEG. Same unit across three turns = three encoder runs. Cactus has no per-image cache key exposed.

8. **Parallel Python stacks.** `kb_engine.py` + `hvac_tools.py` + `db.py` are merged but unused at runtime. Future refactorers will waste time picking which to trust unless they read HANDOFF §12 #9. Ideal: delete the parallel stack once we're sure nothing depends on it post-hackathon.

9. **Startup prefill assumes the system prompt is stable.** If `SYSTEM_PROMPT` changes at runtime, the prefilled KV cache becomes stale. We don't invalidate it. Every change requires a server restart.

10. **Safari Web Speech on iOS is on-device but undocumented by Apple.** We believe STT routes through Siri's local model; no public guarantee. A future iOS update could start sending audio to Apple servers and we'd never know.

---

## Cross-references

| Need to change… | Read HANDOFF §X first | Then this file |
|-----------------|------------------------|----------------|
| How the model is called | §4, §12 | `src/main.py` _complete_once at line 513 |
| Which tools exist | §7 | `shared/hvac_tools.json`, `src/tools.py` |
| How tool dispatch loops | — | `src/main.py:run_turn`, diagram E |
| KB data shape | §8 | `src/kb_store.py`, `kb/*.json` |
| How images get in | §5, §9 | diagram D, `src/main.py` multimodal handler at line 743 |
| How online search works | §7 #6 | diagram F, `src/online_search.py` |
| Deployment for iPhone | §10, §11 | diagram H |
| Session logging | §8 SessionLog | `src/session_log.py`, `tools/analyse_log.py` |
| Known landmines | §12 | this file's "Known gaps" |

---

## Update protocol

This doc goes stale fast. After any commit that changes:
- A tool schema or dispatcher → update §7 diagrams + D7/D8
- The WS protocol → update diagram C + §9 cross-ref
- A new dep or version → update the tech stack table
- A new known risk → add to Known gaps here AND HANDOFF §12

If reality and this document disagree, trust the code and file a fix here.
