"""Shared compact-entry projection for read paths (spec §10 result shape).

``retrieve`` (search) and ``list`` build the same compact dict — ``id, url, title,
tags, note, note_source, content, type, saved_at`` — and the ranked retrieve legs
append a relevance ``score``. ``note_source`` (spec §7.3) tells the consuming agent
how shallow the note is (body summary vs og teaser vs bare title vs user-authored),
so it can calibrate trust before acting on it. Centralizing the row→dict mapping
here keeps the two surfaces from drifting (DRY).
"""

import sqlite3


def tags_for(conn: sqlite3.Connection, entry_id: str) -> list[str]:
    """Tags attached to an entry, sorted, for the compact result shape."""
    rows = conn.execute(
        "SELECT tag FROM entry_tags WHERE entry_id = ? ORDER BY tag", (entry_id,)
    ).fetchall()
    return [row[0] for row in rows]


def compact_entry(conn: sqlite3.Connection, row: sqlite3.Row, *, score: float | None = None) -> dict:
    """Build the spec §10 compact result dict from an ``entries`` row.

    ``row`` must expose ``id, url, title, note, note_source, content, type, saved_at``.
    A ``score`` is included only when supplied (the ranked retrieve paths);
    deterministic list results omit it.
    """
    result = {
        "id": row["id"],
        "url": row["url"],
        "title": row["title"],
        "tags": tags_for(conn, row["id"]),
        "note": row["note"],
        "note_source": row["note_source"],
        "content": row["content"],
        "type": row["type"],
        "saved_at": row["saved_at"],
    }
    if score is not None:
        result["score"] = score
    return result
