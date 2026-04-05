#!/usr/bin/env bash

# This script initializes the Federated AI Memory System inside a new project workspace.
# Usage: 
#   cd /path/to/your/project
#   curl -sO https://raw.githubusercontent.com/rolfmadsen/google_antigravity_memory-bank/main/install.sh
#   chmod +x install.sh
#   ./install.sh [branch_or_tag]

set -e

echo "🧠 Initializing Federated AI Memory System in $(pwd)..."

# Create target directories
mkdir -p .agent/memory-bank
mkdir -p .agent/skills/memory-manager
mkdir -p .agent/workflows

# Create global brain directory
GLOBAL_BRAIN="$HOME/.agent/brain"
mkdir -p "$GLOBAL_BRAIN"
echo "📁 Global brain directory: $GLOBAL_BRAIN"

BRANCH_OR_TAG="${1:-main}"
REPO_URL="https://raw.githubusercontent.com/rolfmadsen/google_antigravity_memory-bank/refs/heads/$BRANCH_OR_TAG"

echo "📋 Downloading core modules..."
curl -s "$REPO_URL/skills/memory-manager/memory_core.py" -o .agent/skills/memory-manager/memory_core.py
curl -s "$REPO_URL/skills/memory-manager/guardrails.py" -o .agent/skills/memory-manager/guardrails.py
curl -s "$REPO_URL/skills/memory-manager/federation.py" -o .agent/skills/memory-manager/federation.py
curl -s "$REPO_URL/skills/memory-manager/bridge.py" -o .agent/skills/memory-manager/bridge.py
curl -s "$REPO_URL/skills/memory-manager/mcp_server.py" -o .agent/skills/memory-manager/mcp_server.py

echo "📋 Downloading skill definition and tests..."
curl -s "$REPO_URL/skills/memory-manager/SKILL.md" -o .agent/skills/memory-manager/SKILL.md
curl -s "$REPO_URL/skills/memory-manager/test_bridge.py" -o .agent/skills/memory-manager/test_bridge.py

echo "📋 Downloading workflows..."
curl -s "$REPO_URL/workflows/sync.md" -o .agent/workflows/sync.md
curl -s "$REPO_URL/workflows/promote.md" -o .agent/workflows/promote.md
curl -s "$REPO_URL/workflows/audit.md" -o .agent/workflows/audit.md

echo "🔒 Creating default .gitignore entry..."
if [ -f .gitignore ]; then
    if ! grep -q ".agent/memory-bank/lancedb" .gitignore 2>/dev/null; then
        echo "
# Ignore LanceDB data but keep the Parquet export
.agent/memory-bank/lancedb/" >> .gitignore
    fi
else
    echo "
# Ignore LanceDB data but keep the Parquet export
.agent/memory-bank/lancedb/" > .gitignore
fi

echo "✅ Federated AI Memory System initialized!"
echo ""
echo "=== 🚀 NEXT STEPS ==="
echo ""
echo "1. ALLOW LIST — Add this to your editor's Terminal Command Allow List:"
echo "   uv run .agent/skills/memory-manager/bridge.py"
echo ""
echo "2. TEST — Verify the installation:"
echo "   uv run --with pytest --with lancedb --with pandas --with pyarrow --with tantivy pytest .agent/skills/memory-manager/test_bridge.py -v"
echo ""
echo "3. MCP (for Zed/Claude Desktop) — Add to your editor's MCP config:"
echo "   See README.md for Zed settings.json and Antigravity mcp_config.json examples."
echo ""
echo "4. USE IT — Save your first memory:"
echo "   uv run .agent/skills/memory-manager/bridge.py save --text 'Project initialized with federated AI memory' --type learning"
echo ""
echo "5. SYNC — Type /sync at the end of each session to persist learnings"
