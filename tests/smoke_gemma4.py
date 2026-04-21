#!/usr/bin/env python3
"""Quick test: load Gemma 4 E4B and run a text completion."""

import sys
import json
import time

# Point to the cactus Python package
sys.path.insert(0, "cactus/python")
from src.cactus import cactus_init, cactus_complete, cactus_destroy

MODEL_PATH = "cactus/weights/gemma-4-e4b-it"

print("🔧 Loading Gemma 4 E4B...")
t0 = time.time()
model = cactus_init(MODEL_PATH, None, False)
print(f"✅ Model loaded in {time.time() - t0:.1f}s")

# Simple text completion
messages = json.dumps([
    {"role": "system", "content": "You are a helpful assistant. Be concise."},
    {"role": "user", "content": "Hello! What are you capable of? Answer in one sentence."}
])

options = json.dumps({"max_tokens": 128, "temperature": 0.7})

print("\n🤖 Generating response...")
t1 = time.time()

def on_token(token, token_id):
    print(token, end="", flush=True)

result = cactus_complete(model, messages, options, None, on_token)
elapsed = time.time() - t1

print(f"\n\n⚡ Generated in {elapsed:.2f}s")

# Parse the result
try:
    parsed = json.loads(result)
    print(f"📊 Response: {parsed.get('response', 'N/A')}")
    print(f"📊 Confidence: {parsed.get('confidence', 'N/A')}")
    print(f"📊 Cloud handoff: {parsed.get('cloud_handoff', 'N/A')}")
    print(f"📊 TTFT: {parsed.get('time_to_first_token_ms', 'N/A')}ms")
    print(f"📊 Decode speed: {parsed.get('decode_tps', 'N/A')} tok/s")
except json.JSONDecodeError:
    print(f"Raw result: {result}")

cactus_destroy(model)
print("\n✅ Done!")
