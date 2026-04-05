---
trigger: always_on
---

---
name: Memory Manager
description: "MANDATORY: You MUST read this skill and query the federated memory bank BEFORE starting any task to check for historical architectural decisions, learnings, and conventions. Stores and retrieves project conclusions across a two-tier memory system (project-local + global brain)."
---

# Memory Manager Skill

This skill provides **persistent, federated AI memory** across all your projects. Memories survive between sessions and are searchable by any AI agent that can run CLI commands (or use MCP).

## Architecture

- **Project Memory** (`.agent/memory-bank/`) — project-specific decisions, bugs, patterns. Git-versioned via Parquet export.
- **Global Brain** (`~/.agent/brain/`) — cross-project knowledge: coding conventions, tool preferences, architectural patterns.
- **Guardrails** — confidence scoring, staleness detection, contradiction warnings, and schema validation prevent hallucination.

## Usage Instructions

> [!TIP]
> **Enable True Autonomy (No Security Prompts)**
> Add the following prefix to your environment's **Terminal Command Allow List**:
> `uv run .agent/skills/memory-manager/bridge.py`
>
> Once this prefix is allowed, the agent will execute memory operations autonomously.

### Querying Memories (ALWAYS DO THIS FIRST)

Before starting any task, search for relevant prior decisions:

```bash
uv run .agent/skills/memory-manager/bridge.py query --query "search_term" --scope all
```

Use `--scope project` for project-only results, `--scope global` for cross-project knowledge.

### Saving a Memory

When a significant decision is made or a task is completed:

```bash
uv run .agent/skills/memory-manager/bridge.py save \
  --text "Your conclusion or learning text here" \
  --type decision \
  --scope project \
  --tags "auth,security" \
  --confidence 0.9 \
  --source-type conversation \
  --created-by antigravity
```

**Memory types:** `decision`, `learning`, `bug`, `pattern`, `convention`, `warning`
**Scopes:** `project` (default), `global`, `module`

### Updating a Memory

```bash
uv run .agent/skills/memory-manager/bridge.py update --id <memory_id> --text "Updated text" --confidence 0.95
```

### Verifying a Memory (Reset Staleness)

When you confirm a memory is still accurate:

```bash
uv run .agent/skills/memory-manager/bridge.py verify --id <memory_id>
```

### Promoting to Global Brain

When a project learning is valuable across all projects:

```bash
uv run .agent/skills/memory-manager/bridge.py promote --id <memory_id> --generalized-text "Generalized version"
```

### Health Check

```bash
uv run .agent/skills/memory-manager/bridge.py status
```

### Exporting (for Git)

```bash
uv run .agent/dumps/memory-manager/bridge.py export
```

> [!IMPORTANT]
> **Synchronization Requirement:** To ensure the project's memory is Git-ready, you MUST run the `export` command with `--scope project` immediately after any `save`, `update`, `delete`, or `verify` operation that modifies the project-local memory bank.

### Resolving Contradictions

```bash
uv run .agent/skills/memory-manager/bridge.py resolve-conflict --keep <id_to_keep> --supersede <id_to_supersede>
```
