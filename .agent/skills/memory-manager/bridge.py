# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "lancedb",
#     "pyarrow",
#     "pandas",
#     "tantivy",
# ]
# ///

"""
bridge.py — CLI entry point for the Federated AI Memory System.

This is the universal interface: any AI agent that can execute shell commands
can use this to interact with the memory system. The MCP server (mcp_server.py)
provides an alternative entry point for agents that support MCP.

Usage:
    uv run bridge.py save --text "..." --type decision --scope project
    uv run bridge.py query --query "auth pattern" --scope all
    uv run bridge.py update --id <id> --text "..." --status active
    uv run bridge.py delete --id <id>
    uv run bridge.py verify --id <id>
    uv run bridge.py promote --id <id>
    uv run bridge.py status
    uv run bridge.py export
    uv run bridge.py resolve-conflict --keep <id> --supersede <id>
"""

import argparse
import json
import os
import sys

# Ensure sibling modules are importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from federation import FederationRouter
from guardrails import ValidationError


# ---------------------------------------------------------------------------
# Output Formatters
# ---------------------------------------------------------------------------

def format_results_markdown(response: dict):
    """Pretty-print query results as Markdown."""
    results = response.get("results", [])
    warnings = response.get("warnings", [])
    sources = response.get("sources", {})

    if not results:
        print("No memories found.")
        return

    # Header
    total = len(results)
    src_parts = []
    for tier, count in sources.items():
        if count > 0:
            src_parts.append(f"{count} {tier}")
    print(f"### Memory Search Results ({total} found: {', '.join(src_parts)})\n")

    # Warnings
    if warnings:
        for w in set(warnings):  # Deduplicate
            print(f"> {w}\n")

    # Results
    for idx, item in enumerate(results):
        tier = item.get("_source_tier", "?")
        stale = " 🟡 STALE" if item.get("_stale") else ""
        conf = item.get("confidence", 0.7)
        conf_bar = "●" * int(conf * 5) + "○" * (5 - int(conf * 5))

        print(f"**{idx + 1}. [{tier}]{stale}** `{item['id'][:16]}...`")
        print(f"   Type: `{item.get('memory_type', '?')}` | "
              f"Confidence: {conf_bar} ({conf:.0%}) | "
              f"Status: `{item.get('status', '?')}`")
        print(f"   Tags: {item.get('tags', '-') or '-'}")
        print(f"   Created: {item.get('created_at', '?')[:19]}")
        if item.get("source_project"):
            print(f"   Source: {item.get('source_project', '')} ({item.get('source_type', '')})")
        print(f"\n   {item['text']}\n")
        print("---\n")


def format_results_json(response: dict):
    """Output query results as JSON."""
    # Clean internal fields
    results = response.get("results", [])
    for r in results:
        for key in list(r.keys()):
            if key.startswith("_"):
                del r[key]
    print(json.dumps(response, indent=2, default=str))


