"""
memory_core.py — Core database operations for the AI Memory System.

Handles a single LanceDB tier (project-local OR global).
Federation across tiers is handled by federation.py.

Enhanced schema with provenance, confidence, and lifecycle management.
Backward-compatible with the original bridge.py schema.
"""

import hashlib
import json
import os
from datetime import datetime, timedelta
from typing import Optional

import lancedb
import pyarrow as pa

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

SCHEMA = pa.schema([
    ("id", pa.string()),
    ("text", pa.string()),
    ("memory_type", pa.string()),       # decision | learning | bug | pattern | convention | warning
    ("scope", pa.string()),             # global | project | module
    ("tags", pa.string()),              # Comma-separated tags
    ("confidence", pa.float32()),       # 0.0–1.0
    ("status", pa.string()),            # active | superseded | deprecated | archived
    ("superseded_by", pa.string()),     # ID of the memory that replaced this one
    ("source_type", pa.string()),       # conversation | commit | manual | import
    ("source_ref", pa.string()),        # Conversation ID, commit SHA, file path
    ("source_project", pa.string()),    # Project slug
    ("created_by", pa.string()),        # Agent identity
    ("last_verified", pa.string()),     # ISO timestamp
    ("access_count", pa.int32()),       # How often retrieved
    ("created_at", pa.string()),        # ISO timestamp
    ("updated_at", pa.string()),        # ISO timestamp
    ("metadata", pa.string()),          # Legacy JSON blob for backward compat
])

TABLE_NAME = "memory_bank"

# Default values for new fields when migrating old records
FIELD_DEFAULTS = {
    "memory_type": "learning",
    "scope": "project",
    "tags": "",
    "confidence": 0.7,
    "status": "active",
    "superseded_by": "",
    "source_type": "import",
    "source_ref": "",
    "source_project": "",
    "created_by": "unknown",
    "last_verified": "",
    "access_count": 0,
    "updated_at": "",
}


# ---------------------------------------------------------------------------
# MemoryStore — single-tier database operations
# ---------------------------------------------------------------------------

