# HVAC Copilot — YC × Cactus × DeepMind Submission

**One-liner:** A senior HVAC technician in your earbuds. Gemma 4 E4B via Cactus handles audio, vision, and function calling in one on-device forward pass — coaching field techs through HVAC repairs with zero cloud, zero data leaving the Mac.

**Team:** Rayhan Patel. Pair-programmed with Claude (Anthropic) for scaffolding + refactors.
**Repo:** [github.com/Rayhanpatel/Ycombinator-Cactus-Deepmind](https://github.com/Rayhanpatel/Ycombinator-Cactus-Deepmind) · branch `mac-webapp`

---

## The problem

The HVAC industry is bleeding senior techs. US BLS data puts the HVAC technician shortage at ~110K unfilled roles; the workforce is aging ~1.5 years per year while junior techs take 3–5 years to become effective. First-time-fix rate is the metric every field service company obsesses over — and the delta between senior and junior techs is 20+ points.

Voice + vision AI can close that gap. A junior tech on a roof can describe a symptom, point their camera at the unit, and get a senior-tech-quality walkthrough in seconds. The model never leaves the device — no customer audio, no customer premises video, no network dependency for basements, rooftops, or rural sites.

## What we shipped

- **5 HVAC tools** frozen in [shared/hvac_tools.json](shared/hvac_tools.json): `query_kb`, `log_finding`, `flag_safety`, `flag_scope_change`, `close_job`.
- **18 curated KB entries** across 15 brands and equipment categories (Carrier 58STA + 24ACC6, Trane XR14 + XV80, Lennox ML180 + XC21, Goodman GSX13 + GSX14, Rheem RA14 + RGPH, York YCD + YCJD, American Standard Silver 14 + Silver thermostat, Bryant 123A, Mitsubishi mini-split, MovinCool Climate Pro X14 portable spot cooler) + a generic gas-furnace safety card. Schema-tolerant loader handles both flat + rich KB shapes.
- **FastAPI + WebSocket backend** ([src/main.py](src/main.py)) running Gemma 4 E4B via Cactus Python on an M4 Pro. One shared Cactus handle, per-session state, `cactus_prefill()` on startup to warm the KV cache for the 500-token system prompt.
- **Browser UI** ([web/](web/)) with streaming transcript, color-coded tool-activity log, session counters, safety banner, push-to-talk mic capturing PCM16 LE @ 16 kHz, 1 fps camera keyframes, and browser TTS speaking the model's replies.
- **Native multimodal in one forward pass** — audio + JPEG keyframe + text all go through the `audio` / `images` message fields of a single `cactus_complete()` call. This is the canonical Gemma 4 path and what prior-year FunctionGemma 270M submissions couldn't do.
- **3-pass tool-call loop + fallback parser** that catches both `name(args)` and `name{args}` Gemma 4 emission forms, in case the C-side sentinel parser misses.
- **3 pre-baked demo scripts** in [demo/](demo/): capacitor happy path (90s), gas-smell safety interrupt (15s), contactor scope-change (30s).

## Architecture

```
Browser (Chrome)                               Mac M4 Pro
────────────────                               ──────────────────────────────
[mic PCM16 LE 16kHz]──┐                                ┌─► cactus_prefill (startup)
[camera 1fps JPEG]    │                                │
[text input]──────────┤  WS  /ws/session               ├─► cactus_complete ─► Gemma 4 E4B
                      ├──────────────────────────────►│       │               (audio+vision
[transcript tokens]◄──┤                                │       │                +text+tools
[tool_call events]    │                                │       │                in ONE pass)
[safety banner]       │                                │       ▼
[session state]       │                                │   HVACToolDispatcher
[browser TTS speaks]  │                                │       ├─ query_kb (keyword-scored, 18 entries, dual schema)
                      │                                │       ├─ log_finding (in-process)
                      │                                │       ├─ flag_safety (level=stop halts session)
                      │                                │       ├─ flag_scope_change
                      │                                │       └─ close_job (emits JSON)
                      └──◄── tool_call + tokens ───────┘
```

## Demo loop

1. Tech opens Chrome on `localhost:8000`, camera + mic on.
2. Points phone/camera at a mock HVAC unit, holds push-to-talk, says: *"I'm seeing intermittent cooling on a Carrier 58STA with a clicking sound right before it shuts off."*
3. Browser packs the latest JPEG keyframe + PCM audio into one WS message → server wraps them in a Gemma 4 multimodal message (`audio: [wav], images: [jpg]`) → `cactus_complete()` returns `query_kb` call → dispatcher retrieves the Carrier entry → model's follow-up pass summarizes *"Top hypothesis: failed dual-run capacitor. Kill power at disconnect before testing capacitance."*
4. Tech continues scripted turns; `log_finding` records the bulged capacitor; `close_job` emits a resolution JSON.
5. Pitch card: **"100% on-device. Zero API calls. Zero bytes left this Mac."**

## Measured performance

Against 8 curated HVAC cases via [tests/smoke_hvac.py](tests/smoke_hvac.py) running over the live WS endpoint:

- **88% tool-match** — the expected tool fired for 7/8 cases. The one miss chained `log_finding` + `flag_scope_change` instead of just the latter — a benign re-ordering, not a wrong answer.
- **100% arg-match** — the expected brand / symptom keyword appeared in every tool-call payload.
- **~3.9–4.5 s average time to first token** on M4 Pro CPU (Cactus hasn't published an ANE-compiled `model.mlpackage` for Gemma 4 E4B yet — the warning `[WARN] [npu] [gemma4] model.mlpackage not found; using CPU prefill` confirms it at server startup). Bare-model baseline is ~217 ms per `test_gemma4.py`; the ~4 s gap is the cost of our 5-tool schema block (~500 tokens) + rules-heavy system prompt + chat-template scaffold, measured at ~935 prefill tokens per turn.
- **~17 tok/s decode** — a 40-token reply streams in ~2.4 s.

## Challenges

1. **Cactus iOS distribution bugs.** We started on Swift + XCFramework; hit open bugs in the static-lib link and Swift FFI type wiring. Retired the iOS path, preserved the Swift scaffold at `archive/ios-abandoned/`, and moved to Cactus Python on the Mac — mature, proven, same binary.
2. **Gemma 4 tool-call emission varies.** Sometimes `name(args)` paren form, sometimes `<|tool_call>call: name{args}<tool_call|>` curly form. Both are official Gemma 4 variants; the Cactus C parser handles paren but not always curly. We added a thin AST-based fallback parser that catches both, dedupes, and strips the call expression from displayed text.
3. **StaticFiles at `/` swallowed WebSocket upgrades.** Mounting `StaticFiles(html=True)` at `/` before the `@app.websocket` decorator runs routes every upgrade into Starlette's HTTP-only assert. Fixed by registering the WS route first and mounting static LAST.
4. **Audio format plumbing.** `cactus_complete`'s `pcm_data` param wants a list of uint8 bytes (raw PCM16 LE), not int16 samples as the legacy voice_handler code assumed. We skipped that path entirely and took the SDK's canonical route: save browser audio as a WAV in `/tmp/`, pass the path via the message's `audio` field.

## Why this over prior FunctionGemma 270M finalists

Prior hackathon winners (CactusRoute, Warriors, cloudNein, FAT BOSS, TrailSense, Mingle) all defended against FunctionGemma 270M's limitations: 7-layer confidence gates, regex argument extraction, 35-rule query rewrites, AM/PM repair, Levenshtein enum snapping, multi-pass retry loops. These are clever workarounds for a 270M-param model that can't extract "6 AM" → `hour=6`.

**Gemma 4 E4B is ~15× larger and natively multimodal.** Most of those workarounds become unnecessary. What we spent time on instead:
- Domain depth — 18 curated HVAC KB entries (nine brands, multiple equipment categories, including the portable spot-cooler used in our live demo) beat a palette of generic `get_weather` / `set_alarm` tools.
- Real multimodal — audio + vision + text in ONE forward pass, not Whisper + ViT + FunctionGemma stitched together.
- Safety first-class — the `flag_safety` tool interrupts the session when the model hears gas, CO symptoms, arcing, or fire cues.

## Roadmap

- **iOS port** once Cactus's Apple SDK stabilizes. The FastAPI path is a thin-client swap away from a native Swift app.
- **Customer app** — the worker app's sibling in [docs/idea.md](docs/idea.md). Customer describes a problem by voice + video; a structured brief seeds the tech's On-Site session.
- **KB flywheel** — every `close_job` output gets indexed back into the KB. At 10k resolution records we fine-tune.
- **Scale to plumbing, electrical, appliance repair.** Same loop, new verticals.

## Hackathon requirements checklist

- [x] Uses **Gemma 4 on Cactus** — E4B variant, Cactus Python day-one support
- [x] Leverages **voice functionality** — PCM16 in via browser, TTS out via browser
- [x] **Working MVP** — 4 demo scripts (capacitor / gas-smell / contactor scope / live MovinCool), 88% tool-match on 8-case smoke benchmark
- [x] **On-device** — zero network calls from the model, zero data leaves the Mac

## What's in the repo

- [README.md](README.md) — quickstart + architecture
- [src/main.py](src/main.py) — FastAPI server, 470 lines
- [src/kb_store.py](src/kb_store.py), [src/findings_store.py](src/findings_store.py), [src/tools.py](src/tools.py) — domain core
- [web/](web/) — browser UI
- [shared/hvac_tools.json](shared/hvac_tools.json) — frozen tool contract (5 tools)
- [kb/](kb/) — 18 curated HVAC entries (dual-schema: flat legacy + richer new format with `common_applications` / `common_faults` / `references`)
- [demo/](demo/) — 4 demo scripts incl. [script_4_movincool_live.md](demo/script_4_movincool_live.md) scripted around a real in-room MovinCool Climate Pro X14
- [tests/test_tools.py](tests/test_tools.py) — 13 green unit tests
- [tests/smoke_hvac.py](tests/smoke_hvac.py) — 8-case live-server benchmark
- [tests/smoke_ws.py](tests/smoke_ws.py) — single-query WS probe for demo prep
- [archive/ios-abandoned/](archive/ios-abandoned/) — retired Swift scaffold (preserved)
- [docs/idea.md](docs/idea.md) — full product vision (customer + worker apps)

## License

MIT
