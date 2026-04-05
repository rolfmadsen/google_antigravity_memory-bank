---
name: promote
description: Promote frequently-used project memories to the global Central Brain
---

# Promote to Global Brain (/promote)

When the user types `/promote`, follow these steps to distill project learnings into cross-project knowledge:

1. **Review**: Query the project memory bank for high-confidence, frequently-accessed memories:

// turbo-all
```bash
uv run .agent/skills/memory-manager/bridge.py query --query "*" --scope project --min-confidence 0.7 --format json
```

2. **Select Candidates**: Identify memories that would be valuable across ALL projects (not just this one). Good candidates are:
   - Coding conventions and patterns
   - Tool/library preferences and their rationale
   - Architectural principles
   - Common bug fixes with broad applicability

3. **Generalize**: For each candidate, create a generalized version that removes project-specific details.

4. **Promote**: Save the generalized version to the global brain:

```bash
uv run .agent/skills/memory-manager/bridge.py promote --id <memory_id> --generalized-text "Generalized version of the learning"
```

5. **Confirm**: List the promoted items and their global IDs.