class MemoryStore:
    """Manages a single LanceDB memory bank (either project-local or global)."""

    def __init__(self, db_path: str, store_name: str = "project"):
        self.db_path = db_path
        self.store_name = store_name
        self._db = None
        self._table = None
        os.makedirs(db_path, exist_ok=True)

    @property
    def db(self):
        if self._db is None:
            self._db = lancedb.connect(self.db_path)
        return self._db

    def get_table(self) -> lancedb.table.Table:
        """Get or create the memory_bank table, migrating old schema if needed."""
        if self._table is not None:
            return self._table

        try:
            table = self.db.open_table(TABLE_NAME)
            # Check if migration is needed (old schema lacks 'confidence' column)
            existing_names = set(table.schema.names)
            if "confidence" not in existing_names:
                table = self._migrate_table(table)
            self._table = table
        except Exception:
            self._table = self.db.create_table(TABLE_NAME, schema=SCHEMA)

        return self._table

    def _migrate_table(self, old_table) -> lancedb.table.Table:
        """Migrate from old schema (id, text, metadata, timestamp) to new schema."""
        df = old_table.to_pandas()
        if df.empty:
            self.db.drop_table(TABLE_NAME)
            return self.db.create_table(TABLE_NAME, schema=SCHEMA)

        migrated_records = []
        for _, row in df.iterrows():
            # Parse old metadata JSON
            old_meta = {}
            if "metadata" in row and row["metadata"]:
                try:
                    old_meta = json.loads(row["metadata"])
                except (json.JSONDecodeError, TypeError):
                    pass

            # Map old fields to new
            record = {
                "id": row.get("id", hashlib.sha256(str(row).encode()).hexdigest()),
                "text": row.get("text", ""),
                "memory_type": old_meta.get("type", FIELD_DEFAULTS["memory_type"]),
                "scope": old_meta.get("scope", FIELD_DEFAULTS["scope"]),
                "tags": old_meta.get("module", FIELD_DEFAULTS["tags"]),
                "confidence": FIELD_DEFAULTS["confidence"],
                "status": old_meta.get("status", FIELD_DEFAULTS["status"]),
                "superseded_by": FIELD_DEFAULTS["superseded_by"],
                "source_type": FIELD_DEFAULTS["source_type"],
                "source_ref": FIELD_DEFAULTS["source_ref"],
                "source_project": FIELD_DEFAULTS["source_project"],
                "created_by": FIELD_DEFAULTS["created_by"],
                "last_verified": FIELD_DEFAULTS["last_verified"],
                "access_count": FIELD_DEFAULTS["access_count"],
                "created_at": row.get("timestamp", datetime.now().isoformat()),
                "updated_at": FIELD_DEFAULTS["updated_at"],
                "metadata": row.get("metadata", "{}"),
            }
            migrated_records.append(record)

        self.db.drop_table(TABLE_NAME)
        new_table = self.db.create_table(TABLE_NAME, data=migrated_records, schema=SCHEMA)
        print(f"✅ Migrated {len(migrated_records)} records to new schema in '{self.store_name}' store.")
        return new_table

    # -----------------------------------------------------------------------
    # CRUD Operations
    # -----------------------------------------------------------------------

    def save(
        self,
        text: str,
        memory_type: str = "learning",
        scope: str = "project",
        tags: str = "",
        confidence: float = 0.8,
        source_type: str = "conversation",
        source_ref: str = "",
        source_project: str = "",
        created_by: str = "unknown",
        metadata_json: Optional[dict] = None,
    ) -> str:
        """Save a new memory. Returns the generated ID."""
        table = self.get_table()
        now = datetime.now().isoformat()
        record_id = hashlib.sha256((text + now).encode()).hexdigest()

        record = {
            "id": record_id,
            "text": text,
            "memory_type": memory_type,
            "scope": scope,
            "tags": tags,
            "confidence": confidence,
            "status": "active",
            "superseded_by": "",
            "source_type": source_type,
            "source_ref": source_ref,
            "source_project": source_project,
            "created_by": created_by,
            "last_verified": now,
            "access_count": 0,
            "created_at": now,
            "updated_at": now,
            "metadata": json.dumps(metadata_json) if metadata_json else "{}",
        }

        table.add([record])
        return record_id

    def query(
        self,
        query_text: str,
        min_confidence: float = 0.0,
        include_deprecated: bool = False,
        limit: int = 20,
    ) -> list[dict]:
        """Search memories using full-text search with filtering."""
        table = self.get_table()

        try:
            table.create_fts_index(["text", "tags", "metadata"], replace=True)
            results_df = table.search(query_text).limit(limit * 2).to_pandas()
        except Exception:
            results_df = None

        # Fallback: if FTS failed or returned nothing, try string matching
        if results_df is None or results_df.empty:
            df = table.to_pandas()
            if df.empty:
                return []
            # Split query into words and match any word (OR logic)
            query_words = [w.strip() for w in query_text.split() if w.strip()]
            mask = df["text"].astype(str).apply(lambda x: False)  # Start with all-False
            for word in query_words:
                mask = mask | (
                    df["text"].astype(str).str.contains(word, case=False, na=False) |
                    df["tags"].astype(str).str.contains(word, case=False, na=False) |
                    df["metadata"].astype(str).str.contains(word, case=False, na=False)
                )
            results_df = df[mask].head(limit * 2)

        if results_df.empty:
            return []

        # Post-query filtering
        results = []
        for _, row in results_df.iterrows():
            # Confidence gate
            conf = row.get("confidence", 0.7)
            if conf is not None and conf < min_confidence:
                continue

            # Status filter
            status = row.get("status", "active")
            if not include_deprecated and status in ("deprecated", "archived", "superseded"):
                continue

            record = self._row_to_dict(row)
            results.append(record)

            if len(results) >= limit:
                break

        return results

    def get_all(self) -> list[dict]:
        """Return all memories (for stats, export, etc.)."""
        table = self.get_table()
        df = table.to_pandas()
        return [self._row_to_dict(row) for _, row in df.iterrows()]

    def get_by_id(self, record_id: str) -> Optional[dict]:
        """Retrieve a single memory by ID."""
        table = self.get_table()
        df = table.to_pandas()
        match = df[df["id"] == record_id]
        if match.empty:
            return None
        return self._row_to_dict(match.iloc[0])

    def update(
        self,
        record_id: str,
        text: Optional[str] = None,
        memory_type: Optional[str] = None,
        confidence: Optional[float] = None,
        status: Optional[str] = None,
        superseded_by: Optional[str] = None,
        tags: Optional[str] = None,
        metadata_json: Optional[dict] = None,
    ) -> bool:
        """Update an existing memory. Returns True if found and updated."""
        existing = self.get_by_id(record_id)
        if not existing:
            return False

        table = self.get_table()
        now = datetime.now().isoformat()

        # Build updated record (merge existing with provided values)
        updated = {
            "id": record_id,
            "text": text if text is not None else existing["text"],
            "memory_type": memory_type if memory_type is not None else existing["memory_type"],
            "scope": existing["scope"],
            "tags": tags if tags is not None else existing["tags"],
            "confidence": confidence if confidence is not None else existing["confidence"],
            "status": status if status is not None else existing["status"],
            "superseded_by": superseded_by if superseded_by is not None else existing["superseded_by"],
            "source_type": existing["source_type"],
            "source_ref": existing["source_ref"],
            "source_project": existing["source_project"],
            "created_by": existing["created_by"],
            "last_verified": existing["last_verified"],
            "access_count": existing["access_count"],
            "created_at": existing["created_at"],
            "updated_at": now,
            "metadata": json.dumps(metadata_json) if metadata_json is not None else existing["metadata"],
        }

        table.delete(f"id = '{record_id}'")
        table.add([updated])
        return True

    def delete(self, record_id: str) -> bool:
        """Delete a memory by ID. Returns True if found and deleted."""
        existing = self.get_by_id(record_id)
        if not existing:
            return False
        table = self.get_table()
        table.delete(f"id = '{record_id}'")
        return True

    def verify(self, record_id: str) -> bool:
        """Mark a memory as still-accurate (resets staleness timer)."""
        existing = self.get_by_id(record_id)
        if not existing:
            return False
        table = self.get_table()
        now = datetime.now().isoformat()
        existing["last_verified"] = now
        existing["updated_at"] = now
        table.delete(f"id = '{record_id}'")
        table.add([existing])
        return True

    def increment_access(self, record_id: str):
        """Bump the access counter for a retrieved memory."""
        existing = self.get_by_id(record_id)
        if not existing:
            return
        table = self.get_table()
        existing["access_count"] = existing.get("access_count", 0) + 1
        table.delete(f"id = '{record_id}'")
        table.add([existing])

    def export_parquet(self, path: str):
        """Export entire memory bank to a Parquet file."""
        table = self.get_table()
        df = table.to_pandas()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        df.to_parquet(path)
        return len(df)

    def get_stats(self) -> dict:
        """Return health statistics for this memory store."""
        all_memories = self.get_all()
        now = datetime.now()
        stale_threshold = now - timedelta(days=90)

        active = [m for m in all_memories if m.get("status") == "active"]
        stale = []
        for m in active:
            last_v = m.get("last_verified", "")
            if last_v:
                try:
                    verified_dt = datetime.fromisoformat(last_v)
                    if verified_dt < stale_threshold:
                        stale.append(m)
                except ValueError:
                    stale.append(m)
            else:
                stale.append(m)

        total = len(all_memories)
        return {
            "store": self.store_name,
            "total": total,
            "active": len(active),
            "stale": len(stale),
            "deprecated": len([m for m in all_memories if m.get("status") in ("deprecated", "archived")]),
            "superseded": len([m for m in all_memories if m.get("status") == "superseded"]),
            "health_pct": round(((len(active) - len(stale)) / total * 100) if total > 0 else 100, 1),
        }

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    @staticmethod
    def _row_to_dict(row) -> dict:
        """Convert a pandas row to a clean dictionary."""
        d = {}
        for field in SCHEMA.names:
            val = row.get(field, FIELD_DEFAULTS.get(field, ""))
            # Convert numpy/pandas types to Python natives
            if hasattr(val, "item"):
                val = val.item()
            if val is None:
                val = FIELD_DEFAULTS.get(field, "")
            d[field] = val
        return d
