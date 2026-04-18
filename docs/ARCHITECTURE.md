# Architecture

## High-Level Overview

```
┌───────────────────────────────────────────────────────────────┐
│                     VOICE AGENT                                │
│                                                                │
│  ┌─────────────┐   ┌──────────────────┐   ┌───────────────┐ │
│  │ VoiceHandler │──▶│  CactusEngine    │──▶│     Tools     │ │
│  │             │   │  (Gemma 4 E2B)   │   │  (Functions)  │ │
│  │  • Record   │   │                  │   │  • Weather    │ │
│  │  • VAD      │   │  • complete()    │   │  • Calendar   │ │
│  │  • Playback │   │  • transcribe()  │   │  • Custom...  │ │
│  └─────────────┘   │  • audio_compl() │   └───────────────┘ │
│                    └────────┬─────────┘                      │
│                             │                                 │
│                    ┌────────▼─────────┐                      │
│                    │  CloudFallback   │                      │
│                    │  (Gemini 2.5)    │                      │
│                    │                  │                      │
│                    │  Auto-routes     │                      │
│                    │  when confidence │                      │
│                    │  is low          │                      │
│                    └──────────────────┘                      │
└───────────────────────────────────────────────────────────────┘
```

## Component Breakdown

### 1. `src/agent.py` — Orchestrator
- Main entry point
- Interactive CLI loop
- Routes between voice/text input
- Manages conversation state

### 2. `src/cactus_engine.py` — On-Device AI Engine
- Wraps the Cactus Python FFI
- Model lifecycle (init, complete, destroy)
- Chat completion with tool support
- Native audio processing (Gemma 4 multimodal)
- Transcription via Whisper/Parakeet

### 3. `src/voice_handler.py` — Audio I/O
- Microphone recording
- Voice Activity Detection (silence detection)
- Audio file I/O (WAV)
- PCM conversion for Cactus FFI

### 4. `src/cloud_fallback.py` — Cloud Routing
- Gemini API integration
- Confidence-based handoff decisions
- Cactus also has built-in cloud handoff (via `cactus auth`)

### 5. `src/tools.py` — Function Calling
- Tool schema definitions (OpenAI-compatible)
- Tool execution engine
- Dynamic tool registration
- Result formatting for conversation turns

### 6. `src/config.py` — Configuration
- Environment variable loading (.env)
- Typed configuration with defaults
- Validation for required keys

## Inference Flow

```
1. User speaks → VoiceHandler captures audio
2. Audio → CactusEngine.complete_with_audio()
   └─ Gemma 4 processes audio natively (no separate ASR step)
   └─ 0.3s to first token on ARM
3. If function calls detected → Tools.execute_tool()
   └─ Results fed back for follow-up response
4. If confidence < threshold → CloudFallback.query()
   └─ Routes to Gemini for complex reasoning
5. Response → displayed (or spoken via TTS)
```

## Model Selection Guide

| Model | Size | Use Case | Speed |
|-------|------|----------|-------|
| Gemma 4 E2B | 2.3B effective | Main LLM (fast) | ~40 tok/s |
| Gemma 4 E4B | 4.5B effective | Main LLM (smarter) | ~25 tok/s |
| FunctionGemma 270M | 270M | Function call routing | ~100 tok/s |
| Whisper Small | 244M | Transcription | Real-time |

## Key Design Decisions

1. **Native audio over ASR pipeline**: Gemma 4 processes audio directly instead of transcribe→then→reason, cutting latency from ~1s to ~0.3s.

2. **Dual cloud strategy**: Cactus built-in handoff (when model detects it can't handle the task) + explicit confidence-based fallback (for fine-grained control).

3. **Pluggable tools**: New tools can be added at runtime via `register_tool()` without modifying the core agent.
