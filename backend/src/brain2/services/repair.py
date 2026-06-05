"""Repair flow for failed (or active) entries (spec §7.4 PATCH /entries/{id}).

A failed entry is never a silent black hole: the user fills the note (and optionally tags)
and the entry re-enters processing using the user's text as the basis. This is the SAME
enrichment path the worker runs, just with the basis forced to the user's note and no
summarization/LLM-note-rewrite — the user's text IS the note (note_source='user').

Steps (spec §7.4): set note = user text, note_source = 'user', clear error_message, reset
attempts + next_retry_at, then embed the note -> run the auto-tagging pipeline grounded in
that note -> re-index FTS + vector -> status = 'active'. Reuses ``tagging.apply_tags`` (one
combined call, but with needs_summary=False so no note is rewritten), the M5 canonicalize,
and the M4 embedder; nothing is duplicated.
"""

import sqlite3
from datetime import datetime, timezone

from brain2.services.providers.embedder import EMBED_INPUT_MAX_CHARS, Embedder
from brain2.services.providers.tagger import Tagger
from brain2.services.structured_tags import StructuredTagSource
from brain2.services.tagging import apply_agent_tags, apply_tags
from brain2.services.vector import index_entry_vector


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def repair_entry(
    conn: sqlite3.Connection,
    entry_id: str,
    *,
    note: str,
    tags: list[str] | None = None,
    embedder: Embedder,
    tagger: Tagger,
    structured_source: StructuredTagSource,
    threshold: float,
    max_tags: int,
    nearest_limit: int,
) -> sqlite3.Row | None:
    """Repair an entry from a user-supplied note (spec §7.4). Returns the updated row, or None.

    Returns None if the id is absent. Otherwise the entry is re-enriched from ``note`` and
    flipped to ``active``. Optional ``tags`` are canonicalized and merged additively on top
    of the auto-tagged set. Counters are reconciled (the shared ``reconcile_tags`` path), so
    a re-repair with a changed tag set keeps counts equal to the live edge set.
    """
    exists = conn.execute("SELECT 1 FROM entries WHERE id = ?", (entry_id,)).fetchone()
    if exists is None:
        return None

    user_note = note.strip()
    now = _now_iso()
    # Reset processing state and write the user's note as the authored note (spec §7.4).
    conn.execute(
        """
        UPDATE entries
           SET note = ?, note_source = 'user', status = 'processing',
               error_message = NULL, attempts = 0, next_retry_at = NULL, updated_at = ?
         WHERE id = ?
        """,
        (user_note, now, entry_id),
    )

    # Re-enter the SAME enrichment path the worker uses, with the basis forced to the user's
    # note and needs_summary=False so the note is NOT rewritten (the user's text IS the note).
    apply_tags(
        conn,
        entry_id,
        basis_text=user_note,
        needs_summary=False,
        source=structured_source,
        tagger=tagger,
        embedder=embedder,
        threshold=threshold,
        max_tags=max_tags,
        nearest_limit=nearest_limit,
    )

    # Optional user-supplied tags: canonicalize-on-write + additive merge (spec §10/§7.4).
    if tags:
        apply_agent_tags(
            conn, entry_id, tags, embedder=embedder, threshold=threshold, max_tags=max_tags
        )

    # Embed the note into entries_vec (clear/replace) so the semantic leg reflects the repair.
    index_entry_vector(conn, entry_id, embedder.embed(user_note[:EMBED_INPUT_MAX_CHARS]))

    conn.execute(
        "UPDATE entries SET status = 'active', updated_at = ? WHERE id = ?",
        (_now_iso(), entry_id),
    )
    conn.commit()
    return conn.execute("SELECT * FROM entries WHERE id = ?", (entry_id,)).fetchone()
