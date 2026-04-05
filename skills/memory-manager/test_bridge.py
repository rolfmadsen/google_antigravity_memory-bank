"""
test_bridge.py — Test suite for the Federated AI Memory System.

Tests the full stack: memory_core → guardrails → federation → bridge CLI.
Uses MEMORY_BANK_DIR and MEMORY_GLOBAL_DIR env vars for test isolation.
"""

import json
import os
import sys

import pytest

# Ensure sibling modules are importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def temp_env(tmp_path):
    """Set up isolated project and global memory dirs."""
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / ".agent" / "memory-bank").mkdir(parents=True)

    global_dir = tmp_path / "global"
    global_dir.mkdir()

    # Set env vars for isolation
    os.environ["MEMORY_PROJECT_ROOT"] = str(project_dir)
    os.environ["MEMORY_BANK_DIR"] = str(project_dir / ".agent" / "memory-bank")
    # Monkey-patch the global brain path for testing
    os.environ["MEMORY_GLOBAL_DIR"] = str(global_dir)

    yield {
        "project_root": str(project_dir),
        "project_db": str(project_dir / ".agent" / "memory-bank"),
        "global_db": str(global_dir),
        "tmp": str(tmp_path),
    }

    # Cleanup env
    for key in ["MEMORY_PROJECT_ROOT", "MEMORY_BANK_DIR", "MEMORY_GLOBAL_DIR"]:
        os.environ.pop(key, None)


@pytest.fixture
def make_store(tmp_path):
    """Create isolated MemoryStore instances for unit testing."""
    from memory_core import MemoryStore

    counter = [0]

    def _make(name="test"):
        counter[0] += 1
        path = str(tmp_path / f"store_{counter[0]}")
        return MemoryStore(path, store_name=name)

    return _make


# ---------------------------------------------------------------------------
# Unit Tests: memory_core.py
# ---------------------------------------------------------------------------

class TestMemoryCore:
    def test_save_and_retrieve(self, make_store):
        store = make_store()
        rid = store.save(text="Always use OAuth 2.1 for auth.", memory_type="decision")
        assert rid, "save() should return an ID"

        record = store.get_by_id(rid)
        assert record is not None
        assert record["text"] == "Always use OAuth 2.1 for auth."
        assert record["memory_type"] == "decision"
        assert record["status"] == "active"
        assert record["confidence"] == pytest.approx(0.8, abs=0.01)

    def test_query_fts(self, make_store):
        store = make_store()
        store.save(text="Use LanceDB for vector storage", memory_type="decision")
        store.save(text="React components should be pure functions", memory_type="convention")

        results = store.query("LanceDB vector")
        assert len(results) >= 1
        assert any("LanceDB" in r["text"] for r in results)

    def test_update(self, make_store):
        store = make_store()
        rid = store.save(text="Old approach to caching")
        assert store.update(rid, text="New approach to caching", confidence=0.95)

        updated = store.get_by_id(rid)
        assert updated["text"] == "New approach to caching"
        assert updated["confidence"] == pytest.approx(0.95, abs=0.01)

    def test_delete(self, make_store):
        store = make_store()
        rid = store.save(text="Temporary note")
        assert store.delete(rid)
        assert store.get_by_id(rid) is None

    def test_verify_resets_staleness(self, make_store):
        store = make_store()
        rid = store.save(text="Auth uses JWT tokens")
        assert store.verify(rid)
        record = store.get_by_id(rid)
        assert record["last_verified"] != ""

    def test_stats(self, make_store):
        store = make_store()
        store.save(text="Memory A for stats test")
        store.save(text="Memory B for stats test")
        stats = store.get_stats()
        assert stats["total"] == 2
        assert stats["active"] == 2

    def test_export_parquet(self, make_store, tmp_path):
        store = make_store()
        store.save(text="Export test memory one")
        store.save(text="Export test memory two")
        path = str(tmp_path / "export.parquet")
        count = store.export_parquet(path)
        assert count == 2
        assert os.path.exists(path)

    def test_confidence_filter(self, make_store):
        store = make_store()
        store.save(text="High confidence decision about auth", confidence=0.95)
        store.save(text="Low confidence guess about auth", confidence=0.3)

        results = store.query("auth", min_confidence=0.5)
        assert len(results) == 1
        assert results[0]["confidence"] >= 0.5

    def test_status_filter(self, make_store):
        store = make_store()
        rid = store.save(text="Deprecated pattern for search")
        store.update(rid, status="deprecated")

        results = store.query("deprecated pattern")
        assert len(results) == 0  # Excluded by default

        results_with_deprecated = store.query("deprecated pattern", include_deprecated=True)
        assert len(results_with_deprecated) == 1


# ---------------------------------------------------------------------------
# Unit Tests: guardrails.py
# ---------------------------------------------------------------------------

class TestGuardrails:
    def test_validate_save_valid(self):
        from guardrails import validate_save_input
        result = validate_save_input(
            text="A valid memory text here",
            memory_type="decision",
            scope="project",
            confidence=0.8,
        )
        assert result["memory_type"] == "decision"
        assert result["confidence"] == 0.8

    def test_validate_save_invalid_type(self):
        from guardrails import validate_save_input, ValidationError
        with pytest.raises(ValidationError, match="memory_type"):
            validate_save_input(text="Some text here.", memory_type="invalid_type")

    def test_validate_save_empty_text(self):
        from guardrails import validate_save_input, ValidationError
        with pytest.raises(ValidationError, match="empty"):
            validate_save_input(text="")

    def test_validate_save_short_text(self):
        from guardrails import validate_save_input, ValidationError
        with pytest.raises(ValidationError, match="too short"):
            validate_save_input(text="Hi")

    def test_validate_confidence_range(self):
        from guardrails import validate_save_input, ValidationError
        with pytest.raises(ValidationError, match="Confidence"):
            validate_save_input(text="Valid text here.", confidence=1.5)

    def test_staleness_check(self):
        from guardrails import check_staleness
        memories = [
            {"last_verified": "2020-01-01T00:00:00", "status": "active"},
            {"last_verified": "", "status": "active"},
        ]
        result = check_staleness(memories, max_age_days=90)
        assert all(m["_stale"] for m in result)

    def test_near_duplicate_detection(self):
        from guardrails import check_near_duplicate
        existing = [
            {"text": "Always use OAuth 2.1 for authentication in this project", "status": "active"},
        ]
        # Very similar text
        dup = check_near_duplicate(
            "Always use OAuth 2.1 for authentication in this project",
            existing,
        )
        assert dup is not None

        # Different text
        no_dup = check_near_duplicate("Use PostgreSQL for the database layer", existing)
        assert no_dup is None


