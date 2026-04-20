# voice-sight — multimodal backend spike (archived)

> Frozen snapshot of the `voice-sight` branch (origin/voice-sight, tip `d50b995` at archival).
> Extracted here for reference. **Not on the live path.**

## What this was

A spike at a different multimodal architecture: feed Gemma 4 a single combined
prompt containing raw PCM audio + a base64-encoded camera frame in one call,
backed by an SQLite-persisted findings store. Authored by Rayhan, pre-dating
the mac-webapp path.

The extracted files:

- `cactus_engine_multimodal.py` — `CactusEngine.complete_multimodal(pcm_data, base64_image)`
  method that calls Gemma 4 with inline audio + image in one round-trip.
- `tools_sqlite.py` — functional HVAC tools (`log_finding`, `get_current_findings`,
  `generate_inspection_report`) backed by a SQLite table.

## Why it's not on the live path

The live path (`src/`) chose a different architecture:

1. **Multimodal via file paths, not inline base64.** `src/main.py` writes the
   camera keyframe to a temp JPEG and passes the path to Cactus. This avoids
   re-encoding PCM audio per turn and lets Gemma 4's existing image-tokeniser
   do the work. Inline base64 would inflate the prompt by ~1.3× and slow TTFT.
2. **No SQLite dependency.** `src/findings_store.py` keeps findings in an
   in-memory per-session dict. Easier to debug, no migrations, and findings
   naturally die with the session — which is what an HVAC job wants.
3. **Keeps the tool dispatcher class-based.** `src/tools.py` implements a
   `HVACToolDispatcher` that matches the `shared/hvac_tools.json` schema.
   Easier to extend with new tools without touching the DB layer.

See `HANDOFF.md §14` on the live branch for the full decision rationale.

## If you want to revive this approach

The live `src/cactus_engine.py` has a signature hook for where `complete_multimodal`
would slot in. The inline-base64 path is worth revisiting if you hit a case where
file-path images lose fidelity — e.g. tiny label text at the edge of the frame.

## Don't import from here

The files in this folder are **archived source**. They are not on the Python
path and are not tested. If you want to reuse logic, copy it into `src/` and
update imports.
