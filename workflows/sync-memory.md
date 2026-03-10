---
description: Sync/Archive the current chat's conclusions into the Persistent Memory Bank
---

# Project Sync (/sync)

When the user types `/sync`, follow these steps to archive the current chat's learnings:

1. **Review Context**: Quickly review the current conversation history to identify the key conclusions, architectural decisions, or bugs solved.
2. **Formulate Learnings**: Abstract the findings into clear, concise, actionable memory items.
3. **Save**: Execute the Memory Manager to save each significant item.

// turbo-all
```bash
uv run .agent/skills/memory-manager/bridge.py save --text "Summarized learning 1" --metadata '{"type": "learning", "module": "relevant module", "status": "active"}'
```
```bash
uv run .agent/skills/memory-manager/bridge.py save --text "Summarized decision 2" --metadata '{"type": "decision", "module": "relevant module", "status": "active"}'
```
```bash
uv run .agent/skills/memory-manager/bridge.py export
```

4. **Confirm**: Notify the user that the sync was successful and list the items that were committed to the Memory Bank.