# ---------------------------------------------------------------------------
# Integration Tests: federation.py
# ---------------------------------------------------------------------------

class TestFederation:
    def _make_router(self, env):
        """Create a FederationRouter with test paths."""
        from federation import FederationRouter
        from memory_core import MemoryStore

        router = FederationRouter(project_root=env["project_root"])
        # Override stores with test paths
        router._project_store = MemoryStore(
            os.path.join(env["project_db"], "lancedb"),
            store_name="project:test",
        )
        router._global_store = MemoryStore(
            os.path.join(env["global_db"], "lancedb"),
            store_name="global",
        )
        return router

    def test_save_to_project(self, temp_env):
        router = self._make_router(temp_env)
        result = router.save(text="Project-specific auth pattern", scope="project")
        assert result["stored_in"] == "project"
        assert result["id"]

    def test_save_to_global(self, temp_env):
        router = self._make_router(temp_env)
        result = router.save(text="Global coding convention to always use", scope="global")
        assert result["stored_in"] == "global"

    def test_federated_query(self, temp_env):
        router = self._make_router(temp_env)
        router.save(text="Project uses React with TypeScript", scope="project")
        router.save(text="Global preference for TypeScript everywhere", scope="global")

        # Query both tiers
        response = router.query("TypeScript", scope="all")
        assert len(response["results"]) >= 2
        assert response["sources"]["project"] >= 1
        assert response["sources"]["global"] >= 1

    def test_project_only_query(self, temp_env):
        router = self._make_router(temp_env)
        router.save(text="Project uses PostgreSQL database", scope="project")
        router.save(text="Global default uses SQLite database", scope="global")

        response = router.query("database", scope="project")
        assert response["sources"]["global"] == 0
        assert response["sources"]["project"] >= 1

    def test_promote_to_global(self, temp_env):
        router = self._make_router(temp_env)
        save_result = router.save(text="Discovered pattern worth sharing globally", scope="project")
        promote_result = router.promote(save_result["id"])
        assert promote_result["promoted"]
        assert promote_result["global_id"]

        # Verify it's now in global
        response = router.query("pattern worth sharing", scope="global")
        assert len(response["results"]) >= 1

    def test_resolve_conflict(self, temp_env):
        router = self._make_router(temp_env)
        r1 = router.save(text="Use REST API for communication", scope="project")
        r2 = router.save(text="Use GraphQL for communication instead", scope="project")

        result = router.resolve_conflict(keep_id=r2["id"], supersede_id=r1["id"])
        assert result["resolved"]

        # The superseded memory should be hidden from normal queries
        response = router.query("REST API communication", scope="project")
        active_ids = [r["id"] for r in response["results"] if r["status"] == "active"]
        assert r1["id"] not in active_ids

    def test_status(self, temp_env):
        router = self._make_router(temp_env)
        router.save(text="Memory for status test result", scope="project")
        stats = router.status()
        assert "tiers" in stats
        assert stats["total_memories"] >= 1

    def test_export(self, temp_env):
        router = self._make_router(temp_env)
        router.save(text="Memory for export test pqt", scope="project")
        result = router.export(scope="project")
        assert "project" in result
        assert result["project"]["records"] >= 1

    def test_validation_error_on_save(self, temp_env):
        from guardrails import ValidationError
        router = self._make_router(temp_env)
        with pytest.raises(ValidationError):
            router.save(text="", scope="project")  # Empty text

    def test_update_and_delete(self, temp_env):
        router = self._make_router(temp_env)
        r = router.save(text="Temporary test memory to update then delete", scope="project")
        rid = r["id"]

        # Update
        update_result = router.update(rid, text="Updated memory content for test")
        assert update_result["updated"]

        # Delete
        delete_result = router.delete(rid)
        assert delete_result["deleted"]

    def test_verify(self, temp_env):
        router = self._make_router(temp_env)
        r = router.save(text="Memory to verify staleness reset", scope="project")
        result = router.verify(r["id"])
        assert result["verified"]


# ---------------------------------------------------------------------------
# Backward Compatibility
# ---------------------------------------------------------------------------

class TestBackwardCompat:
    def test_legacy_save_with_metadata_json(self, temp_env):
        """Ensure the old --metadata '{"type": "decision"}' pattern still works."""
        router = self._make_router(temp_env)
        result = router.save(
            text="Legacy save via metadata JSON format",
            metadata_json={"type": "decision", "module": "auth"},
        )
        assert result["id"]

    def _make_router(self, env):
        from federation import FederationRouter
        from memory_core import MemoryStore
        router = FederationRouter(project_root=env["project_root"])
        router._project_store = MemoryStore(
            os.path.join(env["project_db"], "lancedb"), store_name="project:test"
        )
        router._global_store = MemoryStore(
            os.path.join(env["global_db"], "lancedb"), store_name="global"
        )
        return router
