"""Tests for the vector index + KNN search service (spec §9.2 entries_vec, §11 vector half).

All offline via ``FakeEmbedder``: a note that lexically overlaps the query must rank ahead
of an unrelated note, tag/type pre-filters must constrain candidates, a dimension mismatch
must raise clearly, and removal must drop the vector row.
"""

import sqlite3

import pytest

from brain2.db.connection import open_user_db
from brain2.services.providers.embedder import FakeEmbedder
from brain2.services.vector import (
    index_entry_vector,
    remove_entry_vector,
    vector_search,
)

_EMBEDDER = FakeEmbedder()


@pytest.fixture
def conn(tmp_path):
    with open_user_db("vec-user", data_dir=tmp_path) as c:
        yield c


def _insert(conn: sqlite3.Connection, *, id, type="note", note=None):
    conn.execute(
        """
        INSERT INTO entries (id, url, original_url, title, note, note_source, content,
                             type, source_url, saved_at, updated_at, status, attempts)
        VALUES (?, NULL, NULL, NULL, ?, 'body', NULL, ?, NULL,
                '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z', 'active', 1)
        """,
        (id, note, type),
    )
    conn.commit()


def _tag(conn, entry_id, *tags):
    for t in tags:
        conn.execute("INSERT OR IGNORE INTO tags (name, description) VALUES (?, '')", (t,))
        conn.execute(
            "INSERT OR IGNORE INTO entry_tags (entry_id, tag) VALUES (?, ?)", (entry_id, t)
        )
    conn.commit()


def _embed_and_index(conn, entry_id, text):
    index_entry_vector(conn, entry_id, _EMBEDDER.embed(text))
    conn.commit()


def test_knn_returns_overlapping_note_first(conn):
    _insert(conn, id="a", note="fast async http client written in rust")
    _insert(conn, id="b", note="french cooking recipes for a dinner party")
    _embed_and_index(conn, "a", "fast async http client written in rust")
    _embed_and_index(conn, "b", "french cooking recipes for a dinner party")

    ids = vector_search(conn, _EMBEDDER.embed("rust http library"))
    assert ids[0] == "a"
    assert "b" not in ids[:1]


def test_remove_drops_the_vector(conn):
    _insert(conn, id="a", note="kubernetes deployment guide")
    _embed_and_index(conn, "a", "kubernetes deployment guide")
    assert conn.execute("SELECT count(*) FROM entries_vec WHERE id='a'").fetchone()[0] == 1

    remove_entry_vector(conn, "a")
    conn.commit()
    assert conn.execute("SELECT count(*) FROM entries_vec WHERE id='a'").fetchone()[0] == 0


def test_reindex_replaces_existing_vector(conn):
    _insert(conn, id="a", note="first note")
    _embed_and_index(conn, "a", "first note")
    _embed_and_index(conn, "a", "second different note")
    # Exactly one vector row per entry after re-enrichment.
    assert conn.execute("SELECT count(*) FROM entries_vec WHERE id='a'").fetchone()[0] == 1


def test_dimension_mismatch_raises(conn):
    _insert(conn, id="a")
    with pytest.raises(ValueError):
        index_entry_vector(conn, "a", [0.1, 0.2, 0.3])  # not 768-dim


def test_type_prefilter_constrains_knn(conn):
    _insert(conn, id="n", type="note", note="rust http server library")
    _insert(conn, id="p", type="page", note="rust http server library")
    _embed_and_index(conn, "n", "rust http server library")
    _embed_and_index(conn, "p", "rust http server library")

    ids = vector_search(conn, _EMBEDDER.embed("rust http"), type="note")
    assert ids == ["n"]


def test_tag_prefilter_requires_all_tags(conn):
    _insert(conn, id="a", note="graphql api design patterns")
    _insert(conn, id="b", note="graphql api design patterns")
    _embed_and_index(conn, "a", "graphql api design patterns")
    _embed_and_index(conn, "b", "graphql api design patterns")
    _tag(conn, "a", "graphql", "api")
    _tag(conn, "b", "graphql")

    ids = vector_search(conn, _EMBEDDER.embed("graphql api"), tags=["graphql", "api"])
    assert ids == ["a"]


def test_empty_index_returns_empty(conn):
    assert vector_search(conn, _EMBEDDER.embed("anything")) == []


def test_negative_limit_raises_clear_error(conn):
    # A negative k otherwise surfaces as an opaque vec0 OperationalError; guard it.
    with pytest.raises(ValueError, match="limit must be >= 0"):
        vector_search(conn, _EMBEDDER.embed("anything"), limit=-1)


def test_filter_recall_beyond_overfetch(conn):
    """Regression (Task 3): a rare tag's matches sit OUTSIDE the top ``limit*10`` nearest
    neighbours, so the old fixed-overfetch + Python post-filter dropped them silently. The
    escalating-k fix must still return them.

    We build many near-duplicate vectors close to the query (all untagged/other-tagged) so
    the two "rare"-tagged entries are far down the distance ranking, well past the
    ``limit * _PREFILTER_OVERFETCH`` overfetch window.
    """
    dim = _EMBEDDER.dimension
    # Query direction.
    query = [1.0] + [0.0] * (dim - 1)

    # 60 decoys tightly clustered around the query (near distance 0), none carry "rare".
    for i in range(60):
        vid = f"near{i}"
        _insert(conn, id=vid, note="near")
        v = [1.0, 0.0001 * (i + 1)] + [0.0] * (dim - 2)
        index_entry_vector(conn, vid, v)
    conn.commit()

    # Two far entries (orthogonal-ish direction) that DO carry the rare tag.
    for vid in ("rare1", "rare2"):
        _insert(conn, id=vid, note="rare")
        far = [0.0, 1.0] + [0.0] * (dim - 2)
        index_entry_vector(conn, vid, far)
        _tag(conn, vid, "rare")
    conn.commit()

    # With limit=5 the overfetch window is 50, but the rare matches rank ~61-62 by distance
    # among 62 vectors — beyond that window. The escalation must still surface them.
    ids = vector_search(conn, query, tags=["rare"], limit=5)
    assert set(ids) == {"rare1", "rare2"}


def test_knn_ranks_by_direction_not_magnitude(conn):
    """Lock in cosine-consistent ranking using RAW (un-normalized) vectors of differing
    magnitude — the production failure mode the FakeEmbedder's unit vectors masked.

    Query [1,0,0] must rank the same-direction (but larger) vector ABOVE the orthogonal
    one. Under plain L2 on un-normalized vectors the orthogonal [0,1,0] (L2 1.41) would
    wrongly beat the same-direction [10,0,0] (L2 9.0); with the schema set to cosine /
    normalized vectors, direction wins.
    """
    dim = _EMBEDDER.dimension
    same_dir = [10.0] + [0.0] * (dim - 1)
    orthogonal = [0.0, 1.0] + [0.0] * (dim - 2)

    _insert(conn, id="same", note="same")
    _insert(conn, id="orth", note="orth")
    index_entry_vector(conn, "same", same_dir)
    index_entry_vector(conn, "orth", orthogonal)
    conn.commit()

    query = [1.0] + [0.0] * (dim - 1)
    ids = vector_search(conn, query)
    assert ids[0] == "same"
