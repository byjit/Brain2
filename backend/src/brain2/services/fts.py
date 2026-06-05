"""Keeps the ``entries_fts`` FTS5 index in lockstep with the ``entries`` table.

The BM25 index (spec §9.2) stores ``id`` (UNINDEXED), ``title``, ``tags_text`` and
``content``. This module is the single place that writes/removes those rows so the
entries service never duplicates the sync logic (DRY). It is intentionally tiny and
framework-free: it takes a live ``sqlite3.Connection`` and is unit-testable without HTTP.
"""

import sqlite3


def tags_text_for(conn: sqlite3.Connection, entry_id: str) -> str:
    """Space-joined tags for an entry (the denormalized ``tags_text`` column).

    Empty until auto-tagging lands in M5; kept here so a single helper owns the
    title+tags+content row shape for every write.
    """
    rows = conn.execute(
        "select tag from entry_tags where entry_id = ? order by tag", (entry_id,)
    ).fetchall()
    return " ".join(row[0] for row in rows)


def index_entry(
    conn: sqlite3.Connection,
    entry_id: str,
    title: str | None,
    content: str | None,
) -> None:
    """Insert or replace the entry's FTS row. Caller commits.

    FTS5 has no PK to UPSERT on, so we delete-then-insert to keep exactly one row
    per entry on both insert and update.
    """
    conn.execute("DELETE FROM entries_fts WHERE id = ?", (entry_id,))
    conn.execute(
        "INSERT INTO entries_fts (id, title, tags_text, content) VALUES (?, ?, ?, ?)",
        (entry_id, title or "", tags_text_for(conn, entry_id), content or ""),
    )


def remove_entry(conn: sqlite3.Connection, entry_id: str) -> None:
    """Remove the entry's FTS row. Caller commits."""
    conn.execute("DELETE FROM entries_fts WHERE id = ?", (entry_id,))
