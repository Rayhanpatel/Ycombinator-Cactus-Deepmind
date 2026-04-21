# HVACCopilot iOS — Handoff (LEGACY, iOS path retired)

> **⚠️ Retired 2026-04-18.** The iOS path was abandoned after we hit open
> bugs in the Cactus iOS distribution (XCFramework / SPM wiring, static-lib
> link edge cases). Active build is a Mac web app — see `README.md` and
> the live plan at `~/.claude/plans/ok-think-and-revamp-prancy-spring.md`.
> The iOS scaffold lives at `archive/ios-abandoned/` on branch `mac-webapp`.
>
> This file is preserved because the gotchas section and domain notes are
> still useful reference if the Cactus Apple SDK matures and someone retries.
> **Do not follow the Xcode steps below as if they were current.** The
> step-by-step is time-capsuled for context only.

---

**Branch:** `hvac-copilot` (iOS-committed reference) · active branch: `mac-webapp`
**Last updated:** 2026-04-18
**Written by:** Rayhan (+ Claude as pair programmer)

Read this top-to-bottom before touching anything. Current state is **code-complete on all platform-independent work**. What's left is hands-on Xcode time + device testing.

---

## 1. Where we are right now

### Done ✓

**Domain (pure data — `/kb`, `/demo`, `/shared`):**
- 5 tool schemas frozen in `shared/hvac_tools.json` (query_kb, log_finding, flag_safety, flag_scope_change, close_job)
- 10 KB entries under `kb/` covering Carrier / Trane / Lennox / Goodman / Rheem / York / American Standard / Bryant / Mitsubishi / generic-gas-furnace-safety
- 3 demo scripts under `demo/` (happy path capacitor, safety gas-smell interrupt, scope change)

**iOS scaffold (all Swift under `ios/scaffold/HVACCopilot/HVACCopilot/HVACCopilot/`):**
- `Shared/Schemas.swift` — frozen types (SessionState, Message, Finding, Hypothesis, SafetyLevel, KBEntry, ScopeChange, JobClosure, AnyCodable)
- `Engine/CactusModel.swift` — actor wrapping `cactusInit` + `cactusComplete`
- `Engine/KBStore.swift` — loads KB JSON from bundle, keyword-scored search
- `Engine/FindingsStore.swift` — `@MainActor` observable session store
- `Engine/ToolDispatcher.swift` — parses Cactus tool_calls and runs all 5 handlers
- `Views/` — `OnSiteView`, `HUDOverlay`, `FindingsList`, `CloseJobView` (wired to MockData for now)
- `Mocks/MockData.swift`
- `ContentView.swift` — spike UI (Load Model → prompt → response)

**Xcode project plumbing (`HVACCopilot.xcodeproj`):**
- Cactus integrated as **static libs** (not SPM): `libcactus-device.a` + `libcurl-device.a` + `cactus_ffi.h` + `module.modulemap` + vendored `Cactus.swift`
- `-lc++` set in Other Linker Flags (Debug + Release)
- Link Binary With Libraries configured with the right frameworks

### Not done ✗

- **Source folders not added to Xcode target yet** — `Shared/`, `Engine/`, `Views/`, `Mocks/` live on disk next to `ContentView.swift` but aren't in Compile Sources. See section 3 step A.
- **Gemma 4 E4B not bundled** — ~4.5 GB folder needs to go into `Resources/` as a blue folder reference. See section 3 step C.
- **`kb/` folder not bundled** — KBStore looks for it in Bundle.main; add as blue folder reference. See section 3 step D.
- **Mic capture (AVAudioEngine) not written** — deferred until spike passes.
- **Camera capture (AVCaptureSession) not written** — deferred until spike passes.
- **Views not wired to real stores** — still using MockData. Easy swap once spike passes.
- **Phone storage** — iPhone had 4.84 GB free. Need ≥15 GB. Offload Photos to iCloud before installing.

---

## 2. Commit trail on `hvac-copilot` (most recent first)

```
e212595 feat(ios): tool dispatcher, KB store, findings store
88f14c8 feat(domain): 7 more KB entries + demo scripts 2 & 3
20d915c feat(ios): spike ContentView — load Gemma 4 + text prompt round-trip
bedb257 fix(ios): CactusModel pointer type matches Cactus FFI (UnsafeMutableRawPointer)
cf7354b refactor(ios): move Swift sources into Xcode project folder
36661e4 docs(handoff): Xcode project state + recovery steps for teammate
b37c98d chore: gitignore ios/HVACCopilot/ (Xcode-generated project folder)
00a0b4c refactor(ios): move scaffold from ios/HVACCopilot → ios/scaffold
```

