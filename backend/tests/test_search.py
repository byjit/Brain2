"""BM25 keyword retrieval over entries_fts (spec §11 BM25 half, §10 retrieve).

Vector/RRF is M4; here retrieve ranks purely by FTS5 bm25() over title+tags_text+content,
with optional tag/type pre-filters and a result limit.
"""

import pytest

from brain2.db.connection import open_user_db
from brain2.models.entries import CreateEntryRequest
from brain2.services.entries import save_entry
from brain2.services.search import search_entries


@pytest.fixture
def conn(tmp_path):
    with open_user_db("search-user", data_dir=tmp_path) as c:
        yield c


def _tag(conn, entry_id, *tags):
    """Attach tags to an entry and re-index its FTS tags_text (M5 does this for real)."""
    from brain2.services.fts import index_entry

    for t in tags:
        conn.execute("INSERT OR IGNORE INTO tags (name, description) VALUES (?, '')", (t,))
        conn.execute("INSERT OR IGNORE INTO entry_tags (entry_id, tag) VALUES (?, ?)", (entry_id, t))
    row = conn.execute("select title, content from entries where id = ?", (entry_id,)).fetchone()
    index_entry(conn, entry_id, row["title"], row["content"])
    conn.commit()


def test_bm25_ranks_more_relevant_entry_first(conn):
    a = save_entry(conn, CreateEntryRequest(type="note", captured_text="rust async runtime tokio"))
    b = save_entry(conn, CreateEntryRequest(type="note", captured_text="python web framework flask"))
    results = search_entries(conn, "rust")
    assert results[0]["id"] == a.id
    assert all(r["id"] != b.id for r in results[:1])


def test_result_shape_matches_spec(conn):
    res = save_entry(
        conn,
        CreateEntryRequest(type="clip", url="https://ex.com/x", title="Hyper HTTP", captured_text="fast http for rust"),
    )
    results = search_entries(conn, "http")
    r = results[0]
    assert set(r.keys()) == {"id", "url", "title", "tags", "note", "content", "type", "saved_at", "score"}
    assert r["id"] == res.id
    assert r["title"] == "Hyper HTTP"
    assert r["type"] == "clip"
    assert isinstance(r["tags"], list)
    assert isinstance(r["score"], float)


def test_type_prefilter(conn):
    note = save_entry(conn, CreateEntryRequest(type="note", captured_text="kubernetes deployment guide"))
    save_entry(conn, CreateEntryRequest(type="page", url="https://ex.com/k", title="kubernetes operators"))
    results = search_entries(conn, "kubernetes", type="note")
    assert [r["id"] for r in results] == [note.id]


def test_tag_prefilter_requires_all_tags(conn):
    a = save_entry(conn, CreateEntryRequest(type="note", captured_text="graphql api design"))
    b = save_entry(conn, CreateEntryRequest(type="note", captured_text="graphql schema stitching"))
    _tag(conn, a.id, "graphql", "api")
    _tag(conn, b.id, "graphql")
    # Only entries carrying BOTH tags survive the pre-filter.
    results = search_entries(conn, "graphql", tags=["graphql", "api"])
    assert [r["id"] for r in results] == [a.id]


def test_tags_appear_in_result(conn):
    res = save_entry(conn, CreateEntryRequest(type="note", captured_text="rust ownership model"))
    _tag(conn, res.id, "rust", "memory")
    results = search_entries(conn, "ownership")
    assert sorted(results[0]["tags"]) == ["memory", "rust"]


def test_limit_caps_results(conn):
    for i in range(5):
        save_entry(conn, CreateEntryRequest(type="note", captured_text=f"common keyword entry {i}"))
    results = search_entries(conn, "common", limit=3)
    assert len(results) == 3


def test_default_limit_is_ten(conn):
    for i in range(12):
        save_entry(conn, CreateEntryRequest(type="note", captured_text=f"shared term doc {i}"))
    results = search_entries(conn, "shared")
    assert len(results) == 10


@pytest.mark.parametrize(
    "query",
    ['rust "http', "NEAR(a b)", "title:foo", "a AND b OR c", "foo*", "*", '""', "a:b:c", "(unbalanced"],
)
def test_fts_special_characters_do_not_crash(conn, query):
    save_entry(conn, CreateEntryRequest(type="note", captured_text="rust http server"))
    # Must not raise an FTS5 syntax error; returns a (possibly empty) list.
    results = search_entries(conn, query)
    assert isinstance(results, list)


def test_empty_query_returns_empty(conn):
    save_entry(conn, CreateEntryRequest(type="note", captured_text="anything"))
    assert search_entries(conn, "   ") == []


def test_note_less_hit_surfaces_matched_content(conn):
    # Pre-enrichment (M2) a clip's body lives in content while note stays NULL until
    # summarization (M5). The hit must still carry the readable body it matched on,
    # not just id+score (spec §10, §15).
    res = save_entry(
        conn,
        CreateEntryRequest(
            type="clip",
            url="https://ex.com/clip",
            captured_text="distinctive searchable body",
            source_url="https://ex.com/clip",
        ),
    )
    results = search_entries(conn, "distinctive")
    hit = next(r for r in results if r["id"] == res.id)
    assert hit["note"] is None
    assert hit["content"] == "distinctive searchable body"


def test_cjk_substring_is_searchable(conn):
    # unicode61 stores a contiguous CJK run as one token, so a partial-word query
    # never matches. The trigram tokenizer indexes 3-char substrings across scripts,
    # so a substring (>=3 chars) of a CJK run matches (spec §15 CJK recall).
    res = save_entry(
        conn, CreateEntryRequest(type="note", captured_text="東京タワー観光案内")
    )
    results = search_entries(conn, "タワー観")
    assert any(r["id"] == res.id for r in results)
