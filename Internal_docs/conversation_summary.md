# Hackathon Project Recap & Strategic Summary

## 1. Project Inception & Goal
- **Objective:** Build a competitive voice/multimodal AI agent for the YCombinator x Cactus x DeepMind Hackathon.
- **Hardware Profile:** targeting execution on an M4 Pro Mac and iPhone 16 Pro.
- **Model Selected:** `Gemma 4 E4B` to utilize on-device multimodal inference (text, audio, vision) via the Cactus SDK.

## 2. Initial Strategy vs. Revised Strategy
- **Initial Plan (Abandoned):** Build a native iOS shell application using SwiftUI and the Cactus Apple XCFramework. The plan included detailed phases for Objective-C/Swift bindings, audio/camera pipelines, a SwiftUI interface, and tool calling frameworks.
- **The Pivot:** After critical evaluation, we determined that building a native iOS app from scratch is high-risk for a hackathon timeframe—especially given the challenge of loading and managing a 3-4GB model weight file on an iPhone. Furthermore, the hackathon documentation strongly leans toward the Python SDK. 
- **Current Plan (Approved):** Execute the MVP as a Python backend running locally on the M4 Pro, paired with a web UI (Vite + React) that accesses the device's microphone and camera. This leverages our existing Python scaffolding, takes advantage of the M4 Pro's superior inference speed, and guarantees a working, stable demo within hours.

## 3. Past Hackathon Analysis
We conducted a deep dive into 7 previous Cactus hackathon projects (including finalists like FatBoss, Mingle, and TrailSense) to uncover winning patterns:
- **Winning Patterns:** The top teams built *real product wrappers* (full-stack web portals, mobile apps) around the AI, integrated with real-world APIs (WhatsApp, Linear, SQLite), and implemented deterministic, pre-baked demo scenarios to ensure a flawless pitch.
- **The Architectural Commonality:** Every project used the exact same Python hybrid routing pattern: `FunctionGemma 270M (On-Device)` -> `Confidence/Structural Gate` -> `Gemini Cloud (Fallback)`.
- **Our "Unfair Advantage":** Previous teams only had access to text-based FunctionGemma. We have **Gemma 4**, which introduces native multimodal capabilities. It can ingest raw audio (skipping a separate Whisper STT layer) and raw vision frames in a single pass. Our product must heavily feature these voice-in and vision-in capabilities to stand out.

## 4. Proposed Product Concept: VoiceSight
Based on our analysis, we drafted a strong potential product concept: **VoiceSight — On-Device Field Inspector**.
- **Use Case:** Designed for construction inspectors or insurance adjusters. The user points their camera at damage and speaks notes (e.g., *"I see water damage on the north wall, approximately 3 feet wide, severity high"*). The agent natively processes the image and voice to instantly generate a structured JSON report entry.
- **Value Prop:** 100% on-device execution (ensuring complete privacy and regulatory compliance data retention), zero cloud latency, and utilizing Gemma 4's unique capabilities. Note: If the team has a different domain expertise, this core voice+vision loop can be mapped to any other industry.

## 5. Technical Execution & SDK Setup
We successfully provisioned the M4 Pro development environment and validated the Cactus SDK:
1.  **Cactus SDK:** Cloned the Cactus repository and initialized the environment. Resolved minor `$PATH` issues to locate Homebrew's Python 3.12 installation.
2.  **Compilation:** Built the Cactus Python bindings (`cactus build --python`), compiling the underlying C++ kernels into `libcactus.dylib`.
3.  **Authentication & Download:** Authenticated via the Cactus CLI and successfully downloaded the ~6.4GB `google/gemma-4-E4B-it` weights.
4.  **Inference Testing:** Successfully ran a text completion test (`test_gemma4.py`).
    - *Performance Metrics:* Model loaded in ~7s; Time-to-first-token (TTFT) was an impressive ~217ms; Decode speed hit ~28 tok/s; Confidence was 0.97.
5.  **NPU vs. CPU Troubleshooting:** 
    - We received warnings stating `model.mlpackage not found; using CPU prefill`. This means the model is running on the Mac's CPU instead of the Apple Neural Engine (ANE/NPU).
    - Attempts to compile the Apple SDK (`cactus build --apple`) explicitly for the NPU failed due to iOS SDK/Xcode license configuration issues.
    - Attempts to force the generation of `model.mlpackage` via `--reconvert` required a HuggingFace User Token (as the Gemma 4 base weights are gated) and would have triggered a lengthy download+compile process.
    - **Strategic Conclusion:** The CPU performance on the M4 Pro (217ms TTFT, 28 tok/s) is already exceptional and more than fast enough for a hackathon MVP. We elected to proceed with CPU inference to prioritize actual product development over chasing minor infrastructure optimizations.

## 6. Development Roadmap & Next Steps
1.  **Finalize Product Domain:** Decide if we are building VoiceSight or an alternative concept utilizing the voice+vision+text tool loop.
2.  **Model Integration:** Adapt the existing `src/cactus_engine.py` wrapper to invoke `cactus_complete` by passing raw PCM audio buffers and camera frame images in the context payload.
3.  **Tool Construction:** Implement 3-5 deterministic, domain-specific Python tools (e.g., `log_finding`, `generate_pdf_report`).
4.  **Frontend MVP:** Spin up the Vite+React application to provide access to the browser's `navigator.mediaDevices` (mic/webcam) and stream the data to our Python backend endpoints.
5.  **Pre-bake Demos:** Create 3 specific interaction scenarios that are guaranteed to work for the final presentation.
