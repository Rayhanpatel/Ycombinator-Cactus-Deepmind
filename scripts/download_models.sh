#!/bin/bash
# ============================================
# Download Required Model Weights
# ============================================
# Downloads pre-quantized model weights from HuggingFace.
# Usage: ./scripts/download_models.sh

set -e

echo "📦 Downloading model weights…"
echo "================================"

# Gemma 4 E2B (main LLM — on-device multimodal with voice)
echo ""
echo "1/3 ⬇️  Downloading Gemma 4 E2B…"
cactus download google/gemma-4-E2B-it

# FunctionGemma (for function calling / tool use)
echo ""
echo "2/3 ⬇️  Downloading FunctionGemma 270M…"
cactus download google/functiongemma-270m-it --reconvert

# Whisper Small (transcription fallback)
echo ""
echo "3/3 ⬇️  Downloading Whisper Small…"
cactus download openai/whisper-small

echo ""
echo "================================"
echo "✅ All models downloaded!"
echo ""
echo "Available models:"
echo "  • google/gemma-4-E2B-it        (Main LLM — voice, vision, text)"
echo "  • google/functiongemma-270m-it  (Function calling)"
echo "  • openai/whisper-small          (Transcription)"
echo ""
echo "Optional: Download Gemma 4 E4B for higher quality (needs more RAM):"
echo "  cactus download google/gemma-4-E4B-it"
echo "================================"
