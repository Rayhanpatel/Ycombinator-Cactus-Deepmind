# iOS SwiftUI UI scaffold (archived)

> Frozen snapshot of the `tash-2s/main` branch (origin/tash-2s/main at archival).
> Preserved as reference for a future iOS port. **Do not try to build this today.**

## What this is

A standalone SwiftUI Xcode project authored by teammate **tash-2s** during the
hackathon, intended as the front-end for a native iOS port of HVAC Copilot.
Complete visual system — theme, chat bubbles, safety banner, voice input bar,
scenario picker, findings badges, etc.

Tree:

```
ui/
├── ui.xcodeproj/                 Xcode project
└── ui/
    ├── uiApp.swift               app entry point
    ├── ContentView.swift         root view
    ├── Theme/AppTheme.swift      dark theme + accessibility
    ├── Screens/
    │   ├── OnSiteView.swift
    │   ├── ScenarioPickerView.swift
    │   └── CloseJobView.swift
    ├── Components/               (11 reusable SwiftUI components)
    │   ├── CameraPlaceholderView.swift
    │   ├── ChatBubbleView.swift
    │   ├── ChatTimeline.swift
    │   ├── CoachingCard.swift
    │   ├── FindingBadge.swift
    │   ├── HypothesisCard.swift
    │   ├── SafetyBanner.swift
    │   ├── ToolCallBadge.swift
    │   ├── TopStatusBar.swift
    │   └── VoiceInputBar.swift
    └── PreviewData/MockSession.swift   mock data for Xcode previews
```

## Why it was retired

The iOS path required Cactus's Apple XCFramework + Swift FFI. During the
hackathon we hit open bugs in the static-lib link and pointer-type wiring
that we couldn't unblock in the time we had. See `HANDOFF_IOS_LEGACY.md §12`
on the live branch for specifics.

A separate iOS scaffold with a partial Cactus actor (`CactusModel`, tool
dispatcher, KB store, findings store) lives at `archive/ios-abandoned/`.
**That** scaffold is the Cactus wiring; **this** folder is the UI layer
that would sit on top of it.

## When to resume

Only after:

1. Cactus publishes a stable Apple SDK (XCFramework or SPM) with working
   Swift FFI for Gemma 4. Track: `https://docs.cactuscompute.com/latest/`.
2. `archive/ios-abandoned/` builds end-to-end on physical iPhone hardware.

At that point, the thin-client swap is: replace `archive/ios-abandoned/`'s
`URLSessionWebSocketTask` calls with direct `CactusModel.completeText` calls,
and drop these SwiftUI components in as the view layer.

## Do not edit files here

This is a frozen reference copy. Any new iOS work should happen on a new
branch, using these files as templates — not modifying them in place.
