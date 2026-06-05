"""Worker auto-tagging integration (spec §7.1 steps 4-9, §7.2).

The worker, after resolving the basis, runs the single-call tagging pipeline and persists
tags + note. Offline with fakes. Asserts: exactly one tagger call (no separate summarizer
call on the summarize path), tags applied + tags_text searchable via BM25, and that the
verbatim short-circuits still set the note without a summarizer call.
"""

import sqlite3

import pytest

from brain2.db.connection import open_user_db
from brain2.services.providers.embedder import FakeEmbedder
from brain2.services.providers.page_fetcher import FakePageFetcher, PageContent
from brain2.services.providers.summarizer import FakeSummarizer
from brain2.services.providers.tagger import FakeTagger, TagProposal
from brain2.services.search import search_entries
from brain2.services.structured_tags import FakeStructuredTagSource
from brain2.services.worker import process_entry


@pytest.fixture
def conn(tmp_path):
    with open_user_db("worker-tag-test", data_dir=tmp_path) as c:
        yield c


def _insert(conn, *, id, type, url=None, title=None, content=None):
    conn.execute(
        """
        INSERT INTO entries (id, url, original_url, title, note, note_source, content,
                             type, source_url, saved_at, updated_at, status, attempts)
        VALUES (?, ?, ?, ?, NULL, 'body', ?, ?, NULL, '2026-01-01T00:00:00Z',
                '2026-01-01T00:00:00Z', 'pending', 0)
        """,
        (id, url, url, title, content, type),
    )
    conn.commit()


def test_page_summary_uses_one_tagger_call_not_summarizer(conn):
    _insert(conn, id="e1", type="page", url="https://x.test/a")
    fetcher = FakePageFetcher(default=PageContent(body_text="Body about python web " * 50))
    summarizer = FakeSummarizer()
    tagger = FakeTagger(
        result=TagProposal(note="A page about python web.", tags=["python", "web"],
                            new_tag_descriptions={"python": "Python lang", "web": "Web dev"})
    )
    process_entry(
        conn, "e1", fetcher=fetcher, summarizer=summarizer, embedder=FakeEmbedder(),
        tagger=tagger, structured_source=FakeStructuredTagSource(),
    )

    row = conn.execute("SELECT note, note_source, status FROM entries WHERE id='e1'").fetchone()
    assert row["status"] == "active"
    assert row["note"] == "A page about python web."
    assert row["note_source"] == "body"
    assert len(tagger.calls) == 1           # exactly one LLM call
    assert summarizer.calls == []           # the standalone summarizer was NOT used
    edges = {r[0] for r in conn.execute("SELECT tag FROM entry_tags WHERE entry_id='e1'")}
    assert edges == {"python", "web"}


def test_tag_keyword_returns_entry_via_bm25(conn):
    _insert(conn, id="e1", type="page", url="https://x.test/a", title="Some Title")
    fetcher = FakePageFetcher(default=PageContent(body_text="body " * 50))
    tagger = FakeTagger(
        result=TagProposal(note="note", tags=["kubernetes"],
                            new_tag_descriptions={"kubernetes": "Container orchestration platform"})
    )
    process_entry(
        conn, "e1", fetcher=fetcher, summarizer=FakeSummarizer(), embedder=FakeEmbedder(),
        tagger=tagger, structured_source=FakeStructuredTagSource(),
    )
    # BM25 over tags_text now matches the tag keyword.
    results = search_entries(conn, "kubernetes")
    assert any(r["id"] == "e1" for r in results)


def test_page_meta_keywords_seed_priors_end_to_end(conn):
    """Spec §7.2 mechanism 1: OG/meta keywords from the fetched page seed candidate tags.

    The fetched page surfaces meta keywords, which must reach the single tagger call as
    structured priors through the real worker path (not just unit tests passing them in).
    """
    _insert(conn, id="e1", type="page", url="https://x.test/a")
    fetcher = FakePageFetcher(
        default=PageContent(body_text="body " * 50, keywords=["python", "fastapi"])
    )
    tagger = FakeTagger()  # default echoes structured priors as candidates
    process_entry(
        conn, "e1", fetcher=fetcher, summarizer=FakeSummarizer(), embedder=FakeEmbedder(),
        tagger=tagger, structured_source=FakeStructuredTagSource(),
    )
    assert set(tagger.calls[0].structured_tags) == {"python", "fastapi"}
    edges = {r[0] for r in conn.execute("SELECT tag FROM entry_tags WHERE entry_id='e1'")}
    assert edges == {"python", "fastapi"}


def test_worker_autotag_preserves_preexisting_agent_tags(conn):
    """Spec §10: agent-supplied tags merge additively and must survive auto-tagging.

    A `save` with explicit tags applies them synchronously to the still-`pending` entry;
    when the background worker later runs auto-tagging it must UNION its proposed tags with
    the entry's current edges, not reconcile to only the LLM set (which would silently wipe
    the agent tag).
    """
    _insert(conn, id="e1", type="page", url="https://x.test/a")
    # Simulate the synchronous agent-tag write that save_tool performs before the worker runs.
    conn.execute(
        "INSERT INTO tags (name, description, count) VALUES ('myspecialtag', 'agent tag', 1)"
    )
    conn.execute("INSERT INTO entry_tags (entry_id, tag) VALUES ('e1', 'myspecialtag')")
    conn.commit()

    fetcher = FakePageFetcher(default=PageContent(body_text="Body about python web " * 50))
    tagger = FakeTagger(
        result=TagProposal(note="A page.", tags=["autotag"],
                            new_tag_descriptions={"autotag": "An automatic tag"})
    )
    process_entry(
        conn, "e1", fetcher=fetcher, summarizer=FakeSummarizer(), embedder=FakeEmbedder(),
        tagger=tagger, structured_source=FakeStructuredTagSource(),
    )

    edges = {r[0] for r in conn.execute("SELECT tag FROM entry_tags WHERE entry_id='e1'")}
    assert edges == {"myspecialtag", "autotag"}  # agent tag preserved alongside the auto-tag


def test_short_clip_verbatim_note_still_tags_with_one_call(conn):
    _insert(conn, id="c1", type="clip", content="useEffect hook cleanup")
    tagger = FakeTagger(
        result=TagProposal(note="", tags=["react"],
                            new_tag_descriptions={"react": "React UI library hooks"})
    )
    summarizer = FakeSummarizer()
    process_entry(
        conn, "c1", fetcher=FakePageFetcher(), summarizer=summarizer, embedder=FakeEmbedder(),
        tagger=tagger, structured_source=FakeStructuredTagSource(),
    )
    row = conn.execute("SELECT note, note_source FROM entries WHERE id='c1'").fetchone()
    assert row["note"] == "useEffect hook cleanup"  # verbatim, not summarized
    assert row["note_source"] == "body"
    assert summarizer.calls == []
    assert len(tagger.calls) == 1
    edges = {r[0] for r in conn.execute("SELECT tag FROM entry_tags WHERE entry_id='c1'")}
    assert edges == {"react"}
