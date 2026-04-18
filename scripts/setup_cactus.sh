#!/bin/bash
# ============================================
# Cactus SDK Setup Script
# ============================================
# Run this once to clone and build the Cactus SDK.
# Usage: ./scripts/setup_cactus.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "🌵 Setting up Cactus SDK…"
echo "================================"

# Step 1: Clone Cactus
if [ ! -d "$PROJECT_ROOT/cactus" ]; then
    echo "📦 Cloning Cactus repository…"
    cd "$PROJECT_ROOT"
    git clone https://github.com/cactus-compute/cactus
else
    echo "✅ Cactus repo already exists."
fi

# Step 2: Build
echo "🔨 Building Cactus SDK…"
cd "$PROJECT_ROOT/cactus"
source ./setup

# Step 3: Build Python bindings
echo "🐍 Building Python bindings…"
cactus build --python

echo ""
echo "================================"
echo "✅ Cactus SDK setup complete!"
echo ""
echo "Next steps:"
echo "  1. Run: cactus auth"
echo "     (Enter your Cactus API key when prompted)"
echo "  2. Run: ./scripts/download_models.sh"
echo "     (Downloads model weights)"
echo "================================"
