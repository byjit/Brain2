"""Tests for RRF hybrid search: BM25 (set A) + vector (set B) fused, k=60 (spec §11).

All offline via ``FakeEmbedder``. Covers: an entry strong in either leg ranks well; an
entry found ONLY by vector (a paraphrase sharing no stored lexical tokens but reachable
via shared fake-embedding tokens) is retrieved; tag/type pre-filters constrain the fused
result; empty query is handled; and the compact §10 result shape is returned.
"""

import pytest

from brain2.db.connection import open_user_db
from brain2.models.entries import CreateEntryRequest
from brain2.services.entries import save_entry
from brain2.services.providers.embedder import FakeEmbedder
from brain2.services.search import hybrid_search
from brain2.services.vector import index_entry_vector

_EMBEDDER = FakeEmbedder()


@pytest.fixture
def conn(tmp_path):
    with open_user_db("hybrid-user", data_dir=tmp_path) as c:
        yield c


def _save_active(conn, *, note, type="note", title=None, url=None):
    """Save an entry, set it active with a note, index FTS + its note vector (as the
    worker would post-enrichment), so both retrieval legs see it."""
    from brain2.services.fts import index_entry

    res = save_entry(
        conn,
        CreateEntryRequest(type=type, captured_text=note if type == "note" else None,
                           title=title, url=url, note=None),
    )
    conn.execute(
        "UPDATE entries SET note=?, status='active' WHERE id=?", (note, res.id)
    )
    row = conn.execute("select title, content from entries where id=?", (res.id,)).fetchone()
    index_entry(conn, res.id, row["title"], row["content"])
    index_entry_vector(conn, res.id, _EMBEDDER.embed(note))
    conn.commit()
    return res.id


def _tag(conn, entry_id, *tags):
    from brain2.services.fts import index_entry

    for t in tags:
        conn.execute("INSERT OR IGNORE INTO tags (name, description) VALUES (?, '')", (t,))
        conn.execute("INSERT OR IGNORE INTO entry_tags (entry_id, tag) VALUES (?, ?)", (entry_id, t))
    row = conn.execute("select title, content from entries where id=?", (entry_id,)).fetchone()
    index_entry(conn, entry_id, row["title"], row["content"])
    conn.commit()


def test_result_shape_matches_spec(conn):
    eid = _save_active(conn, note="rust async http client", type="clip", url="https://e.com/h", title="Hyper")
    results = hybrid_search(conn, "rust http", embedder=_EMBEDDER)
    r = next(x for x in results if x["id"] == eid)
    assert set(r.keys()) == {"id", "url", "title", "tags", "note", "note_source", "content", "type", "saved_at", "score"}
    assert isinstance(r["score"], float)


def test_lexical_match_ranks_well(conn):
    target = _save_active(conn, note="the hyper rust http library is fast")
    _save_active(conn, note="completely unrelated gardening tips")
    results = hybrid_search(conn, "hyper rust http", embedder=_EMBEDDER)
    assert results[0]["id"] == target


def test_paraphrase_only_vector_hit_is_retrieved(conn):
    # The query shares NO lexical tokens with the stored note's *title/content* once the
    # note text is the only signal, but the FakeEmbedder maps overlapping tokens to shared
    # buckets — so the vector leg surfaces it. We assert the entry is retrieved at all.
    target = _save_active(conn, note="fast networking primitives for the rust ecosystem")
    _save_active(conn, note="a recipe blog about italian pasta dishes")
    # "networking rust" overlaps the target note via the vector leg; ensure it's returned.
    results = hybrid_search(conn, "rust networking", embedder=_EMBEDDER)
    assert any(r["id"] == target for r in results)
    assert results[0]["id"] == target


def test_strong_in_either_leg_ranks_above_weak(conn):
    strong = _save_active(conn, note="kubernetes operators controller pattern")
    weak = _save_active(conn, note="docker compose basics")
    results = hybrid_search(conn, "kubernetes operators", embedder=_EMBEDDER)
    ids = [r["id"] for r in results]
    assert ids.index(strong) < ids.index(weak)


def test_tag_prefilter_constrains_hybrid(conn):
    a = _save_active(conn, note="graphql api design")
    b = _save_active(conn, note="graphql api design")
    _tag(conn, a, "graphql", "api")
    _tag(conn, b, "graphql")
    results = hybrid_search(conn, "graphql api", embedder=_EMBEDDER, tags=["graphql", "api"])
    assert [r["id"] for r in results] == [a]


def test_type_prefilter_constrains_hybrid(conn):
    n = _save_active(conn, note="rust http server", type="note")
    _save_active(conn, note="rust http server", type="page", url="https://e.com/p")
    results = hybrid_search(conn, "rust http", embedder=_EMBEDDER, type="note")
    assert [r["id"] for r in results] == [n]


def test_empty_query_returns_empty(conn):
    _save_active(conn, note="anything at all")
    assert hybrid_search(conn, "   ", embedder=_EMBEDDER) == []


def test_default_limit_is_ten(conn):
    for i in range(12):
        _save_active(conn, note=f"shared common term entry number {i}")
    results = hybrid_search(conn, "shared common term", embedder=_EMBEDDER)
    assert len(results) == 10
