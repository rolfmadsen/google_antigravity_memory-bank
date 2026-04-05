# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "mcp",
#     "lancedb",
#     "pyarrow",
#     "pandas",
#     "tantivy",
# ]
# ///

"""
mcp_server.py — Thin MCP adapter for the Federated AI Memory System.

This is a ~100-line wrapper that exposes federation.py as MCP tools.
Any MCP-compatible AI agent (Zed+Ollama, Antigravity, Claude Desktop,
Cursor) can discover and use these tools automatically.

The REAL logic lives in federation.py — this file just translates
MCP tool calls into federation.py function calls.

Usage:
    uv run mcp_server.py              # stdio mode (default, for editors)
"""

import json
import os
import sys

# Ensure sibling modules are importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp.server.fastmcp import FastMCP

from federation import FederationRouter
from guardrails import ValidationError

# ---------------------------------------------------------------------------
# Initialize
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "memory-brain",
    instructions=(
        "Federated AI Memory System. Use these tools to save, query, and manage "
        "persistent memories across projects. Memories survive between sessions "
        "and are shared across all your AI tools."
    ),
)

# Lazy-init router (created on first tool call)
_router = None


def get_router() -> FederationRouter:
    global _router
    if _router is None:
        _router = FederationRouter()
    return _router


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def memory_query(
    query: str,
    scope: str = "all",
    min_confidence: float = 0.0,
    include_deprecated: bool = False,
    limit: int = 10,
) -> str:
    """
    Search the federated memory bank across project and global memories.

    Args:
        query: Natural language search text
        scope: "all" (both tiers), "project" (current project only), "global" (cross-project only)
        min_confidence: Minimum confidence threshold (0.0-1.0)
        include_deprecated: Whether to include deprecated/archived memories
        limit: Maximum number of results

    Returns:
        JSON with results, warnings, and source tier counts.
    """
    router = get_router()
    response = router.query(
        query_text=query,
        scope=scope,
        min_confidence=min_confidence,
        include_deprecated=include_deprecated,
        limit=limit,
    )
    # Clean internal fields for output
    for r in response.get("results", []):
        for key in list(r.keys()):
            if key.startswith("_"):
                del r[key]
    return json.dumps(response, indent=2, default=str)


@mcp.tool()
def memory_save(
    text: str,
    memory_type: str = "learning",
    scope: str = "project",
    tags: str = "",
    confidence: float = 0.8,
    source_type: str = "conversation",
    source_ref: str = "",
    created_by: str = "unknown",
) -> str:
    """
    Save a new memory with provenance tracking and guardrails.

    Args:
        text: The memory content (decision, learning, bug fix, pattern, etc.)
        memory_type: One of: decision, learning, bug, pattern, convention, warning
        scope: "project" (current project), "global" (cross-project), "module" (specific module)
        tags: Comma-separated tags for filtering
        confidence: How confident you are in this memory (0.0-1.0)
        source_type: Origin type: conversation, commit, manual
        source_ref: Reference ID (conversation ID, commit SHA)
        created_by: Your agent identity

    Returns:
        JSON with the generated memory ID, storage tier, and any warnings.
    """
    router = get_router()
    try:
        result = router.save(
            text=text,
            memory_type=memory_type,
            scope=scope,
            tags=tags,
            confidence=confidence,
            source_type=source_type,
            source_ref=source_ref,
            created_by=created_by,
        )
        return json.dumps(result, indent=2)
    except ValidationError as e:
        return json.dumps({"error": str(e)}, indent=2)


@mcp.tool()
def memory_update(
    id: str,
    text: str = "",
    memory_type: str = "",
    confidence: float = -1,
    status: str = "",
    tags: str = "",
) -> str:
    """
    Update an existing memory. Only provide fields you want to change.

    Args:
        id: The memory ID to update
        text: New text content (empty = no change)
        memory_type: New type (empty = no change)
        confidence: New confidence (-1 = no change)
        status: New status: active, superseded, deprecated, archived (empty = no change)
        tags: New tags (empty = no change)

    Returns:
        JSON confirming the update or an error message.
    """
    router = get_router()
    kwargs = {}
    if text:
        kwargs["text"] = text
    if memory_type:
        kwargs["memory_type"] = memory_type
    if confidence >= 0:
        kwargs["confidence"] = confidence
    if status:
        kwargs["status"] = status
    if tags:
        kwargs["tags"] = tags

    try:
        result = router.update(id, **kwargs)
        return json.dumps(result, indent=2)
    except ValidationError as e:
        return json.dumps({"error": str(e)}, indent=2)


@mcp.tool()
def memory_delete(id: str) -> str:
    """
    Delete a memory by ID.

    Args:
        id: The memory ID to delete

    Returns:
        JSON confirming deletion or an error message.
    """
    router = get_router()
    result = router.delete(id)
    return json.dumps(result, indent=2)


@mcp.tool()
def memory_verify(id: str) -> str:
    """
    Mark a memory as still-accurate. Resets the staleness timer so
    the memory won't be flagged as potentially outdated.

    Args:
        id: The memory ID to verify

    Returns:
        JSON confirming verification or an error message.
    """
    router = get_router()
    result = router.verify(id)
    return json.dumps(result, indent=2)


@mcp.tool()
def memory_promote(id: str, generalized_text: str = "") -> str:
    """
    Promote a project-specific memory to the global Central Brain.
    Optionally provide generalized_text to abstract away project-specific details.

    Args:
        id: The project memory ID to promote
        generalized_text: Optional generalized version (empty = use original text)

    Returns:
        JSON with the new global memory ID.
    """
    router = get_router()
    result = router.promote(id, generalized_text=generalized_text or None)
    return json.dumps(result, indent=2)


@mcp.tool()
def memory_resolve_conflict(keep_id: str, supersede_id: str, note: str = "") -> str:
    """
    Resolve a contradiction between two memories by keeping one and
    superseding the other.

    Args:
        keep_id: ID of the memory to keep (will get a confidence boost)
        supersede_id: ID of the memory to mark as superseded
        note: Optional resolution note

    Returns:
        JSON confirming the resolution.
    """
    router = get_router()
    result = router.resolve_conflict(keep_id, supersede_id, resolution_note=note)
    return json.dumps(result, indent=2)


@mcp.tool()
def memory_status() -> str:
    """
    Get health metrics for all memory stores: total memories, stale count,
    health percentage, and registered projects.

    Returns:
        JSON with health statistics across all tiers.
    """
    router = get_router()
    stats = router.status()
    return json.dumps(stats, indent=2, default=str)


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
