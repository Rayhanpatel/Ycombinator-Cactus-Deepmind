# 🌵 Cactus x Google DeepMind x Y Combinator — Voice Agent Hackathon

> **Gemma 4 Voice Agents** — Building the future of on-device AI voice interaction

[![Cactus](https://img.shields.io/badge/Powered_by-Cactus-green)](https://cactuscompute.com)
[![Gemma 4](https://img.shields.io/badge/Model-Gemma_4-blue)](https://ai.google.dev/gemma)
[![Python](https://img.shields.io/badge/Python-3.10+-yellow)](https://python.org)

---

## 🏗️ Project Overview

**[TODO: Replace with your project name and one-liner]**

A voice-powered agent built on Gemma 4 (via Cactus) that [describe what your product does]. 

### Key Features
- 🎤 **Voice-first interaction** — Natural voice input/output using Gemma 4's native audio understanding
- 🧠 **On-device inference** — Sub-300ms latency with Cactus Engine on ARM
- ☁️ **Smart cloud handoff** — Automatically routes complex tasks to Gemini when needed  
- 🔧 **Function calling** — Tool-use via FunctionGemma for real-world actions
- 🔒 **Privacy-first** — Audio never leaves the device for simple queries

---

## 📁 Project Structure

```
├── src/
│   ├── __init__.py
│   ├── agent.py              # Main voice agent orchestrator
│   ├── voice_handler.py      # Voice I/O (recording, playback, VAD)
│   ├── cactus_engine.py      # Cactus SDK wrapper (init, complete, transcribe)
│   ├── cloud_fallback.py     # Gemini cloud handoff logic
│   ├── tools.py              # Function/tool definitions for the agent
│   └── config.py             # Configuration and environment variables
├── tests/
│   ├── test_agent.py
│   ├── test_cactus_engine.py
│   └── test_tools.py
├── scripts/
│   ├── setup_cactus.sh       # One-click Cactus SDK setup
│   └── download_models.sh    # Download required model weights
├── docs/
│   └── ARCHITECTURE.md       # Technical architecture documentation
├── .env.example              # Environment variable template
├── .gitignore
├── requirements.txt
└── README.md
```

---

## 🚀 Quick Setup

### Prerequisites
- macOS (Apple Silicon recommended) or Linux (ARM64)
- Python 3.10+
- Git, CMake

### 1. Clone & Install

```bash
git clone https://github.com/<your-org>/Ycombinator-Cactus-Deepmind.git
cd Ycombinator-Cactus-Deepmind
```

### 2. Set Up Cactus SDK

```bash
chmod +x scripts/setup_cactus.sh
./scripts/setup_cactus.sh
```

This will:
- Clone the Cactus repo
- Run `source ./setup` to build the SDK
- Build the Python bindings with `cactus build --python`

### 3. Download Models

```bash
chmod +x scripts/download_models.sh
./scripts/download_models.sh
```

### 4. Configure API Keys

```bash
cp .env.example .env
# Edit .env with your keys
```

```bash
# Authenticate with Cactus
cactus auth
# Enter your Cactus API key when prompted

# Set Gemini API key (for cloud fallback)
export GEMINI_API_KEY="your-gemini-key"
```

### 5. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 6. Run the Agent

```bash
python -m src.agent
```

---

## 🔑 API Keys

| Service | Key | Purpose |
|---------|-----|---------|
| **Cactus** | `cactus auth` | On-device model downloads & telemetry |
| **Gemini** | `GEMINI_API_KEY` | Cloud fallback for complex queries |

---

## 🏛️ Architecture

```
┌──────────────────────────────────────────────────┐
│                  Voice Agent                      │
│                                                    │
│  ┌──────────┐    ┌──────────────┐    ┌─────────┐ │
│  │  Voice    │───▶│  Cactus      │───▶│ Tools / │ │
│  │  Handler  │    │  Engine      │    │ Actions │ │
│  │ (mic/spk) │    │ (Gemma 4)    │    │         │ │
│  └──────────┘    └──────┬───────┘    └─────────┘ │
│                         │                         │
│                   ┌─────▼──────┐                  │
│                   │   Cloud    │                  │
│                   │  Fallback  │                  │
│                   │  (Gemini)  │                  │
│                   └────────────┘                  │
└──────────────────────────────────────────────────┘
```

**Inference Pipeline:**
1. **Voice Input** → Microphone capture with VAD (Voice Activity Detection)
2. **On-device Processing** → Gemma 4 on Cactus processes audio natively (0.3s to first token)
3. **Smart Routing** → FunctionGemma determines if cloud handoff is needed
4. **Tool Execution** → Function calls trigger real-world actions
5. **Response** → Text-to-speech or text output

---

## 👥 Team

| Member | Role | GitHub |
|--------|------|--------|
| Rayhan | Lead | [@rayhan](https://github.com/rayhan) |
| Member 2 | TBD | TBD |
| Member 3 | TBD | TBD |

---

## 📝 Hackathon Requirements

- [x] Uses **Gemma 4 on Cactus** ✅
- [x] Leverages **voice functionality** ✅  
- [ ] Working **MVP** capable of venture backing
- [ ] Demo video

### Judging Criteria
1. **Relevance & Realness** — Problem appeal to enterprises and VCs
2. **Correctness & Quality** — MVP and demo quality

### Special Tracks
- 🏢 **Best On-Device Enterprise Agent (B2B)**
- 🎯 **Ultimate Consumer Voice Experience (B2C)**  
- ⚙️ **Deepest Technical Integration**

---

## 📚 Resources

- [Cactus Docs](https://docs.cactuscompute.com/latest/)
- [Gemma 4 on Cactus Walkthrough](https://docs.cactuscompute.com/latest/blog/gemma4/)
- [Cactus Python SDK](https://docs.cactuscompute.com/latest/python/)
- [Hackathon Starter Repo](https://github.com/cactus-compute/voice-agents-hack)
- [Pre-quantized Weights](https://huggingface.co/cactus-compute)

---

## License

MIT — See [LICENSE](LICENSE) for details.
