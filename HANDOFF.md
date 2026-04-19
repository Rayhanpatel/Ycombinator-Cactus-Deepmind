# HVACCopilot iOS — Handoff to Teammate

**Branch:** `hvac-copilot`
**Date:** 2026-04-18
**Written by:** Rayhan (handing off the Xcode spike)

Read this top-to-bottom before touching anything. There is an **active blocker** you need to recover from first.

---

## 1. Immediate blocker — recover the Xcode target first

I accidentally deleted the app **target** inside Xcode (clicked the wrong `–` button under the TARGETS list instead of under the Link Binary list). Files on disk are fine. The `project.pbxproj` on disk has the damage in its unstaged modifications.

### Recovery steps

**Option A — Xcode Undo (try first, zero risk)**
If Xcode is still open on the machine: press ⌘Z repeatedly until the `HVACCopilot` target reappears in the TARGETS list on the right pane. Then ⌘S.

**Option B — Git restore (if Xcode is closed or Undo doesn't work)**

```bash
# 1. Make sure Xcode is fully closed (⌘Q, "Don't Save" if prompted)
# 2. Restore the pbxproj from the staged (good) version
git restore ios/scaffold/HVACCopilot/HVACCopilot/HVACCopilot.xcodeproj/project.pbxproj
# 3. Reopen Xcode
open ios/scaffold/HVACCopilot/HVACCopilot/HVACCopilot.xcodeproj
```

After recovery, verify:
- TARGETS list shows `HVACCopilot`
- Build Phases → Link Binary With Libraries has ~7 items including `libcactus-device.a` and (likely) `libcurl-device.a`

---

## 2. Current state of the project

### What's working
- Xcode project at [ios/scaffold/HVACCopilot/HVACCopilot/HVACCopilot.xcodeproj](ios/scaffold/HVACCopilot/HVACCopilot/HVACCopilot.xcodeproj)
- Cactus integrated via **static libs** (not SPM — cleaner for hackathon, no network/build-time dependency):
  - `libcactus-device.a` (6.4 MB)
  - `libcurl-device.a` (1.3 MB)
  - `cactus_ffi.h` — C FFI header
  - `module.modulemap` — exposes FFI as Swift module `cactus`
  - `Cactus.swift` — official Swift wrapper from Cactus SDK
- Build settings: `-lc++` in Other Linker Flags (Debug + Release) for C++ stdlib
- Scheme `GTFO` = Rayhan's iPhone 16 Pro (change to your own device)

### What's on disk but NOT in the Xcode target (you have to add these manually after recovery)
- [ios/scaffold/HVACCopilot/Shared/Schemas.swift](ios/scaffold/HVACCopilot/Shared/Schemas.swift) — **frozen contract** (SessionState, Message, Finding, Hypothesis, SafetyLevel)
- [ios/scaffold/HVACCopilot/Engine/CactusModel.swift](ios/scaffold/HVACCopilot/Engine/CactusModel.swift) — actor wrapping `cactusInit` + `cactusComplete`
- [ios/scaffold/HVACCopilot/Views/](ios/scaffold/HVACCopilot/Views/) — `OnSiteView`, `HUDOverlay`, `FindingsList`, `CloseJobView` (mock data wired)
- [ios/scaffold/HVACCopilot/Mocks/MockData.swift](ios/scaffold/HVACCopilot/Mocks/MockData.swift)

Compile Sources in Xcode currently has only 3 items (the default app files + `Cactus.swift`). After recovery, add the folders above to the target:

1. Right-click `HVACCopilot` group in Xcode Project Navigator
2. **Add Files to "HVACCopilot"…**
3. Select the four folders (`Shared/`, `Engine/`, `Views/`, `Mocks/`)
4. Options: "Create groups" selected, "Copy items if needed" **unchecked**
5. Target Membership: `HVACCopilot` ✓

### Known bug to fix before build
[ios/scaffold/HVACCopilot/Engine/CactusModel.swift:13](ios/scaffold/HVACCopilot/Engine/CactusModel.swift#L13) declares:
```swift
private var model: OpaquePointer?
```
But [ios/scaffold/HVACCopilot/HVACCopilot/Cactus.swift:4](ios/scaffold/HVACCopilot/HVACCopilot/Cactus.swift#L4) defines:
```swift
public typealias CactusModelT = UnsafeMutableRawPointer
```
Change line 13 to `private var model: UnsafeMutableRawPointer?`. Also the `guard isLoaded, let model = model else` in `complete()` needs matching type.

### What's NOT done yet
- `ContentView.swift` is still the default "Hello, world!" template — **no spike UI yet**
- Gemma 4 E4B model not bundled into app Resources (~4.5 GB, must be added as a **folder reference** — blue icon)
- No mic / camera capture wired
- No tool-call dispatcher
- Phone storage was 4.84 GB free — **needs ≥ 15 GB** before model can load on device. Offload Photos to iCloud first.

---

## 3. The plan — follow [Internal_docs/build_plan.md](Internal_docs/build_plan.md)

**Product:** HVAC Copilot — voice + vision field assistant for HVAC techs, 100% on-device via Gemma 4 E4B + Cactus.

**Demo (90s):** tech points iPhone at a failing unit, speaks the symptom, model coaches them through the fix, outputs structured resolution JSON at the end.

**3-person split:**
| Role | Owns |
|---|---|
| Brain (Person 1) | Swift spike, `CactusModel` wrapper, tool dispatch |
| Face (Person 2) | SwiftUI views, AVFoundation mic/camera |
| Domain (Person 3) | `shared/hvac_tools.json`, `kb/*.json`, demo scripts — no iOS deps |

**Gates:**
- T+2h: spike works on device (load model → text reply)
- T+4h: text end-to-end (prompt → tool call → tool result → UI)
- T+6h: multimodal (audio OR vision in real `cactusComplete` call)
- T+8h: backup demo video recorded

**Fallback if Swift spike fails:** Safari PWA on iPhone + FastAPI backend on Mac M4 Pro via LAN WebSocket. Python scaffold exists under [src/](src/). All UI/schemas/KB work ports cleanly.

---

## 4. Recommended next 30 min after target recovery

In this order:

1. **Fix the type mismatch** in `CactusModel.swift` (line 13 + line 48).
2. **Add source folders to target** — `Shared/`, `Engine/`, `Views/`, `Mocks/` (see section 2 above).
3. **Replace `ContentView.swift`** with a spike UI: one "Load Model" button, one text field, one "Send" button, one result label. Calls `CactusModel.shared.load()` then `completeText(...)`. This is the T+2h gate test.
4. **Build (without model yet)** — confirm everything compiles and the app launches on device with dummy UI. Load will fail (no model) — that's fine, it tells you the build chain is green.
5. **Bundle the Gemma 4 E4B model** — drag the model folder from `~/.cache/huggingface/` or wherever `cactus download` saved it into `ios/scaffold/HVACCopilot/HVACCopilot/Resources/models/gemma-4-E4B-it/` as a **folder reference** (blue folder icon, "Copy items if needed" unchecked — it's 4.5 GB, don't duplicate it).
6. **Run on device** — tap Load Model → wait ~30s → tap Send with "what is 2+2" → expect reply. **This is the Path A confirmation.**

---

## 5. File map

```
Ycombinator-Cactus-Deepmind/
├── HANDOFF.md                                  (this file)
├── Internal_docs/
│   └── build_plan.md                           (the plan — 16 sections, read sections 1–8)
├── ios/scaffold/HVACCopilot/
│   ├── HVACCopilot/                            (Xcode project root)
│   │   ├── HVACCopilot.xcodeproj/              (open this)
│   │   ├── HVACCopilot/                        (default app sources)
│   │   │   ├── HVACCopilotApp.swift
│   │   │   ├── ContentView.swift               (still default — needs spike UI)
│   │   │   └── Assets.xcassets/
│   │   ├── Cactus.swift                        (vendored from Cactus SDK)
│   │   ├── cactus_ffi.h
│   │   ├── module.modulemap
│   │   ├── libcactus-device.a
│   │   └── libcurl-device.a
│   ├── Shared/Schemas.swift                    (frozen contract — don't edit alone)
│   ├── Engine/CactusModel.swift                (needs type fix, line 13)
│   ├── Views/                                  (OnSite, HUD, Findings, CloseJob)
│   └── Mocks/MockData.swift
├── shared/
│   ├── hvac_tools.json                         (5 OpenAI-format tool schemas)
│   └── kb_schema.json
├── kb/                                         (3 entries so far, need 10 total)
└── demo/                                       (demo script 1 done; need 2 + 3)
```

---

## 6. Commands cheat-sheet

```bash
# switch to the branch
git checkout hvac-copilot

# check state
git status

# if Xcode damage happens again
git restore ios/scaffold/HVACCopilot/HVACCopilot/HVACCopilot.xcodeproj/project.pbxproj

# commit WIP
git add -A && git commit -m "wip: <what you did>"
git push origin hvac-copilot

# open Xcode project
open ios/scaffold/HVACCopilot/HVACCopilot/HVACCopilot.xcodeproj
```

---

## 7. Traps I already hit — don't repeat

1. **Wrong `–` button.** Under TARGETS and under Link Binary look similar. To remove a library row, **select the row and press Delete on the keyboard** — don't use the `–` at the bottom of the pane (too easy to click the wrong one).
2. **Simulator static libs.** I removed `libcactus-simulator.a` and `libcurl-simulator.a` because Xcode filter popover only offers OS platforms, not device-vs-simulator. Target is physical iPhone anyway — simulator has no Neural Engine, so Gemma wouldn't work there. You lose simulator builds; use SwiftUI Previews for UI work instead.
3. **Xcode filter dropdown only has iOS/macOS/visionOS checkboxes.** For device/simulator discrimination with static libs you need an `.xcframework` (Cactus didn't ship one). Workaround: just link device libs only.
4. **`-lc++` must stay.** Cactus internals are C++. Removing this will undefine ~hundreds of `std::` symbols. Keep it in Other Linker Flags for both Debug + Release.

---

## 8. Known risks

- Nobody on team has Swift experience — the AI pair-programmer (Claude) is writing all Swift. Paste verbatim, report errors verbatim.
- 4.5 GB model on 8 GB RAM iPhone 16 Pro is tight. Test early; if OOM, pivot to Path B (Mac backend + PWA) immediately — do not spend 2h debugging.
- Free Apple Developer tier = 7-day provisioning. Re-sign before the demo day if the build drifts past a week.

---

**When the target is back and it compiles, you're back on plan. Good luck.**
