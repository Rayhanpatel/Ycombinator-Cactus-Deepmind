# 🌵 HVAC Copilot

> **A senior HVAC tech in your earbuds.** Gemma 4 runs 100% on-device via
> Cactus, sees what the technician sees, hears what they describe, and
> coaches them through the fix with structured tool calls into a curated
> knowledge base.

[![Cactus](https://img.shields.io/badge/Powered_by-Cactus-green)](https://cactuscompute.com)
[![Gemma 4 E4B](https://img.shields.io/badge/Model-Gemma_4_E4B-blue)](https://ai.google.dev/gemma)
[![YC × DeepMind](https://img.shields.io/badge/Hackathon-YC_%C3%97_DeepMind-orange)](https://events.ycombinator.com/voice-agents-hackathon26)

Hackathon: YC × Cactus × Google DeepMind — Voice Agents on Gemma 4, April 19–20 2026.

---

## The pitch

Senior HVAC techs are retiring faster than juniors can replace them; first-time-fix rate is the metric field service companies obsess over. HVAC Copilot puts a senior tech on every truck: a browser-based voice + vision agent running Gemma 4 E4B on the MacBook Pro M4 via Cactus Python. The tech describes a symptom, the model retrieves matching past cases from a 10-entry curated KB, coaches through the fix one step at a time, and generates a structured resolution record at close. Every fix makes the next one better. Zero API calls, zero data off device.

## What's in this repo

```text
src/
├── main.py              # FastAPI + /ws/session (the server)
├── kb_store.py          # Keyword-scored search over kb/*.json
├── findings_store.py    # Per-session state (findings, safety, scope, closure)
├── tools.py             # 5 HVAC tools wired to the schema in shared/hvac_tools.json
├── cactus_engine.py     # Cactus wrapper (used by the standalone CLI)
├── config.py            # .env loading
├── agent.py             # Standalone CLI (NOT the server — use src/main.py)
├── voice_handler.py     # Mic capture for CLI (browser does this for the server)
└── cloud_fallback.py    # Gemini fallback (off by default; on-device story)

web/
├── index.html           # Single-page UI
├── app.js               # WS client + mic (PCM16 LE) + 1fps camera keyframes
└── styles.css

shared/hvac_tools.json   # Frozen tool schemas (5 tools, OpenAI function format)
kb/                      # 10 curated HVAC entries (Carrier, Trane, Lennox, …)
demo/                    # 3 pre-baked demo scripts (capacitor, gas smell, scope change)
tests/
├── test_tools.py        # 13 passing tests for the HVAC dispatcher
└── smoke_ws.py          # Live-server WS smoke test for demo prep

archive/ios-abandoned/   # Swift scaffold (retired — see archive README)
HANDOFF_IOS_LEGACY.md    # iOS handoff, kept for reference
Internal_docs/           # idea.md (vision), build_plan.md, conversation history
```

## The 5 HVAC tools

Each tool's schema lives in [shared/hvac_tools.json](shared/hvac_tools.json) and is dispatched by [src/tools.py](src/tools.py):

- **`query_kb(query, equipment_model?)`** — keyword-scored search over the 10 KB entries
- **`log_finding(location, issue, severity, part_number?, notes?)`** — records a diagnosed problem
- **`flag_safety(hazard, immediate_action, level)`** — level=`stop` halts the session, fires the red banner in the UI
- **`flag_scope_change(original_scope, new_scope, reason, estimated_extra_time_minutes?)`**
- **`close_job(summary, parts_used, follow_up_required, follow_up_notes?)`** — emits the structured resolution record

## Quickstart

### Prereqs

- Mac with Apple Silicon (tested on M4 Pro)
- Python 3.12 via `cactus/venv/`
- The Cactus repo cloned into `cactus/` and built (`cactus build --python`), Gemma 4 E4B weights downloaded to `cactus/weights/gemma-4-e4b-it/`

If you're setting up fresh: `./scripts/setup_cactus.sh` and `./scripts/download_models.sh`.

### Run the server

```bash
# Install deps into the cactus venv (already the project's default Python)
cactus/venv/bin/pip install -r requirements.txt

# Start FastAPI + Cactus. Model load takes ~6s.
cactus/venv/bin/python -m uvicorn src.main:app --host 127.0.0.1 --port 8000
```

Then open `http://127.0.0.1:8000/` in Chrome.

### Run the demos

Use the scripts in [demo/](demo/) as your voice prompts. The web UI:

1. **Demo A — Carrier 58STA capacitor:** *"I'm seeing intermittent cooling on a Carrier 58STA with a clicking sound right before it shuts off."* → fires `query_kb`, retrieves the Carrier entry, summarizes fix.
2. **Demo B — Gas smell (safety):** *"I'm smelling a strong rotten-egg smell near this gas furnace."* → fires `flag_safety` level=stop, red banner.
3. **Demo C — Scope change:** *"While I'm in here replacing the capacitor, the contactor looks pitted too."* → fires `log_finding` + `flag_scope_change` in one turn.

### Verify without the browser

```bash
# In one terminal:
cactus/venv/bin/python -m uvicorn src.main:app --host 127.0.0.1 --port 8000

# In another:
cactus/venv/bin/python tests/smoke_ws.py "Carrier 58STA intermittent cooling clicking"
```

### Run unit tests

```bash
cactus/venv/bin/python -m pytest tests/test_tools.py -v
```

## Measured performance

On MacBook Pro M4 Pro (CPU, no ANE):

| Metric | Value |
|---|---|
| Model load | ~5.8 s (one-time) |
| Time to first token | 217–233 ms |
| Decode speed | 28–29 tok/s |
| Confidence (text completions) | 0.97 |
| KB retrieval (10 entries) | <1 ms |

## Architecture

```text
Browser (Chrome)                        Mac M4 Pro (FastAPI + Cactus)
────────────────                        ────────────────────────────
[mic PCM16 LE]──┐                                ┌─→ cactus_complete ─→ Gemma 4 E4B
[camera 1fps]   ├── WebSocket ── /ws/session ────┤
[text input]────┘                                ├─→ HVACToolDispatcher
                                                 │    ├─ query_kb (kb/*.json)
[transcript]◄──── tokens + tool_call + session ──│    ├─ log_finding
[tool log]                                       │    ├─ flag_safety
[safety banner]                                  │    ├─ flag_scope_change
[findings counts]                                │    └─ close_job
[browser TTS speaks reply]                       │
```

One shared Cactus handle; per-session `FindingsStore` + conversation history; 3-pass tool-call loop so chained calls land in a single turn.

## Where the iPhone is

Abandoned for this hackathon. The Cactus iOS distribution (XCFramework / SPM) has open bugs that blocked the Swift path — not our Xcode config. The same Cactus binary ships for both platforms, so porting to iOS once the Apple SDK matures is a thin-client swap: replace the WebSocket with a Cactus Swift SDK call. The Swift scaffold (schemas, stores, views) is preserved at [archive/ios-abandoned/](archive/ios-abandoned/).

## Hackathon requirements

- [x] Uses **Gemma 4 on Cactus** (E4B variant, Cactus Python SDK)
- [x] Leverages **voice functionality** (browser mic → PCM16 → model; browser TTS speaks replies)
- [x] **Working MVP** — three demos verified end-to-end
- [ ] Demo video — record before submission

## Resources

- [Cactus Docs](https://docs.cactuscompute.com/latest/) · [Python SDK](https://docs.cactuscompute.com/latest/python/) · [Gemma 4 post](https://docs.cactuscompute.com/latest/blog/gemma4/)
- [Gemma 4 on DeepMind](https://deepmind.google/models/gemma/gemma-4/) · [model card](https://ai.google.dev/gemma/docs/core/model_card_4)
- [Pre-quantized weights](https://huggingface.co/cactus-compute)
- Internal: [Internal_docs/idea.md](Internal_docs/idea.md) (vision), [Internal_docs/build_plan.md](Internal_docs/build_plan.md) (hackathon plan, sections 5/7/11 are pre-pivot)

## License

MIT — see [LICENSE](LICENSE).
