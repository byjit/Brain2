"""Delete removes an entry and ALL derived data + symmetrically decrements counters (spec §10, §9.2).

Offline. Builds a tagged entry via the M5 pipeline, then deletes it and asserts the
entry, FTS row, vector row, and tag edges are gone, that tags.count and
tag_cooccurrence.count are decremented by the exact inverse of M5's increment (floored at
0), that a tag whose count hits 0 is LEFT in place WITH its tags_vec embedding (still
useful for canonicalization, spec §9.2), and that deleting a missing id returns False.
"""

import sqlite3

import pytest

from brain2.db.connection import open_user_db
from brain2.services.entries import delete_entry
from brain2.services.providers.embedder import FakeEmbedder
from brain2.services.providers.tagger import FakeTagger, TagProposal
from brain2.services.structured_tags import FakeStructuredTagSource
from brain2.services.tagging import apply_tags


@pytest.fixture
def conn(tmp_path):
    with open_user_db("delete-test", data_dir=tmp_path) as c:
        yield c


def _insert_entry(conn, entry_id, *, type="page", url=None, note="", content=None):
    conn.execute(
        """
        INSERT INTO entries (id, url, original_url, title, note, note_source, content,
                             type, source_url, saved_at, updated_at, status, attempts)
        VALUES (?, ?, ?, NULL, ?, 'body', ?, ?, NULL, '2026-01-01T00:00:00Z',
                '2026-01-01T00:00:00Z', 'active', 1)
        """,
        (entry_id, url, url, note, content, type),
    )
    conn.commit()


def _tag_entry(conn, entry_id, tags):
    embedder = FakeEmbedder()
    tagger = FakeTagger(
        result=TagProposal(
            note="", tags=tags, new_tag_descriptions={t: f"Concept {t}" for t in tags}
        )
    )
    # Embed the note into entries_vec too, so we can assert the vector row is removed.
    from brain2.services.vector import index_entry_vector

    apply_tags(
        conn, entry_id, basis_text="basis", needs_summary=False,
        source=FakeStructuredTagSource(), tagger=tagger, embedder=embedder,
        threshold=0.90, max_tags=5, nearest_limit=10,
    )
    index_entry_vector(conn, entry_id, embedder.embed("note text"))
    conn.commit()


def test_delete_missing_id_returns_false(conn):
    assert delete_entry(conn, "nope") is False


def test_delete_removes_entry_fts_vector_and_edges(conn):
    _insert_entry(conn, "e1", note="python web async")
    _tag_entry(conn, "e1", ["python", "web", "async"])

    assert delete_entry(conn, "e1") is True

    assert conn.execute("SELECT count(*) FROM entries WHERE id='e1'").fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM entries_fts WHERE id='e1'").fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM entries_vec WHERE id='e1'").fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM entry_tags WHERE entry_id='e1'").fetchone()[0] == 0


def test_delete_decrements_tag_counts_and_cooccurrence(conn):
    # Two entries share python+web; e2 also has async. After deleting e1, the shared
    # tags drop by one and the e1-only co-occurrence pairs drop.
    _insert_entry(conn, "e1", note="a")
    _insert_entry(conn, "e2", note="b")
    _tag_entry(conn, "e1", ["python", "web"])
    _tag_entry(conn, "e2", ["python", "web", "async"])

    assert conn.execute("SELECT count FROM tags WHERE name='python'").fetchone()[0] == 2
    assert conn.execute("SELECT count FROM tags WHERE name='web'").fetchone()[0] == 2
    # (python, web) co-occur in both entries -> count 2.
    assert conn.execute(
        "SELECT count FROM tag_cooccurrence WHERE tag_a='python' AND tag_b='web'"
    ).fetchone()[0] == 2

    delete_entry(conn, "e1")

    assert conn.execute("SELECT count FROM tags WHERE name='python'").fetchone()[0] == 1
    assert conn.execute("SELECT count FROM tags WHERE name='web'").fetchone()[0] == 1
    assert conn.execute("SELECT count FROM tags WHERE name='async'").fetchone()[0] == 1
    # (python, web) drops to 1 (still in e2); pairs only in e2 are untouched.
    assert conn.execute(
        "SELECT count FROM tag_cooccurrence WHERE tag_a='python' AND tag_b='web'"
    ).fetchone()[0] == 1
    assert conn.execute(
        "SELECT count FROM tag_cooccurrence WHERE tag_a='async' AND tag_b='python'"
    ).fetchone()[0] == 1


def test_zero_count_tag_left_in_place_with_vector(conn):
    _insert_entry(conn, "e1", note="solo")
    _tag_entry(conn, "e1", ["solo"])  # only e1 has this tag

    assert conn.execute("SELECT count FROM tags WHERE name='solo'").fetchone()[0] == 1

    delete_entry(conn, "e1")

    # The tag row stays (count floored at 0) and keeps its tags_vec embedding (spec §9.2).
    assert conn.execute("SELECT count FROM tags WHERE name='solo'").fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM tags_vec WHERE name='solo'").fetchone()[0] == 1


def test_cooccurrence_floors_at_zero(conn):
    _insert_entry(conn, "e1", note="x")
    _tag_entry(conn, "e1", ["alpha", "beta"])
    delete_entry(conn, "e1")
    # The only pair drops to 0 (no negative counts).
    row = conn.execute(
        "SELECT count FROM tag_cooccurrence WHERE tag_a='alpha' AND tag_b='beta'"
    ).fetchone()
    assert row is None or row[0] == 0
