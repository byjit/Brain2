"""PATCH repair: recover a failed entry from a user-supplied note (spec §7.4).

Offline with fakes. The repair flow sets note=user text, note_source='user', clears
error_message, resets attempts/next_retry_at, and re-enters processing using the user's
note as the basis: embed -> auto-tag grounded in that note (no summarization) -> re-index
FTS + vector -> status=active. Reuses the M5 tagging pipeline and the M4 embedder.
"""

import pytest

from brain2.db.connection import open_user_db
from brain2.services.providers.embedder import FakeEmbedder
from brain2.services.providers.tagger import FakeTagger, TagProposal
from brain2.services.repair import repair_entry
from brain2.services.structured_tags import FakeStructuredTagSource


@pytest.fixture
def conn(tmp_path):
    with open_user_db("repair-test", data_dir=tmp_path) as c:
        yield c


def _insert_failed(conn, entry_id, *, type="page", url=None, attempts=3):
    conn.execute(
        """
        INSERT INTO entries (id, url, original_url, title, note, note_source, content,
                             type, source_url, saved_at, updated_at, status, attempts,
                             next_retry_at, error_message)
        VALUES (?, ?, ?, NULL, NULL, 'body', NULL, ?, NULL, '2026-01-01T00:00:00Z',
                '2026-01-01T00:00:00Z', 'failed', ?, '2026-01-01T01:00:00Z',
                'no extractable content')
        """,
        (entry_id, url, url, type, attempts),
    )
    conn.commit()


def _providers(tags):
    embedder = FakeEmbedder()
    tagger = FakeTagger(
        result=TagProposal(note="", tags=tags, new_tag_descriptions={t: f"Concept {t}" for t in tags})
    )
    return embedder, tagger, FakeStructuredTagSource()


def test_repair_failed_entry_reenriches_from_user_note(conn):
    _insert_failed(conn, "e1", type="page", url="https://x.test/blocked")
    embedder, tagger, source = _providers(["python", "web"])

    row = repair_entry(
        conn, "e1", note="My own description of this page about python web frameworks.",
        embedder=embedder, tagger=tagger, structured_source=source,
        threshold=0.90, max_tags=5, nearest_limit=10,
    )

    assert row["status"] == "active"
    assert row["note"] == "My own description of this page about python web frameworks."
    assert row["note_source"] == "user"
    assert row["error_message"] is None
    assert row["attempts"] == 0
    assert row["next_retry_at"] is None
    # Auto-tagging ran, grounded in the user note (no summarization -> note unchanged).
    edges = {r[0] for r in conn.execute("SELECT tag FROM entry_tags WHERE entry_id='e1'")}
    assert edges == {"python", "web"}
    # The note was embedded into entries_vec and FTS re-indexed.
    assert conn.execute("SELECT count(*) FROM entries_vec WHERE id='e1'").fetchone()[0] == 1
    tags_text = conn.execute("SELECT tags_text FROM entries_fts WHERE id='e1'").fetchone()[0]
    assert set(tags_text.split()) == {"python", "web"}
    # No LLM summary rewrite happened (the user's text IS the note).
    assert tagger.calls[0].needs_summary is False


def test_repair_reconciles_counters_when_tags_change(conn):
    """Re-repairing with a different tag set reconciles counters (spec §7.4)."""
    _insert_failed(conn, "e1", type="note")
    embedder = FakeEmbedder()
    source = FakeStructuredTagSource()

    repair_entry(
        conn, "e1", note="first", embedder=embedder,
        tagger=FakeTagger(result=TagProposal(note="", tags=["rust", "cli"],
                                             new_tag_descriptions={"rust": "Rust", "cli": "CLI"})),
        structured_source=source, threshold=0.90, max_tags=5, nearest_limit=10,
    )
    assert conn.execute("SELECT count FROM tags WHERE name='cli'").fetchone()[0] == 1

    # Repair again with a different set: drops cli, adds wasm.
    repair_entry(
        conn, "e1", note="second", embedder=embedder,
        tagger=FakeTagger(result=TagProposal(note="", tags=["rust", "wasm"],
                                             new_tag_descriptions={"rust": "Rust", "wasm": "WASM"})),
        structured_source=source, threshold=0.90, max_tags=5, nearest_limit=10,
    )
    edges = {r[0] for r in conn.execute("SELECT tag FROM entry_tags WHERE entry_id='e1'")}
    assert edges == {"rust", "wasm"}
    assert conn.execute("SELECT count FROM tags WHERE name='cli'").fetchone()[0] == 0
    assert conn.execute("SELECT count FROM tags WHERE name='rust'").fetchone()[0] == 1
    assert conn.execute("SELECT count FROM tags WHERE name='wasm'").fetchone()[0] == 1


def test_repair_accepts_optional_explicit_tags(conn):
    """The user may supply tags directly; they are canonicalized + merged (spec §7.4)."""
    _insert_failed(conn, "e1", type="note")
    embedder = FakeEmbedder()
    # Tagger proposes nothing extra; the user's explicit tags must still land.
    tagger = FakeTagger(result=TagProposal(note="", tags=[], new_tag_descriptions={}))

    repair_entry(
        conn, "e1", note="hand-written note", tags=["Rust", "Async"],
        embedder=embedder, tagger=tagger, structured_source=FakeStructuredTagSource(),
        threshold=0.90, max_tags=5, nearest_limit=10,
    )
    edges = {r[0] for r in conn.execute("SELECT tag FROM entry_tags WHERE entry_id='e1'")}
    assert edges == {"rust", "async"}
