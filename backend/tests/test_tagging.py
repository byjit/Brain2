"""Auto-tagging orchestration (spec §7.1 steps 4-9, §7.2).

Offline with fakes. Covers the end-to-end tag pipeline against a live DB connection:
priors -> nearest tags -> ONE tagger call -> canonicalize -> persist edges/counts/
co-occurrence -> tags_text. Asserts exactly-one tagger call, snap-vs-create, counters,
co-occurrence pair canonical ordering, and the cap.
"""

import sqlite3

import pytest

from brain2.db.connection import open_user_db
from brain2.services.canonicalize import TagCandidate, canonicalize_candidates
from brain2.services.providers.embedder import EMBED_INPUT_MAX_CHARS, FakeEmbedder
from brain2.services.providers.summarizer import SUMMARY_INPUT_MAX_CHARS
from brain2.services.providers.tagger import FakeTagger, TagProposal
from brain2.services.structured_tags import FakeStructuredTagSource
from brain2.services.tags_vector import index_tag_vector
from brain2.services.tagging import apply_tags


class _RecordingEmbedder(FakeEmbedder):
    """FakeEmbedder that records the text it was asked to embed (input-bound assertions)."""

    def __init__(self) -> None:
        super().__init__()
        self.inputs: list[str] = []

    def embed(self, text: str) -> list[float]:
        self.inputs.append(text)
        return super().embed(text)


@pytest.fixture
def conn(tmp_path):
    with open_user_db("tagging-test", data_dir=tmp_path) as c:
        yield c


def _insert_entry(conn, entry_id, *, type="page", url=None, note="", content=None):
    conn.execute(
        """
        INSERT INTO entries (id, url, original_url, title, note, note_source, content,
                             type, source_url, saved_at, updated_at, status, attempts)
        VALUES (?, ?, ?, NULL, ?, 'body', ?, ?, NULL, '2026-01-01T00:00:00Z',
                '2026-01-01T00:00:00Z', 'processing', 1)
        """,
        (entry_id, url, url, note, content, type),
    )
    conn.commit()


def _seed_tag(conn, name, description, embedder, count=1):
    conn.execute(
        "INSERT INTO tags (name, description, count) VALUES (?, ?, ?)", (name, description, count)
    )
    index_tag_vector(conn, name, embedder.embed(description))
    conn.commit()


def test_exactly_one_tagger_call_per_entry(conn):
    _insert_entry(conn, "e1", note="Some content about python web")
    embedder = FakeEmbedder()
    tagger = FakeTagger(
        result=TagProposal(note="", tags=["python", "web"],
                            new_tag_descriptions={"python": "Python language", "web": "Web dev"})
    )
    source = FakeStructuredTagSource()

    apply_tags(
        conn, "e1", basis_text="Some content about python web", needs_summary=False,
        source=source, tagger=tagger, embedder=embedder,
        threshold=0.90, max_tags=5, nearest_limit=10,
    )

    assert len(tagger.calls) == 1  # spec: exactly one LLM call per entry


def test_oversized_basis_bounds_embedder_and_tagger_separately(conn):
    """A huge basis is prefix-bounded — tightly for the embedder, generously for the note.

    The embedder has a hard ~2k-token budget (EMBED_INPUT_MAX_CHARS) while the note-writer
    can read more (SUMMARY_INPUT_MAX_CHARS), so a long article still yields a meaningful
    routing-card note instead of being starved at 8k (spec §7.3).
    """
    _insert_entry(conn, "e1", note="")
    embedder = _RecordingEmbedder()
    tagger = FakeTagger()
    huge_basis = "word " * 20_000  # ~100k chars, well over both caps

    apply_tags(
        conn, "e1", basis_text=huge_basis, needs_summary=True,
        source=FakeStructuredTagSource(), tagger=tagger, embedder=embedder,
        threshold=0.90, max_tags=5, nearest_limit=10,
    )

    # The basis embedding (first embed call) is bounded to the embedder's hard limit.
    assert len(embedder.inputs[0]) == EMBED_INPUT_MAX_CHARS
    # The note-writer reads a larger prefix — strictly more than the embedder gets.
    assert len(tagger.calls[0].basis_text) == SUMMARY_INPUT_MAX_CHARS
    assert SUMMARY_INPUT_MAX_CHARS > EMBED_INPUT_MAX_CHARS


