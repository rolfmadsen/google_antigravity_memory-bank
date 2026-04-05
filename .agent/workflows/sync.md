---
name: sync
description: Sync/Archive the current chat's conclusions into the Persistent Memory Bank
---

# Project Sync (/sync)

When the user types `/sync`, follow these steps to archive the current chat's learnings:

1. **Review Context**: Quickly review the current conversation history to identify the key conclusions, architectural decisions, or bugs solved.
2. **Formulate Learnings**: Abstract the findings into clear, concise, actionable memory items. Assign appropriate type, scope, and confidence.
3. **Save**: Execute the Memory Manager to save each significant item.

// turbo-all
```bash
uv run .agent/skills/memory-manager/bridge.py save --text "Summarized learning 1" --type learning --scope project --confidence 0.8 --created-by antigravity
```
```bash
uv run .agent/skills/memory-manager/bridge.py save --text "Summarized decision 2" --type decision --scope project --confidence 0.9 --created-by antigravity
```
```bash
uv run .agent/skills/memory-manager/bridge.py export --scope project
```

4. **Confirm**: Notify the user that the sync was successful and list the items that were committed to the Memory Bank.
