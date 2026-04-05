"""
federation.py — Two-tier query routing for the AI Memory System.

Manages both the project-local memory bank and the global Central Brain,
routing queries to both and merging results intelligently.

This is the core logic layer that both bridge.py (CLI) and
mcp_server.py (MCP adapter) delegate to.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from memory_core import MemoryStore
from guardrails import (
    validate_save_input,
    validate_update_input,
    check_staleness,
    filter_by_confidence,
    detect_contradictions,
    check_near_duplicate,
    ValidationError,
)


# ---------------------------------------------------------------------------
# Path Resolution
# ---------------------------------------------------------------------------

def _resolve_project_root() -> Optional[str]:
    """Find the project root by looking for .agent/memory-bank/ upward."""
    env_root = os.environ.get("MEMORY_PROJECT_ROOT")
    if env_root:
        resolved = os.path.abspath(env_root)
        if os.path.isdir(os.path.join(resolved, ".agent")):
            return resolved
        # If MEMORY_PROJECT_ROOT is set but no .agent dir, still use it
        return resolved

    # Walk upward from this file's location
    current = Path(__file__).resolve().parent
    for _ in range(10):  # Max 10 levels up
        if (current / ".agent" / "memory-bank").is_dir():
            return str(current)
        parent = current.parent
        if parent == current:
            break
        current = parent

    return None


def _global_brain_path() -> str:
    """Return the path to the global Central Brain."""
    return os.path.join(Path.home(), ".agent", "brain", "lancedb")


def _global_export_path() -> str:
    return os.path.join(Path.home(), ".agent", "brain", "global_memory.parquet")


def _project_db_path(project_root: str) -> str:
    return os.path.join(project_root, ".agent", "memory-bank", "lancedb")


def _project_export_path(project_root: str) -> str:
    return os.path.join(project_root, ".agent", "memory-bank", "conclusions_backup.parquet")


def _registry_path() -> str:
    return os.path.join(Path.home(), ".agent", "brain", "project_registry.json")


def _project_slug(project_root: str) -> str:
    """Derive a short project name from the path."""
    return os.path.basename(os.path.abspath(project_root))


# ---------------------------------------------------------------------------
# Project Registry
# ---------------------------------------------------------------------------

def _load_registry() -> dict:
    path = _registry_path()
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {"projects": {}}


def _save_registry(registry: dict):
    path = _registry_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(registry, f, indent=2)


def _register_project(project_root: str, memory_count: int = 0):
    """Register a project in the global project registry."""
    registry = _load_registry()
    slug = _project_slug(project_root)
    registry["projects"][slug] = {
        "path": os.path.abspath(project_root),
        "last_synced": datetime.now().isoformat(),
        "memory_count": memory_count,
    }
    _save_registry(registry)


# ---------------------------------------------------------------------------
# FederationRouter
# ---------------------------------------------------------------------------

class FederationRouter:
    """
    Routes memory operations across project-local and global stores.

    Both bridge.py (CLI) and mcp_server.py (MCP) use this class
    as their single entry point to the memory system.
    """

    def __init__(self, project_root: Optional[str] = None):
        self.project_root = project_root or _resolve_project_root()
        self.project_slug = _project_slug(self.project_root) if self.project_root else "unknown"

        # Initialize stores
        self._project_store = None
        self._global_store = None

    @property
    def project_store(self) -> Optional[MemoryStore]:
        if self._project_store is None and self.project_root:
            db_path = _project_db_path(self.project_root)
            self._project_store = MemoryStore(db_path, store_name=f"project:{self.project_slug}")
        return self._project_store

    @property
    def global_store(self) -> MemoryStore:
        if self._global_store is None:
            db_path = _global_brain_path()
            self._global_store = MemoryStore(db_path, store_name="global")
        return self._global_store

    # -------------------------------------------------------------------
    # Query (federated)
    # -------------------------------------------------------------------

    def query(
        self,
        query_text: str,
        scope: str = "all",
        min_confidence: float = 0.0,
        include_deprecated: bool = False,
        limit: int = 10,
    ) -> dict:
        """
        Search across project and/or global memory banks.

        Returns:
            {
                "results": [...],
                "warnings": [...],
                "sources": {"project": N, "global": M}
            }
        """
        results = []
        warnings = []
        sources = {"project": 0, "global": 0}

        # Query project store
        if scope in ("all", "project") and self.project_store:
            project_results = self.project_store.query(
                query_text, min_confidence=min_confidence,
                include_deprecated=include_deprecated, limit=limit,
            )
            for r in project_results:
                r["_source_tier"] = "project"
            results.extend(project_results)
            sources["project"] = len(project_results)

        # Query global store
        if scope in ("all", "global"):
            global_results = self.global_store.query(
                query_text, min_confidence=min_confidence,
                include_deprecated=include_deprecated, limit=limit,
            )
            for r in global_results:
                r["_source_tier"] = "global"
            results.extend(global_results)
            sources["global"] = len(global_results)

        # Merge & rank
        results = self._merge_results(results, limit)

        # Apply guardrails
        results = check_staleness(results)
        results = filter_by_confidence(results, min_confidence)

        # Collect warnings
        for r in results:
            if r.get("_stale"):
                warnings.append(r.get("_warning", "Stale memory detected."))

        # Increment access counters (fire and forget)
        for r in results:
            tier = r.get("_source_tier", "project")
            store = self.project_store if tier == "project" else self.global_store
            if store:
                store.increment_access(r["id"])

        return {
            "results": results,
            "warnings": warnings,
            "sources": sources,
        }

    def _merge_results(self, results: list[dict], limit: int) -> list[dict]:
        """
        Merge results from multiple tiers.

        Ranking strategy:
        1. Project results rank higher than global (specificity wins)
        2. Higher confidence scores rank higher
        3. More recent memories rank higher
        """
        # Deduplicate by text similarity (exact match)
        seen_texts = set()
        deduped = []
        for r in results:
            text_key = r.get("text", "").strip().lower()
            if text_key not in seen_texts:
                seen_texts.add(text_key)
                deduped.append(r)

        # Score each result
        def rank_score(r):
            tier_bonus = 1.0 if r.get("_source_tier") == "project" else 0.5
            confidence = r.get("confidence", 0.7)
            # Recency: newer = higher score (use created_at as a proxy)
            try:
                age_days = (datetime.now() - datetime.fromisoformat(r.get("created_at", ""))).days
                recency = max(0, 1.0 - (age_days / 365))
            except (ValueError, TypeError):
                recency = 0.5

            return tier_bonus + confidence + recency

        deduped.sort(key=rank_score, reverse=True)
        return deduped[:limit]

    # -------------------------------------------------------------------
    # Save (with guardrails)
    # -------------------------------------------------------------------

    def save(
        self,
        text: str,
        memory_type: str = "learning",
        scope: str = "project",
        tags: str = "",
        confidence: float = 0.8,
        source_type: str = "conversation",
        source_ref: str = "",
        created_by: str = "unknown",
        metadata_json: Optional[dict] = None,
    ) -> dict:
        """
        Save a memory with full validation and guardrails.

        Returns:
            {"id": "...", "stored_in": "project|global", "warnings": [...]}
        """
        # Validate input
        cleaned = validate_save_input(
            text=text, memory_type=memory_type, scope=scope,
            confidence=confidence, source_type=source_type, tags=tags,
        )

        warnings = []

        # Choose store based on scope
        if cleaned["scope"] == "global":
            store = self.global_store
            stored_in = "global"
        else:
            store = self.project_store
            stored_in = "project"
            if store is None:
                # Fallback to global if no project detected
                store = self.global_store
                stored_in = "global"
                warnings.append("No project root detected. Saved to global brain instead.")

        # Check for near-duplicates
        existing = store.get_all()
        duplicate = check_near_duplicate(cleaned["text"], existing)
        if duplicate:
            warnings.append(
                f"⚠️ Near-duplicate detected (ID: {duplicate['id']}). "
                f"Saving anyway, but consider updating the existing memory instead."
            )

        # Check for contradictions
        conflicts = detect_contradictions(cleaned["text"], existing)
        if conflicts:
            conflict_ids = [c["id"][:12] for c in conflicts]
            warnings.append(
                f"⚠️ Potential contradiction with {len(conflicts)} existing memor{'y' if len(conflicts) == 1 else 'ies'} "
                f"(IDs: {', '.join(conflict_ids)}...). Consider resolving with 'resolve-conflict'."
            )

        # Save
        record_id = store.save(
            text=cleaned["text"],
            memory_type=cleaned["memory_type"],
            scope=cleaned["scope"],
            tags=cleaned["tags"],
            confidence=cleaned["confidence"],
            source_type=source_type,
            source_ref=source_ref,
            source_project=self.project_slug,
            created_by=created_by,
            metadata_json=metadata_json,
        )

        # Update registry
        if stored_in == "project" and self.project_root:
            stats = store.get_stats()
            _register_project(self.project_root, stats["total"])

        return {"id": record_id, "stored_in": stored_in, "warnings": warnings}

    # -------------------------------------------------------------------
    # Update / Delete / Verify
    # -------------------------------------------------------------------

    def update(self, record_id: str, **kwargs) -> dict:
        """Update a memory, searching both tiers for the ID."""
        # Validate updateable fields
        validate_update_input(
            status=kwargs.get("status"),
            confidence=kwargs.get("confidence"),
            memory_type=kwargs.get("memory_type"),
        )

        # Try project first, then global
        for store_name, store in self._iter_stores():
            if store and store.update(record_id, **kwargs):
                return {"updated": True, "store": store_name}

        return {"updated": False, "error": f"Memory '{record_id}' not found in any store."}

    def delete(self, record_id: str) -> dict:
        """Delete a memory from whichever tier contains it."""
        for store_name, store in self._iter_stores():
            if store and store.delete(record_id):
                return {"deleted": True, "store": store_name}

        return {"deleted": False, "error": f"Memory '{record_id}' not found in any store."}

    def verify(self, record_id: str) -> dict:
        """Mark a memory as still-accurate (resets staleness timer)."""
        for store_name, store in self._iter_stores():
            if store and store.verify(record_id):
                return {"verified": True, "store": store_name}

        return {"verified": False, "error": f"Memory '{record_id}' not found in any store."}

    # -------------------------------------------------------------------
    # Promote (project → global)
    # -------------------------------------------------------------------

    def promote(self, record_id: str, generalized_text: Optional[str] = None) -> dict:
        """
        Promote a project memory to the global Central Brain.
        Optionally provide generalized_text to abstract away project-specific details.
        """
        if not self.project_store:
            return {"promoted": False, "error": "No project store available."}

        source = self.project_store.get_by_id(record_id)
        if not source:
            return {"promoted": False, "error": f"Memory '{record_id}' not found in project store."}

        # Save to global with adjusted scope
        global_id = self.global_store.save(
            text=generalized_text or source["text"],
            memory_type=source["memory_type"],
            scope="global",
            tags=source["tags"],
            confidence=source["confidence"],
            source_type="import",
            source_ref=f"promoted:{record_id}",
            source_project=self.project_slug,
            created_by=source["created_by"],
        )

        return {
            "promoted": True,
            "source_id": record_id,
            "global_id": global_id,
            "source_project": self.project_slug,
        }

    # -------------------------------------------------------------------
    # Resolve Conflicts
    # -------------------------------------------------------------------

    def resolve_conflict(
        self,
        keep_id: str,
        supersede_id: str,
        resolution_note: str = "",
    ) -> dict:
        """
        Resolve a contradiction by keeping one memory and superseding the other.
        """
        # Mark the superseded memory
        result = self.update(
            supersede_id,
            status="superseded",
            superseded_by=keep_id,
        )
        if not result.get("updated"):
            return {"resolved": False, "error": f"Could not find memory '{supersede_id}'."}

        # Optionally bump confidence of the kept memory
        self.update(keep_id, confidence=0.9)

        return {
            "resolved": True,
            "kept": keep_id,
            "superseded": supersede_id,
            "note": resolution_note,
        }

    # -------------------------------------------------------------------
    # Export
    # -------------------------------------------------------------------

    def export(self, scope: str = "all") -> dict:
        """Export memory banks to Parquet files."""
        exported = {}

        if scope in ("all", "project") and self.project_store and self.project_root:
            path = _project_export_path(self.project_root)
            count = self.project_store.export_parquet(path)
            exported["project"] = {"path": path, "records": count}

        if scope in ("all", "global"):
            path = _global_export_path()
            count = self.global_store.export_parquet(path)
            exported["global"] = {"path": path, "records": count}

        return exported

    # -------------------------------------------------------------------
    # Stats / Health
    # -------------------------------------------------------------------

    def status(self) -> dict:
        """Get health statistics across all tiers."""
        stats = {"tiers": {}, "registry": _load_registry()}

        if self.project_store:
            stats["tiers"]["project"] = self.project_store.get_stats()

        stats["tiers"]["global"] = self.global_store.get_stats()

        # Overall health
        total = sum(t.get("total", 0) for t in stats["tiers"].values())
        stale = sum(t.get("stale", 0) for t in stats["tiers"].values())
        stats["total_memories"] = total
        stats["total_stale"] = stale
        stats["overall_health_pct"] = round(
            ((total - stale) / total * 100) if total > 0 else 100, 1
        )

        return stats

    # -------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------

    def _iter_stores(self):
        """Yield (name, store) for each available tier, project first."""
        if self.project_store:
            yield "project", self.project_store
        yield "global", self.global_store
