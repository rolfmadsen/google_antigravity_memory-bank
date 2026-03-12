#!/usr/bin/env bash

# This script initializes the LanceDB Memory Bank inside a new Google Antigravity project workspace.
# Usage: 
#   cd /path/to/your/project
#   curl -sO https://raw.githubusercontent.com/rolfmadsen/google_antigravity_memory-bank/main/install.sh
#   chmod +x install.sh
#   ./install.sh [branch_or_tag]

set -e

echo "🧠 Initializing Memory Bank in $(pwd)..."

# Create target directories
mkdir -p .agent/memory-bank
mkdir -p .agent/skills/memory-manager
mkdir -p .agent/workflows

BRANCH_OR_TAG="${1:-main}"
REPO_URL="https://raw.githubusercontent.com/rolfmadsen/google_antigravity_memory-bank/refs/heads/$BRANCH_OR_TAG"

echo "📋 Downloading Memory Manager skill, bridge, and tests..."
curl -s "$REPO_URL/skills/memory-manager/SKILL.md" -o .agent/skills/memory-manager/SKILL.md
curl -s "$REPO_URL/skills/memory-manager/bridge.py" -o .agent/skills/memory-manager/bridge.py
curl -s "$REPO_URL/skills/memory-manager/test_bridge.py" -o .agent/skills/memory-manager/test_bridge.py

echo "📋 Downloading /sync workflow..."
curl -s "$REPO_URL/workflows/sync.md" -o .agent/workflows/sync.md

echo "🔒 Creating default .gitignore entry..."
if [ -f .gitignore ]; then
    if ! grep -q ".agent/memory-bank/lancedb/\.\*" .gitignore 2>/dev/null; then
        echo "
# Ignore LanceDB data but keep the Parquet export
.agent/memory-bank/lancedb/.*" >> .gitignore
    fi
else
    echo "
# Ignore LanceDB data but keep the Parquet export
.agent/memory-bank/lancedb/.*" > .gitignore
fi

echo "✅ Memory Bank initialized successfully!"
echo ""
echo "=== 🚀 NEXT STEPS ==="
echo "1. Remember to add the following exact phrase to your editor's Terminal Command Allow List:"
echo "   uv run .agent/skills/memory-manager/bridge.py"
echo "2. Ask the agent to run a test using:"
echo "   uv run --with pytest --with lancedb --with pandas --with pyarrow pytest .agent/skills/memory-manager/test_bridge.py"
echo "3. Type '/sync' to start archiving your session learnings!"