Each commit is a clean revert point.

---

## 3. What to do next — step by step

### Step A — Add our Swift folders to the Xcode target (3 min)

1. `open ios/scaffold/HVACCopilot/HVACCopilot/HVACCopilot.xcodeproj`
2. In Project Navigator (left), right-click the **HVACCopilot** yellow group (inner one, under the blue project icon)
3. **Add Files to "HVACCopilot"…**
4. Navigate into `HVACCopilot/HVACCopilot/HVACCopilot/`
5. ⌘-click to select: **Engine**, **Mocks**, **Shared**, **Views**
6. Options: **Create groups** ✓, **Copy items if needed** ✗, Target Membership: **HVACCopilot** ✓
7. **Add**

### Step B — First build (no model yet)

⌘⇧K then ⌘B.

Expected: **Build Succeeded** with zero errors. This confirms:
- Static-lib linking works
- `-lc++` is set correctly
- All Swift files compile together
- Cactus module is importable

If there are errors, they'll be in `CactusModel.swift`, `ToolDispatcher.swift`, or `KBStore.swift` referencing types from `Schemas.swift`. Confirm those four files are in Compile Sources.

### Step C — Bundle the Gemma 4 E4B model (~10 min)

1. Locate the model folder on your Mac (downloaded by `tests/smoke_gemma4.py` or the Cactus CLI). Typical paths:
   - `~/.cache/huggingface/hub/models--google--gemma-4-E4B-it/snapshots/<hash>/`
   - Or wherever `cactus download` saved it.
2. In Xcode, create a **Resources** group (right-click HVACCopilot group → New Group → name it `Resources`). On disk, this should map to `HVACCopilot/HVACCopilot/Resources/`.
3. Drag the model folder from Finder into the `Resources` group in Xcode.
4. Options: **Create folder references** (BLUE folder icon — NOT yellow group), **Copy items if needed** ✗ (do NOT duplicate 4.5 GB), Target Membership: **HVACCopilot** ✓.
5. After drop, confirm the folder shows with a blue icon in the navigator.

Xcode will include this as a resource and `Bundle.main.path(forResource: "gemma-4-E4B-it", ofType: nil)` will resolve.

### Step D — Bundle the KB folder (~1 min)

Same pattern as the model, much smaller file.

1. In Finder, locate `kb/` at the repo root.
2. Drag the `kb` folder into the `Resources` group in Xcode (or next to it).
3. Options: **Create folder references** (blue icon), **Copy items if needed** ✗, Target Membership: **HVACCopilot** ✓.

### Step E — Phone storage (~30 min, do this while Step C drags)

Target: 15 GB free on the iPhone 16 Pro.

- Settings → General → iPhone Storage → shows what's consuming space
- Photos: Settings → Photos → iCloud Photos → **Optimize iPhone Storage** (frees most)
- Or AirDrop video library to the Mac and delete from phone

### Step F — Run on device

1. Plug in iPhone 16 Pro
2. Developer Mode: Settings → Privacy & Security → Developer Mode → On → restart
3. Xcode top bar: select your iPhone as destination
4. ⌘R
5. First run: iPhone will show "Untrusted Developer" — Settings → General → VPN & Device Management → trust the cert
6. App launches → tap **Load Gemma 4 E4B** → wait ~30s → expect "Loaded ✓"
7. Type "what is 2+2" → tap **Send** → expect a reply

**This is the T+2h gate.** If it works, Path A is confirmed.

---

## 4. If the spike fails at Step F

Three failure shapes, each with a different next move:

### (a) Build error at Step B / C
Fix the code, not the plan. Paste error into chat, fix, retry.

### (b) `cactusInit` throws "Failed to initialize model"
- Model folder probably not in bundle. Check Build Phases → Copy Bundle Resources — folder should be listed.
- Or the folder-reference added as yellow group (not blue) — delete and re-add as folder reference.

### (c) App launches, model loads, but reply is gibberish or OOM kills the app
- iPhone 16 Pro has 8 GB RAM. Gemma 4 E4B is ~4.5 GB. Tight but possible.
- Quit all other apps. Retry.
- If consistent OOM → pivot to **Path B (Mac backend)** immediately. Don't spend 2h debugging.