def test_persists_edges_counts_and_tags_text(conn):
    _insert_entry(conn, "e1", note="python web async")
    embedder = FakeEmbedder()
    tagger = FakeTagger(
        result=TagProposal(note="", tags=["python", "web", "async"],
                            new_tag_descriptions={
                                "python": "Python language scripting",
                                "web": "Web development http",
                                "async": "Asynchronous concurrency",
                            })
    )
    apply_tags(
        conn, "e1", basis_text="python web async", needs_summary=False,
        source=FakeStructuredTagSource(), tagger=tagger, embedder=embedder,
        threshold=0.90, max_tags=5, nearest_limit=10,
    )

    # entry_tags edges
    edges = {r[0] for r in conn.execute("SELECT tag FROM entry_tags WHERE entry_id='e1'")}
    assert edges == {"python", "web", "async"}
    # tags.count incremented for each
    for tag in ("python", "web", "async"):
        assert conn.execute("SELECT count FROM tags WHERE name=?", (tag,)).fetchone()[0] == 1
    # tags_text denormalized into FTS
    tags_text = conn.execute("SELECT tags_text FROM entries_fts WHERE id='e1'").fetchone()[0]
    assert set(tags_text.split()) == {"python", "web", "async"}


def test_cooccurrence_pairs_canonical_order(conn):
    _insert_entry(conn, "e1", note="a b c")
    embedder = FakeEmbedder()
    tagger = FakeTagger(
        result=TagProposal(note="", tags=["rust", "http", "cli"],
                            new_tag_descriptions={
                                "rust": "Rust lang", "http": "HTTP proto", "cli": "Command line"})
    )
    apply_tags(
        conn, "e1", basis_text="a b c", needs_summary=False,
        source=FakeStructuredTagSource(), tagger=tagger, embedder=embedder,
        threshold=0.90, max_tags=5, nearest_limit=10,
    )
    pairs = conn.execute("SELECT tag_a, tag_b, count FROM tag_cooccurrence ORDER BY tag_a, tag_b").fetchall()
    # 3 tags -> 3 unordered pairs, each stored with tag_a < tag_b, count 1.
    assert [(r[0], r[1], r[2]) for r in pairs] == [
        ("cli", "http", 1), ("cli", "rust", 1), ("http", "rust", 1)
    ]
    for r in pairs:
        assert r[0] < r[1]  # canonical ordering


def test_snap_does_not_create_duplicate(conn):
    _insert_entry(conn, "e1", note="python tutorial")
    embedder = FakeEmbedder()
    _seed_tag(conn, "python", "Python programming language scripting backend", embedder)
    # Candidate description identical to existing -> snaps.
    tagger = FakeTagger(
        result=TagProposal(note="", tags=["python3"],
                            new_tag_descriptions={"python3": "Python programming language scripting backend"})
    )
    apply_tags(
        conn, "e1", basis_text="python tutorial", needs_summary=False,
        source=FakeStructuredTagSource(), tagger=tagger, embedder=embedder,
        threshold=0.90, max_tags=5, nearest_limit=10,
    )
    assert conn.execute("SELECT count(*) FROM tags").fetchone()[0] == 1
    assert conn.execute("SELECT tag FROM entry_tags WHERE entry_id='e1'").fetchone()[0] == "python"
    # existing python count bumped to 2 (was 1 + this entry).
    assert conn.execute("SELECT count FROM tags WHERE name='python'").fetchone()[0] == 2


def test_reprocessing_same_entry_does_not_inflate_counts(conn):
    """Re-running apply_tags for the same entry+tags (spec §7.4 repair) must not double-bump.

    INSERT OR IGNORE dedupes the edges, so counters must stay equal to the live edge count
    (each edge = 1) and remain safe to decrement on delete (M6).
    """
    _insert_entry(conn, "e1", note="rust http")
    embedder = FakeEmbedder()
    proposal = TagProposal(
        note="", tags=["rust", "http"],
        new_tag_descriptions={"rust": "Rust lang", "http": "HTTP proto"},
    )
    kwargs = dict(
        basis_text="rust http", needs_summary=False,
        source=FakeStructuredTagSource(), tagger=FakeTagger(result=proposal), embedder=embedder,
        threshold=0.90, max_tags=5, nearest_limit=10,
    )
    apply_tags(conn, "e1", **kwargs)
    apply_tags(conn, "e1", **kwargs)

    assert conn.execute("SELECT count(*) FROM entry_tags WHERE entry_id='e1'").fetchone()[0] == 2
    for tag in ("rust", "http"):
        assert conn.execute("SELECT count FROM tags WHERE name=?", (tag,)).fetchone()[0] == 1
    assert conn.execute("SELECT count FROM tag_cooccurrence").fetchone()[0] == 1


