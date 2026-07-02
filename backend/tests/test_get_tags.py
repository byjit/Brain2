"""get_tags service: paged tag listing with counts, descriptions, co-occurrence (spec §10).

Offline. Asserts the exact §10 response shape (tag, description, count, co_occurs_with),
the two sorts ('count' default desc, 'name' asc), the limit, and that co_occurs_with lists
the top co-occurring tag names ordered by co-occurrence count.
"""

import pytest

from brain2.db.connection import open_user_db
from brain2.services.tags_service import list_tags


@pytest.fixture
def conn(tmp_path):
    with open_user_db("get-tags-test", data_dir=tmp_path) as c:
        yield c


def _seed_tag(conn, name, description, count):
    conn.execute(
        "INSERT INTO tags (name, description, count) VALUES (?, ?, ?)",
        (name, description, count),
    )


def _seed_cooc(conn, a, b, count):
    tag_a, tag_b = (a, b) if a < b else (b, a)
    conn.execute(
        "INSERT INTO tag_cooccurrence (tag_a, tag_b, count) VALUES (?, ?, ?)",
        (tag_a, tag_b, count),
    )


def _seed(conn):
    _seed_tag(conn, "rust", "Rust programming language", 14)
    _seed_tag(conn, "http", "Hypertext transfer protocol", 9)
    _seed_tag(conn, "async", "Asynchronous concurrency", 7)
    _seed_tag(conn, "wasm", "WebAssembly", 3)
    _seed_tag(conn, "cli", "Command-line tooling", 5)
    # rust co-occurs with http(8), async(6), wasm(2), cli(4)
    _seed_cooc(conn, "rust", "http", 8)
    _seed_cooc(conn, "rust", "async", 6)
    _seed_cooc(conn, "rust", "wasm", 2)
    _seed_cooc(conn, "rust", "cli", 4)
    conn.commit()


def test_response_shape_and_default_sort_by_count(conn):
    _seed(conn)
    rows = list_tags(conn)
    # Default sort is count desc.
    assert [r["tag"] for r in rows] == ["rust", "http", "async", "cli", "wasm"]
    top = rows[0]
    assert set(top) == {"tag", "description", "count", "co_occurs_with"}
    assert top["tag"] == "rust"
    assert top["description"] == "Rust programming language"
    assert top["count"] == 14
    # co_occurs_with: top co-occurring tag names, ordered by co-occurrence count desc.
    assert top["co_occurs_with"] == ["http", "async", "cli", "wasm"]


def test_sort_by_name(conn):
    _seed(conn)
    rows = list_tags(conn, sort="name")
    assert [r["tag"] for r in rows] == ["async", "cli", "http", "rust", "wasm"]


def test_limit_paging(conn):
    _seed(conn)
    rows = list_tags(conn, limit=2)
    assert len(rows) == 2
    assert [r["tag"] for r in rows] == ["rust", "http"]


def test_cooccurrence_is_symmetric_lookup(conn):
    """A tag stored only as tag_b in a pair still lists its partner in co_occurs_with."""
    _seed(conn)
    http = next(r for r in list_tags(conn) if r["tag"] == "http")
    # (rust, http) is stored with tag_a='http'? No: rust<http is false (h<r), so tag_a='http'.
    # Either way http must see rust as a co-occurring partner.
    assert "rust" in http["co_occurs_with"]


def test_empty_db_returns_empty_list(conn):
    assert list_tags(conn) == []


def test_batched_cooccurrence_preserves_per_tag_ordering(conn):
    """The batched co-occurrence fetch must keep EACH tag's partners ordered exactly as the
    old per-tag query did (count desc, partner asc) across a whole page of tags."""
    _seed(conn)
    rows = {r["tag"]: r for r in list_tags(conn)}
    # rust: http(8) > async(6) > cli(4) > wasm(2), all under the 5-partner cap.
    assert rows["rust"]["co_occurs_with"] == ["http", "async", "cli", "wasm"]
    # Each partner sees rust back (symmetric across both stored directions).
    for partner in ("http", "async", "cli", "wasm"):
        assert rows[partner]["co_occurs_with"] == ["rust"]


def test_batched_cooccurrence_caps_and_breaks_ties_by_name(conn):
    """More than _COOCCUR_LIMIT partners: keep the top 5 by count, ties broken by name asc."""
    _seed_tag(conn, "hub", "hub tag", 100)
    # Seven partners; two share count 5 so the name tie-break decides which of them lands.
    partners = {
        "aa": 9, "bb": 8, "cc": 7, "dd": 6, "ee": 5, "ff": 5, "gg": 4,
    }
    for name, c in partners.items():
        _seed_tag(conn, name, name, c)
        _seed_cooc(conn, "hub", name, c)
    conn.commit()
    hub = next(r for r in list_tags(conn) if r["tag"] == "hub")
    # Top 5 by count desc; at the count-5 tie "ee" precedes "ff" (name asc), so "ee" is in.
    assert hub["co_occurs_with"] == ["aa", "bb", "cc", "dd", "ee"]


def test_batched_cooccurrence_matches_naive_per_tag_query(conn):
    """Regression: the batched result must equal a naive per-tag recomputation exactly."""
    _seed(conn)

    def naive(name):
        rows = conn.execute(
            """
            SELECT partner, count FROM (
                SELECT tag_b AS partner, count FROM tag_cooccurrence
                 WHERE tag_a = ? AND count > 0
                UNION ALL
                SELECT tag_a AS partner, count FROM tag_cooccurrence
                 WHERE tag_b = ? AND count > 0
            )
            ORDER BY count DESC, partner ASC
            LIMIT 5
            """,
            (name, name),
        ).fetchall()
        return [r["partner"] for r in rows]

    for row in list_tags(conn):
        assert row["co_occurs_with"] == naive(row["tag"])
