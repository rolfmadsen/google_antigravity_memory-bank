# Federated AI Memory System

A local-first, editor-agnostic persistent memory system for AI coding agents. Works with **any** AI tool — Google Antigravity, Zed + Ollama, Claude Desktop, Cursor, or custom scripts.

## The Problem

AI coding agents lose context between sessions. They understand what they're looking at *now*, but forget the *why* — architectural decisions, hard-fought bug solutions, and established conventions. And when you switch editors or AI tools, all that knowledge stays locked in one silo.

## The Solution

A **federated two-tier memory system** that gives every AI agent persistent, searchable, hallucination-resistant memory:

- **Project Memory** (`.agent/memory-bank/`) — Project-specific decisions, versioned in git
- **Global Brain** (`~/.agent/brain/`) — Cross-project knowledge shared across all your workspaces
- **Guardrails** — Confidence scoring, staleness detection, and contradiction warnings

```
┌─────────────────────────────────────────────────────┐
│           AI Agent (Any Editor, Any Model)           │
├─────────────────────────────────────────────────────┤
│              MCP Server  ·  CLI Bridge               │
├─────────────────────────────────────────────────────┤
│     Federation Router (query both, merge, rank)      │
├──────────────────────┬──────────────────────────────┤
│   Project Memory     │      Global Brain             │
│   .agent/memory-bank │      ~/.agent/brain           │
│   (git-versioned)    │      (machine-local)          │
└──────────────────────┴──────────────────────────────┘
```

## Features

- **Editor-Agnostic:** MCP server works in Zed, Antigravity, Claude Desktop, Cursor. CLI works everywhere.
- **Two-Tier Federation:** Project-specific + cross-project memories, queried in parallel, merged intelligently.
- **Anti-Hallucination Guardrails:** Confidence scoring (0.0–1.0), staleness detection (90-day threshold), contradiction warnings, near-duplicate detection.
- **Local-First & Private:** Embedded LanceDB — no API keys, no cloud, no subscriptions.
- **Git-Friendly:** Parquet export for version-controlled team sharing.
- **Full Lifecycle:** Save → Query → Update → Verify → Promote → Deprecate → Archive.
- **Provenance Tracking:** Every memory records who created it, when, from which conversation, and in which project.

## Quickstart

### 1. Installation

```bash
cd /path/to/your/project
curl -sO https://raw.githubusercontent.com/rolfmadsen/google_antigravity_memory-bank/refs/heads/main/install.sh
chmod +x install.sh
./install.sh
```

### 2. Editor Setup

#### Zed + Ollama (MCP)

Add to Zed's `settings.json`:

```json
{
  "context_servers": {
    "memory-brain": {
      "command": "/home/rolfmadsen/.local/bin/uv",
      "args": ["run", "/path/to/project/.agent/skills/memory-manager/mcp_server.py"],
      "env": {
        "MEMORY_PROJECT_ROOT": "/path/to/project"
      }
    }
  }
}
```

#### Google Antigravity (MCP + CLI)

Add to `~/.gemini/antigravity/mcp_config.json`:

```json
{
  "mcpServers": {
    "memory-brain": {
      "command": "uv",
      "args": ["run", ".agent/skills/memory-manager/mcp_server.py"],
      "env": { "MEMORY_PROJECT_ROOT": "." }
    }
  }
}
```

Also add the CLI allow-list prefix for slash commands:

```
uv run .agent/skills/memory-manager/bridge.py
```

#### Claude Desktop (MCP)

Add to `~/.config/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "memory-brain": {
      "command": "uv",
      "args": ["run", "/path/to/project/.agent/skills/memory-manager/mcp_server.py"],
      "env": { "MEMORY_PROJECT_ROOT": "/path/to/project" }
    }
  }
}
```

#### Any Other Agent (CLI)

Any agent that can execute shell commands can use the CLI directly:

```bash
uv run .agent/skills/memory-manager/bridge.py query --query "search term" --scope all
```

### 3. Usage

#### Save a memory

```bash
uv run .agent/skills/memory-manager/bridge.py save \
  --text "Always use OAuth 2.1 for auth in this project" \
  --type decision --scope project --confidence 0.9 --tags "auth,security"
```

#### Query memories

```bash
uv run .agent/skills/memory-manager/bridge.py query --query "authentication" --scope all
```

#### Check health

```bash
uv run .agent/skills/memory-manager/bridge.py status
```

#### Promote to global brain

```bash
uv run .agent/skills/memory-manager/bridge.py promote --id <memory_id>
```

### 4. Workflows

| Command | Description |
|---|---|
| `/sync` | Archive the current session's learnings to project memory |
| `/promote` | Distill project learnings into the global brain |
| `/audit` | Health check: flag stale memories, resolve contradictions |

## Architecture

### Files

| File | Purpose |
|---|---|
| `memory_core.py` | Core DB operations, schema, migration |
| `guardrails.py` | Validation, confidence gating, staleness, contradiction detection |
| `federation.py` | Two-tier routing, merge, promote, conflict resolution |
| `bridge.py` | CLI entry point (universal) |
| `mcp_server.py` | MCP adapter (Zed/Antigravity/Claude Desktop) |

### Memory Schema

| Field | Type | Description |
|---|---|---|
| `id` | string | SHA-256 hash |
| `text` | string | The memory content |
| `memory_type` | string | decision / learning / bug / pattern / convention / warning |
| `scope` | string | global / project / module |
| `confidence` | float | 0.0–1.0 confidence score |
| `status` | string | active / superseded / deprecated / archived |
| `tags` | string | Comma-separated tags |
| `source_type` | string | conversation / commit / manual / import |
| `source_ref` | string | Conversation ID, commit SHA |
| `source_project` | string | Project name |
| `created_by` | string | Agent identity |
| `last_verified` | string | ISO timestamp (for staleness detection) |
| `created_at` | string | ISO timestamp |

## License

GNU General Public License v3.0 — see [LICENSE](LICENSE) for details.