def test_retag_partial_overlap_reconciles_counters(conn):
    """Spec §7.4/§9.2: re-tagging with a partially-overlapping set reconciles edges.

    Dropped tags decrement (count + co-occurrence); new tags increment; kept tags are
    untouched — so counters always equal the live edge set (the case M5 deferred).
    """
    _insert_entry(conn, "e1", note="x")
    embedder = FakeEmbedder()
    descs = {t: f"Concept {t}" for t in ("rust", "http", "cli", "wasm")}

    # First tag set: rust, http, cli.
    apply_tags(
        conn, "e1", basis_text="x", needs_summary=False, source=FakeStructuredTagSource(),
        tagger=FakeTagger(result=TagProposal(note="", tags=["rust", "http", "cli"],
                                             new_tag_descriptions=descs)),
        embedder=embedder, threshold=0.90, max_tags=5, nearest_limit=10,
    )
    # Re-tag set: rust, http, wasm (drops cli, keeps rust+http, adds wasm).
    apply_tags(
        conn, "e1", basis_text="x", needs_summary=False, source=FakeStructuredTagSource(),
        tagger=FakeTagger(result=TagProposal(note="", tags=["rust", "http", "wasm"],
                                             new_tag_descriptions=descs)),
        embedder=embedder, threshold=0.90, max_tags=5, nearest_limit=10,
    )

    edges = {r[0] for r in conn.execute("SELECT tag FROM entry_tags WHERE entry_id='e1'")}
    assert edges == {"rust", "http", "wasm"}
    # cli edge dropped -> count back to 0; the others stay at 1.
    assert conn.execute("SELECT count FROM tags WHERE name='cli'").fetchone()[0] == 0
    for tag in ("rust", "http", "wasm"):
        assert conn.execute("SELECT count FROM tags WHERE name=?", (tag,)).fetchone()[0] == 1
    # Co-occurrence equals the live pairs: (http,rust),(http,wasm),(rust,wasm) at 1; any
    # pair involving cli is decremented to 0.
    live = {(r[0], r[1]): r[2] for r in conn.execute(
        "SELECT tag_a, tag_b, count FROM tag_cooccurrence")}
    assert live.get(("http", "rust")) == 1
    assert live.get(("http", "wasm")) == 1
    assert live.get(("rust", "wasm")) == 1
    assert live.get(("cli", "http"), 0) == 0
    assert live.get(("cli", "rust"), 0) == 0


def test_summary_note_written_when_needed(conn):
    _insert_entry(conn, "e1", type="page", url="https://x.test", note="")
    embedder = FakeEmbedder()
    tagger = FakeTagger(
        result=TagProposal(note="A neutral summary of the page.", tags=["docs"],
                            new_tag_descriptions={"docs": "Documentation reference"})
    )
    note = apply_tags(
        conn, "e1", basis_text="long body text " * 50, needs_summary=True,
        source=FakeStructuredTagSource(), tagger=tagger, embedder=embedder,
        threshold=0.90, max_tags=5, nearest_limit=10,
    )
    assert note == "A neutral summary of the page."


def test_priors_seed_candidates_into_one_call(conn):
    _insert_entry(conn, "e1", type="page", url="https://github.com/encode/httpx", note="x")
    embedder = FakeEmbedder()
    source = FakeStructuredTagSource(
        repos={"encode/httpx": {"topics": ["http", "async"], "language": "Python"}}
    )
    tagger = FakeTagger()  # default echoes structured tags
    apply_tags(
        conn, "e1", basis_text="httpx client", needs_summary=False,
        source=source, tagger=tagger, embedder=embedder,
        threshold=0.90, max_tags=5, nearest_limit=10,
        url="https://github.com/encode/httpx",
    )
    # The single call received the github priors as structured_tags.
    assert set(tagger.calls[0].structured_tags) == {"http", "async", "python"}
    edges = {r[0] for r in conn.execute("SELECT tag FROM entry_tags WHERE entry_id='e1'")}
    assert edges == {"http", "async", "python"}
