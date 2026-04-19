# iOS scaffold — retired 2026-04-18

Abandoned when the Cactus iOS distribution proved too brittle for a
hackathon timeline: the XCFramework / SPM story has open bugs, the
static-lib drop-in leaves subtle link-time gaps (`-lc++` required,
device-vs-simulator arch filtering is coarse), and the Swift wiring
around `cactus_ffi.h` hit opaque-pointer / raw-pointer type mismatches
that took too long to unwind.

The **product** was sound — what stalled was the toolchain.

## What's in here (preserved for reference)

- [scaffold/HVACCopilot/HVACCopilot/HVACCopilot/Shared/Schemas.swift](scaffold/HVACCopilot/HVACCopilot/HVACCopilot/Shared/Schemas.swift) — frozen domain types (SessionState, Message, Finding, Hypothesis, SafetyLevel, KBEntry, ScopeChange, JobClosure). Mirrors [shared/hvac_tools.json](../../shared/hvac_tools.json).
- [scaffold/HVACCopilot/HVACCopilot/HVACCopilot/Engine/](scaffold/HVACCopilot/HVACCopilot/HVACCopilot/Engine/) — Swift `CactusModel`, `KBStore`, `FindingsStore`, `ToolDispatcher`. Algorithms match the active Python implementations in [src/kb_store.py](../../src/kb_store.py), [src/findings_store.py](../../src/findings_store.py), [src/tools.py](../../src/tools.py).
- [scaffold/HVACCopilot/HVACCopilot/HVACCopilot/Views/](scaffold/HVACCopilot/HVACCopilot/HVACCopilot/Views/) — `OnSiteView`, `HUDOverlay`, `FindingsList`, `CloseJobView`. Wired to mock data. Useful reference for a real Swift port.
- [scaffold/HVACCopilot/HVACCopilot/](scaffold/HVACCopilot/HVACCopilot/) — Cactus static libs (`libcactus-device.a`, `libcurl-device.a`, `cactus_ffi.h`, `module.modulemap`, vendored `Cactus.swift`) + Xcode project.

## Active build

Mac web app on branch `mac-webapp`: Python FastAPI (`src/main.py`) +
browser UI (`web/`) using the same Cactus binary via the Python SDK
(which is mature). See [../../README.md](../../README.md).

## If Cactus iOS stabilizes

Revisit the failure map in [../../HANDOFF_IOS_LEGACY.md](../../HANDOFF_IOS_LEGACY.md) before
starting — the gotchas section documents specific edges that cost us time.
