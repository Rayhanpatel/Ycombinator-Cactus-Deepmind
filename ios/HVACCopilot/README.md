# HVACCopilot — iOS (Xcode Setup Guide)

This folder holds the Swift sources + resources for the iOS app.

**The Xcode project itself (`HVACCopilot.xcodeproj`) is not committed — Person 1 (Xcode Driver) creates it in Xcode on first run and drags these files in.**

## Person 1 — Xcode project setup (do this once, ~15 min)

### 1. Create the project
- Open **Xcode 15+**
- File → New → Project → **iOS** → **App**
- Product Name: `HVACCopilot`
- Team: your Apple ID (free tier works)
- Organization Identifier: `com.hvaccopilot`
- Interface: **SwiftUI**
- Language: **Swift**
- Storage: None
- Minimum Deployment: **iOS 17.0**
- Save location: `ios/HVACCopilot_Xcode/` (inside this repo, gitignored below)

### 2. Add Cactus via Swift Package Manager
- File → Add Package Dependencies
- Paste URL: `https://github.com/cactus-compute/cactus`
- Dependency Rule: **Up to Next Major Version** from `1.0.0`
- Add to target: `HVACCopilot`

### 3. Import our source files into the Xcode project
Right-click the `HVACCopilot` group in Xcode's Project Navigator → **Add Files to "HVACCopilot"…** → select these folders from `ios/HVACCopilot/HVACCopilot/`:
- `Shared/` (contains `Schemas.swift` — the frozen contract)
- `Engine/` (contains `CactusModel.swift`)
- `Views/` (contains `OnSiteView.swift`, `HUDOverlay.swift`, `FindingsList.swift`, `CloseJobView.swift`)
- `Mocks/` (contains `MockData.swift`)

Ensure "Create groups" is selected and "Copy items if needed" is **unchecked** (we want the Xcode project to reference files in-place so git tracks edits).

Also replace the default `HVACCopilotApp.swift` and `ContentView.swift` Xcode created with the versions from this folder.

### 4. Add the Gemma 4 E4B model as a bundle resource
- On the Mac, the Gemma 4 folder is already downloaded (from `test_gemma4.py` runs). Locate it under `~/.cache/huggingface/hub/models--google--gemma-4-E4B-it/snapshots/<hash>/` or wherever Cactus CLI saved it.
- Copy the model folder into `ios/HVACCopilot/HVACCopilot/Resources/models/gemma-4-E4B-it/`
- In Xcode: right-click `Resources` group → Add Files → pick `models/gemma-4-E4B-it/` → Add as **folder reference** (blue folder icon, not yellow group)
- Confirm "Copy items if needed" is **unchecked** (avoid duplicating 4.5 GB)
- Target Membership: check `HVACCopilot`

This folder is in `.gitignore` — each teammate copies the model locally.

### 5. Info.plist permissions (for T+4h when we wire mic/camera)
Open the target → Info tab → add:
- `NSMicrophoneUsageDescription` → "HVAC Copilot listens for voice commands on-site"
- `NSCameraUsageDescription` → "HVAC Copilot analyzes equipment via camera"

### 6. Enable device deployment
- Plug in iPhone 16 Pro
- Xcode top bar → select your device (not simulator — simulator has no ANE)
- Settings on iPhone → Privacy & Security → Developer Mode → On → restart
- First build will prompt to trust the developer certificate: iPhone Settings → General → VPN & Device Management → trust the cert

### 7. Run the spike
- Cmd+R
- App launches, shows a "Load Model" button → tap it → shows "Loaded ✓"
- Text field + Send button → type "what is 2+2" → model replies
- **This is the T+2h gate.** If this works, Path A is green.

## Person 2 — SwiftUI Integrator setup
- Install Xcode (if not already). Once Person 1 has the project running, pull the branch; the project will open in Xcode. Work on `Views/` — mock data is in `Mocks/MockData.swift`. Use SwiftUI previews (Canvas) — no device needed for UI iteration.

## Person 3 — Domain (no iOS tools required)
- Work in `shared/`, `kb/`, `demo/` at the repo root. Python + JSON + markdown only.

## Common errors + fixes

| Error | Fix |
|---|---|
| `No such module 'Cactus'` | SPM didn't resolve. File → Packages → Reset Package Caches |
| `cactusInit failed: model not found` | Model folder not added to bundle, or path resolution failed. See `CactusModel.swift` path logic |
| `Code signing error` | Xcode → target → Signing & Capabilities → select your Personal Team |
| `Untrusted Developer` on iPhone | iPhone Settings → General → VPN & Device Management → trust |
| App crashes on launch (OOM) | Model too big for device RAM. Check free storage + quit other apps |
