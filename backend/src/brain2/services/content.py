"""Conditional content persistence (spec §7.3).

Single source of truth for which entry types keep their raw captured text.
``page`` is re-fetchable via its URL, so its body is discarded; ``clip`` /
``conversation`` / ``note`` cannot be re-fetched, so their text is the value.
"""

# Types whose raw captured text cannot be re-fetched and must be persisted.
_CONTENT_PERSISTING_TYPES = frozenset({"clip", "conversation", "note"})


def persists_content(entry_type: str) -> bool:
    """Whether an entry of this type stores its raw captured text."""
    return entry_type in _CONTENT_PERSISTING_TYPES


def persisted_content(entry_type: str, captured_text: str | None) -> str | None:
    """Return the value to store in ``entries.content`` for this entry.

    Returns the captured text for persisting types and page type (temporarily),
    and ``None`` otherwise.
    """
    if entry_type == "page":
        return captured_text
    if not persists_content(entry_type):
        return None
    return captured_text
