"""
guardrails.py — Validation & anti-hallucination layer for the AI Memory System.

Enforces schema constraints, confidence gating, staleness detection,
and contradiction checks. All write operations should pass through
this module before reaching memory_core.
"""

from datetime import datetime, timedelta
from typing import Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_MEMORY_TYPES = {"decision", "learning", "bug", "pattern", "convention", "warning"}
VALID_SCOPES = {"global", "project", "module"}
VALID_STATUSES = {"active", "superseded", "deprecated", "archived"}
VALID_SOURCE_TYPES = {"conversation", "commit", "manual", "import"}

DEFAULT_STALENESS_DAYS = 90
DEFAULT_MIN_CONFIDENCE = 0.0
DUPLICATE_SIMILARITY_THRESHOLD = 0.95  # For future embedding-based dedup


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class ValidationError(Exception):
    """Raised when input fails validation."""
    pass


def validate_save_input(
    text: str,
    memory_type: str = "learning",
    scope: str = "project",
    confidence: float = 0.8,
    source_type: str = "conversation",
    tags: str = "",
) -> dict:
    """
    Validate and normalize inputs for saving a memory.
    Returns a dict of cleaned values. Raises ValidationError on invalid input.
    """
    errors = []

    # Text must be non-empty and substantive
    if not text or not text.strip():
        errors.append("Text cannot be empty.")
    elif len(text.strip()) < 10:
        errors.append("Text is too short to be a useful memory (min 10 characters).")

    # memory_type
    memory_type = memory_type.lower().strip()
    if memory_type not in VALID_MEMORY_TYPES:
        errors.append(
            f"Invalid memory_type '{memory_type}'. "
            f"Must be one of: {', '.join(sorted(VALID_MEMORY_TYPES))}"
        )

    # scope
    scope = scope.lower().strip()
    if scope not in VALID_SCOPES:
        errors.append(
            f"Invalid scope '{scope}'. "
            f"Must be one of: {', '.join(sorted(VALID_SCOPES))}"
        )

    # confidence
    if not isinstance(confidence, (int, float)):
        errors.append("Confidence must be a number.")
    elif confidence < 0.0 or confidence > 1.0:
        errors.append(f"Confidence must be between 0.0 and 1.0, got {confidence}.")

    # source_type
    source_type = source_type.lower().strip()
    if source_type not in VALID_SOURCE_TYPES:
        errors.append(
            f"Invalid source_type '{source_type}'. "
            f"Must be one of: {', '.join(sorted(VALID_SOURCE_TYPES))}"
        )

    # tags — normalize
    if tags:
        tags = ",".join(t.strip() for t in tags.split(",") if t.strip())

    if errors:
        raise ValidationError(" | ".join(errors))

    return {
        "text": text.strip(),
        "memory_type": memory_type,
        "scope": scope,
        "confidence": float(confidence),
        "source_type": source_type,
        "tags": tags,
    }


def validate_update_input(
    status: Optional[str] = None,
    confidence: Optional[float] = None,
    memory_type: Optional[str] = None,
) -> dict:
    """Validate partial update fields. Returns cleaned values."""
    errors = []
    cleaned = {}

    if status is not None:
        status = status.lower().strip()
        if status not in VALID_STATUSES:
            errors.append(
                f"Invalid status '{status}'. "
                f"Must be one of: {', '.join(sorted(VALID_STATUSES))}"
            )
        cleaned["status"] = status

    if confidence is not None:
        if not isinstance(confidence, (int, float)) or confidence < 0.0 or confidence > 1.0:
            errors.append(f"Confidence must be between 0.0 and 1.0, got {confidence}.")
        cleaned["confidence"] = float(confidence)

    if memory_type is not None:
        memory_type = memory_type.lower().strip()
        if memory_type not in VALID_MEMORY_TYPES:
            errors.append(
                f"Invalid memory_type '{memory_type}'. "
                f"Must be one of: {', '.join(sorted(VALID_MEMORY_TYPES))}"
            )
        cleaned["memory_type"] = memory_type

    if errors:
        raise ValidationError(" | ".join(errors))

    return cleaned


# ---------------------------------------------------------------------------
# Post-Query Filters & Warnings
# ---------------------------------------------------------------------------

def check_staleness(memories: list[dict], max_age_days: int = DEFAULT_STALENESS_DAYS) -> list[dict]:
    """
    Annotate memories with a '_stale' flag if they haven't been verified
    within max_age_days. Does NOT remove them — just warns.
    """
    threshold = datetime.now() - timedelta(days=max_age_days)

    for memory in memories:
        last_v = memory.get("last_verified", "")
        is_stale = False
        if last_v:
            try:
                verified_dt = datetime.fromisoformat(last_v)
                is_stale = verified_dt < threshold
            except ValueError:
                is_stale = True
        else:
            # No verification timestamp — consider stale
            is_stale = True

        memory["_stale"] = is_stale
        if is_stale:
            memory["_warning"] = (
                f"⚠️ This memory hasn't been verified since "
                f"{last_v or 'never'}. It may be outdated."
            )

    return memories


def filter_by_confidence(memories: list[dict], min_confidence: float) -> list[dict]:
    """Remove memories below the confidence threshold."""
    if min_confidence <= 0.0:
        return memories
    return [m for m in memories if m.get("confidence", 0.7) >= min_confidence]


def detect_contradictions(
    new_text: str,
    existing_memories: list[dict],
) -> list[dict]:
    """
    Basic contradiction detection using keyword overlap.
    Returns a list of potentially conflicting memories.

    Phase 3 upgrade: Use embedding cosine similarity for much better detection.
    """
    # Simple heuristic: find memories that share significant word overlap
    # but have different conclusions (indicated by negation words)
    new_words = set(new_text.lower().split())
    negation_signals = {"not", "don't", "doesn't", "shouldn't", "avoid", "never",
                        "instead", "rather", "but", "however", "replaced", "deprecated"}

    conflicts = []
    for memory in existing_memories:
        if memory.get("status") != "active":
            continue

        existing_words = set(memory.get("text", "").lower().split())
        overlap = new_words & existing_words

        # Significant overlap (shared topic) + negation present = potential conflict
        if len(overlap) >= 3:
            combined = new_words | existing_words
            has_negation = bool(combined & negation_signals)
            if has_negation:
                conflicts.append(memory)

    return conflicts


def check_near_duplicate(
    new_text: str,
    existing_memories: list[dict],
) -> Optional[dict]:
    """
    Check if new_text is a near-duplicate of an existing memory.
    Returns the duplicate memory if found, None otherwise.

    Phase 1: Uses simple Jaccard similarity on words.
    Phase 3 upgrade: Use embedding cosine similarity.
    """
    new_words = set(new_text.lower().split())
    if not new_words:
        return None

    for memory in existing_memories:
        if memory.get("status") != "active":
            continue

        existing_words = set(memory.get("text", "").lower().split())
        if not existing_words:
            continue

        # Jaccard similarity
        intersection = len(new_words & existing_words)
        union = len(new_words | existing_words)
        similarity = intersection / union if union > 0 else 0

        if similarity > DUPLICATE_SIMILARITY_THRESHOLD:
            return memory

    return None