### Path B pivot (Mac backend, ~2h)
- FastAPI server on Mac M4 Pro using existing `src/` scaffold
- SwiftUI app replaces `CactusModel.completeText` call with `URLSessionWebSocketTask` to `ws://<mac-lan-ip>:8000`
- Same views, same schemas, same KB — only the inference boundary moves
- Story for judges: "Cactus ships the same Gemma 4 as an iOS XCFramework; production moves it on-device."

---

## 5. File map

```
Ycombinator-Cactus-Deepmind/
├── HANDOFF.md                                     ← this file
├── Internal_docs/
│   └── build_plan.md                              ← the plan, 16 sections
├── shared/
│   ├── hvac_tools.json                            ← 5 tool schemas (OpenAI format)
│   └── kb_schema.json
├── kb/                                            ← 10 entries, bundle as folder ref
│   ├── carrier_58sta_capacitor.json
│   ├── trane_xr14_contactor.json
│   ├── lennox_ml180_ignitor.json
│   ├── goodman_gsx14_low_refrigerant.json
│   ├── rheem_ra14_breaker_trip.json
│   ├── york_ycd_condensate_clog.json
│   ├── american_standard_silver14_compressor_relay.json
│   ├── bryant_123a_fan_limit_switch.json
│   ├── mitsubishi_minisplit_comm_fault.json
│   └── generic_gas_furnace_gas_smell.json
├── demo/
│   ├── script_1_capacitor.md                      ← happy path, 2.5 min
│   ├── script_2_safety_gas.md                     ← safety interrupt, 30s
│   └── script_3_scope_change_contactor.md         ← B2B insight, 40s
└── ios/scaffold/HVACCopilot/HVACCopilot/          ← Xcode project root
    ├── HVACCopilot.xcodeproj
    ├── HVACCopilot/                               ← app sources (Xcode group)
    │   ├── HVACCopilotApp.swift
    │   ├── ContentView.swift                      ← spike UI
    │   ├── Assets.xcassets
    │   ├── Shared/Schemas.swift                   ← frozen contract
    │   ├── Engine/
    │   │   ├── CactusModel.swift
    │   │   ├── KBStore.swift
    │   │   ├── FindingsStore.swift
    │   │   └── ToolDispatcher.swift
    │   ├── Views/                                 ← 4 mock views
    │   └── Mocks/MockData.swift
    ├── Cactus.swift                               ← vendored Cactus SDK wrapper
    ├── cactus_ffi.h
    ├── module.modulemap
    ├── libcactus-device.a                         ← iPhone device only
    ├── libcactus-simulator.a                      ← on disk, not linked
    ├── libcurl-device.a                           ← iPhone device only
    └── libcurl-simulator.a                        ← on disk, not linked
```

---

## 6. Gotchas I hit — don't repeat

1. **Wrong `–` button in Xcode.** TARGETS pane and Link Binary pane both have minus buttons at the bottom. Clicking the wrong one deletes the target. To remove a library, **click the row and press Delete on the keyboard** instead.
2. **Static lib arch filtering.** Xcode's Filter popover only has iOS/macOS/visionOS checkboxes — no Device-vs-Simulator. We dropped the simulator `.a` files from Link Binary because the target is physical iPhone. Simulator has no Neural Engine anyway.
3. **`-lc++` is required.** Cactus internals are C++. Without this flag, you get hundreds of `std::` undefined symbols.
4. **Folder reference vs Group.** Blue icon = folder reference (whole folder tree is bundled verbatim; use for model + kb). Yellow icon = Xcode group (individual files in target). Wrong choice = files not found at runtime.
5. **`OpaquePointer` ≠ `UnsafeMutableRawPointer`.** The Cactus FFI typealiases to `UnsafeMutableRawPointer`. Our `CactusModel` used to use `OpaquePointer` and wouldn't compile — now fixed in commit `bedb257`.

---

## 7. Known risks

- **Nobody on team has Swift experience.** Claude (AI pair programmer) writes all Swift. Paste verbatim, report errors verbatim.
- **4.5 GB model on 8 GB iPhone 16 Pro RAM.** Tight. Test early. If OOM, pivot to Path B.
- **Free Apple Developer tier = 7-day provisioning.** Re-sign before demo if more than a week passes between build and demo.
- **No one has run Gemma 4 on iPhone ANE in this repo yet.** Our Python tests hit CPU only. First on-device run is the real truth test.

---

**Current instruction: do Step A (3 min) and report the Build output. Everything else flows from there.**
