"""Agent-supplied tags are canonicalized on write and merged additively (spec §10 save).

Offline. The MCP save tool accepts an optional ``tags`` list. Each is normalized +
canonicalized (reuse M5 canonicalize: embed description / snap to near-duplicate / create)
so agent tags cannot fragment the vocabulary, then merged ADDITIVELY into the entry's tags
with counters/co-occurrence/tags_text updated. Agent tags skip the LLM proposal step.
"""

import pytest

from brain2.db.connection import open_user_db
from brain2.services.providers.embedder import FakeEmbedder
from brain2.services.tagging import apply_agent_tags
from brain2.services.tags_vector import index_tag_vector


@pytest.fixture
def conn(tmp_path):
    with open_user_db("agent-tags-test", data_dir=tmp_path) as c:
        yield c


def _insert_entry(conn, entry_id):
    conn.execute(
        """
        INSERT INTO entries (id, url, original_url, title, note, note_source, content,
                             type, source_url, saved_at, updated_at, status, attempts)
        VALUES (?, NULL, NULL, NULL, '', 'body', NULL, 'note', NULL,
                '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z', 'active', 1)
        """,
        (entry_id,),
    )
    conn.commit()


def _seed_tag(conn, name, description, embedder, count=1):
    conn.execute(
        "INSERT INTO tags (name, description, count) VALUES (?, ?, ?)",
        (name, description, count),
    )
    index_tag_vector(conn, name, embedder.embed(description))
    conn.commit()


def test_agent_tags_created_and_counted(conn):
    _insert_entry(conn, "e1")
    embedder = FakeEmbedder()
    apply_agent_tags(conn, "e1", ["Rust", "HTTP"], embedder=embedder, threshold=0.90, max_tags=5)

    edges = {r[0] for r in conn.execute("SELECT tag FROM entry_tags WHERE entry_id='e1'")}
    assert edges == {"rust", "http"}  # normalized (lowercased)
    for tag in ("rust", "http"):
        assert conn.execute("SELECT count FROM tags WHERE name=?", (tag,)).fetchone()[0] == 1
    # co-occurrence recorded for the pair.
    assert conn.execute(
        "SELECT count FROM tag_cooccurrence WHERE tag_a='http' AND tag_b='rust'"
    ).fetchone()[0] == 1
    # denormalized into FTS.
    tags_text = conn.execute("SELECT tags_text FROM entries_fts WHERE id='e1'").fetchone()
    assert tags_text is not None and set(tags_text[0].split()) == {"rust", "http"}


def test_near_duplicate_snaps_not_fragments(conn):
    _insert_entry(conn, "e1")
    embedder = FakeEmbedder()
    # An existing tag whose description the agent's near-duplicate will snap to.
    _seed_tag(conn, "python", "Python programming language scripting backend", embedder)

    # Agent proposes "python3" — its name-derived embedding would NOT snap, but with a
    # matching description it must snap to the existing tag rather than fragment.
    apply_agent_tags(
        conn, "e1", ["python3"], embedder=embedder, threshold=0.90, max_tags=5,
        descriptions={"python3": "Python programming language scripting backend"},
    )
    # No new tag was created; the edge points at the canonical existing tag.
    assert conn.execute("SELECT count(*) FROM tags").fetchone()[0] == 1
    assert conn.execute("SELECT tag FROM entry_tags WHERE entry_id='e1'").fetchone()[0] == "python"


def test_merge_is_additive(conn):
    """Agent tags merge additively: existing edges are preserved, not replaced (spec §10)."""
    _insert_entry(conn, "e1")
    embedder = FakeEmbedder()
    apply_agent_tags(conn, "e1", ["rust"], embedder=embedder, threshold=0.90, max_tags=5)
    apply_agent_tags(conn, "e1", ["http"], embedder=embedder, threshold=0.90, max_tags=5)

    edges = {r[0] for r in conn.execute("SELECT tag FROM entry_tags WHERE entry_id='e1'")}
    assert edges == {"rust", "http"}  # the first tag survived the second merge
    # Re-adding an existing tag does not inflate its count.
    apply_agent_tags(conn, "e1", ["rust"], embedder=embedder, threshold=0.90, max_tags=5)
    assert conn.execute("SELECT count FROM tags WHERE name='rust'").fetchone()[0] == 1
