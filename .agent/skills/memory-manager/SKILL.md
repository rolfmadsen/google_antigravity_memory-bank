---
name: Memory Manager
description: Stores and retrieves project conclusions, architectural decisions, and learnings using LanceDB. Ensures a persistent project memory bank without lock-in.
---

# Memory Manager Skill

This skill allows you to save and query persistent project memory to remember architectural decisions, learnings, and conclusions across different sessions. Data is saved to a local LanceDB instance and backed up to a portable Parquet file `.agent/memory-bank/conclusions_backup.parquet`.

## Usage Instructions

> [!TIP]
> **Enable True Autonomy (No Security Prompts)**
> To allow the Memory Manager to save memories quietly in the background without asking for your permission every time, add the following prefix to your environment's **Terminal Command Allow List**:
> `uv run .agent/skills/memory-manager/bridge.py`
> 
> Once this prefix is allowed, the agent will execute memory operations autonomously.

To use the Memory Manager natively, run the `bridge.py` script via the terminal.

### Saving a Memory
When a significant decision is made or a task is completed, save the conclusion:

```bash
uv run .agent/skills/memory-manager/bridge.py save --text "Your conclusion or learning text here" --metadata '{"type": "decision", "module": "SCEP", "status": "active"}'
```
*Note: Ensure the metadata is a valid JSON string.*

### Querying Memories
When starting a new task or needing context, search the memory bank:

```bash
uv run .agent/skills/memory-manager/bridge.py query --query "search_term"
```
