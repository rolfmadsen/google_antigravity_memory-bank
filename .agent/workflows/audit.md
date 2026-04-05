---
name: audit
description: Run a health check on the memory bank — flag stale, duplicates, and contradictions
---

# Memory Audit (/audit)

When the user types `/audit`, perform a comprehensive health check:

1. **Get Status**: Display the overall system health:

// turbo-all
```bash
uv run .agent/skills/memory-manager/bridge.py status
```

2. **Find Stale Memories**: Query for all memories and identify those not verified in 90+ days. Present them to the user.

3. **Verify or Deprecate**: For each stale memory:
   - If still accurate: `uv run .agent/skills/memory-manager/bridge.py verify --id <id>`
   - If outdated: `uv run .agent/skills/memory-manager/bridge.py update --id <id> --status deprecated`

4. **Export**: Snapshot the cleaned memory bank:

```bash
uv run .agent/skills/memory-manager/bridge.py export
```

5. **Report**: Summarize the audit results — how many verified, deprecated, and remaining.