def format_status(stats: dict):
    """Pretty-print system health status."""
    tiers = stats.get("tiers", {})
    total = stats.get("total_memories", 0)
    stale = stats.get("total_stale", 0)
    health = stats.get("overall_health_pct", 100)

    print("╔══════════════════════════════════════════════════════════╗")
    print("║                  🧠 Memory Brain Health                  ║")
    print("╠══════════════════════════════════════════════════════════╣")

    for name, tier in tiers.items():
        t = tier.get("total", 0)
        s = tier.get("stale", 0)
        label = f"  {name}:".ljust(22)
        detail = f"{t} memories ({s} stale)"
        print(f"║{label}{detail.ljust(36)}║")

    print("╠══════════════════════════════════════════════════════════╣")
    print(f"║  Total: {total}  |  Stale: {stale}  |  Health: {health}%".ljust(59) + "║")
    print("╚══════════════════════════════════════════════════════════╝")

    # Registry info
    registry = stats.get("registry", {})
    projects = registry.get("projects", {})
    if projects:
        print(f"\n📋 Registered projects: {', '.join(projects.keys())}")


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Federated AI Memory System — CLI Bridge",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="This CLI works with any AI agent. For MCP-compatible agents, use mcp_server.py instead.",
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # -- save --
    save_p = subparsers.add_parser("save", help="Save a new memory")
    save_p.add_argument("--text", required=True, help="The memory content")
    save_p.add_argument("--type", default="learning", dest="memory_type",
                        help="Memory type: decision|learning|bug|pattern|convention|warning")
    save_p.add_argument("--scope", default="project", help="Scope: global|project|module")
    save_p.add_argument("--tags", default="", help="Comma-separated tags")
    save_p.add_argument("--confidence", type=float, default=0.8, help="Confidence 0.0-1.0")
    save_p.add_argument("--source-type", default="conversation", help="Source type: conversation|commit|manual")
    save_p.add_argument("--source-ref", default="", help="Source reference (conversation ID, commit SHA)")
    save_p.add_argument("--created-by", default="unknown", help="Agent identity")
    save_p.add_argument("--metadata", default=None, help="Legacy JSON metadata string")

    # -- query --
    query_p = subparsers.add_parser("query", help="Search memories")
    query_p.add_argument("--query", required=True, help="Search text")
    query_p.add_argument("--scope", default="all", help="Scope: all|project|global")
    query_p.add_argument("--min-confidence", type=float, default=0.0, help="Minimum confidence filter")
    query_p.add_argument("--include-deprecated", action="store_true", help="Include deprecated/archived memories")
    query_p.add_argument("--limit", type=int, default=10, help="Max results")
    query_p.add_argument("--format", choices=["json", "markdown"], default="markdown", help="Output format")

    # -- update --
    update_p = subparsers.add_parser("update", help="Update a memory")
    update_p.add_argument("--id", required=True, help="Memory ID to update")
    update_p.add_argument("--text", default=None, help="New text")
    update_p.add_argument("--type", default=None, dest="memory_type", help="New memory type")
    update_p.add_argument("--confidence", type=float, default=None, help="New confidence")
    update_p.add_argument("--status", default=None, help="New status: active|superseded|deprecated|archived")
    update_p.add_argument("--tags", default=None, help="New tags")
    update_p.add_argument("--metadata", default=None, help="New JSON metadata")

    # -- delete --
    delete_p = subparsers.add_parser("delete", help="Delete a memory")
    delete_p.add_argument("--id", required=True, help="Memory ID to delete")

    # -- verify --
    verify_p = subparsers.add_parser("verify", help="Mark a memory as still-accurate")
    verify_p.add_argument("--id", required=True, help="Memory ID to verify")

    # -- promote --
    promote_p = subparsers.add_parser("promote", help="Promote a project memory to global")
    promote_p.add_argument("--id", required=True, help="Memory ID to promote")
    promote_p.add_argument("--generalized-text", default=None, help="Optional generalized version of the text")

    # -- resolve-conflict --
    resolve_p = subparsers.add_parser("resolve-conflict", help="Resolve a contradiction")
    resolve_p.add_argument("--keep", required=True, help="ID of memory to keep")
    resolve_p.add_argument("--supersede", required=True, help="ID of memory to supersede")
    resolve_p.add_argument("--note", default="", help="Resolution note")

    # -- status --
    subparsers.add_parser("status", help="Show memory bank health")

    # -- export --
    export_p = subparsers.add_parser("export", help="Export memory bank to Parquet")
    export_p.add_argument("--scope", default="all", help="Scope: all|project|global")

    # -- Parse --
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Initialize router
    router = FederationRouter()

    try:
        if args.command == "save":
            metadata = None
            if args.metadata:
                try:
                    metadata = json.loads(args.metadata)
                except json.JSONDecodeError:
                    print("Error: --metadata must be valid JSON.")
                    sys.exit(1)

            result = router.save(
                text=args.text,
                memory_type=args.memory_type,
                scope=args.scope,
                tags=args.tags,
                confidence=args.confidence,
                source_type=args.source_type,
                source_ref=args.source_ref,
                created_by=args.created_by,
                metadata_json=metadata,
            )

            print(f"Saved memory: {result['id']} (stored in: {result['stored_in']})")
            for w in result.get("warnings", []):
                print(f"  {w}")

        elif args.command == "query":
            response = router.query(
                query_text=args.query,
                scope=args.scope,
                min_confidence=args.min_confidence,
                include_deprecated=args.include_deprecated,
                limit=args.limit,
            )
            if args.format == "json":
                format_results_json(response)
            else:
                format_results_markdown(response)

        elif args.command == "update":
            metadata = None
            if args.metadata:
                try:
                    metadata = json.loads(args.metadata)
                except json.JSONDecodeError:
                    print("Error: --metadata must be valid JSON.")
                    sys.exit(1)

            result = router.update(
                record_id=args.id,
                text=args.text,
                memory_type=args.memory_type,
                confidence=args.confidence,
                status=args.status,
                tags=args.tags,
                metadata_json=metadata,
            )

            if result.get("updated"):
                print(f"Updated memory: {args.id} (in: {result['store']})")
            else:
                print(f"Error: {result.get('error', 'Unknown error')}")
                sys.exit(1)

        elif args.command == "delete":
            result = router.delete(args.id)
            if result.get("deleted"):
                print(f"Deleted memory: {args.id} (from: {result['store']})")
            else:
                print(f"Error: {result.get('error', 'Unknown error')}")
                sys.exit(1)

        elif args.command == "verify":
            result = router.verify(args.id)
            if result.get("verified"):
                print(f"Verified memory: {args.id} (in: {result['store']})")
            else:
                print(f"Error: {result.get('error', 'Unknown error')}")
                sys.exit(1)

        elif args.command == "promote":
            result = router.promote(args.id, generalized_text=args.generalized_text)
            if result.get("promoted"):
                print(f"Promoted: {result['source_id'][:16]}... → global:{result['global_id'][:16]}...")
            else:
                print(f"Error: {result.get('error', 'Unknown error')}")
                sys.exit(1)

        elif args.command == "resolve-conflict":
            result = router.resolve_conflict(
                keep_id=args.keep,
                supersede_id=args.supersede,
                resolution_note=args.note,
            )
            if result.get("resolved"):
                print(f"Resolved: kept {args.keep[:16]}..., superseded {args.supersede[:16]}...")
            else:
                print(f"Error: {result.get('error', 'Unknown error')}")
                sys.exit(1)

        elif args.command == "status":
            stats = router.status()
            format_status(stats)

        elif args.command == "export":
            result = router.export(scope=args.scope)
            for tier, info in result.items():
                print(f"Exported {info['records']} records to {info['path']}")

    except ValidationError as e:
        print(f"Validation error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
