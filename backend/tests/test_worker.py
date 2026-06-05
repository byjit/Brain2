"""Tests for the resilient async worker (spec §7.1, §7.4).

All offline: the worker takes injected fake providers, so no GEMINI_API_KEY or network.
Covers note resolution + provenance, status transitions, FTS re-indexing, retry/backoff
on failure, the failed-after-ceiling path, and processing-status double-pickup guard.
"""

import sqlite3

import pytest

from brain2.db.connection import open_user_db
from brain2.services.providers.page_fetcher import FakePageFetcher, PageContent
from brain2.services.providers.summarizer import FakeSummarizer
from brain2.services.worker import process_entry, process_pending


@pytest.fixture
def conn(tmp_path):
    with open_user_db("worker-test", data_dir=tmp_path) as c:
        yield c


def _insert(conn: sqlite3.Connection, *, id, type, url=None, title=None, content=None, status="pending", attempts=0):
    conn.execute(
        """
        INSERT INTO entries (id, url, original_url, title, note, note_source, content,
                             type, source_url, saved_at, updated_at, status, attempts)
        VALUES (?, ?, ?, ?, NULL, 'body', ?, ?, NULL, '2026-01-01T00:00:00Z',
                '2026-01-01T00:00:00Z', ?, ?)
        """,
        (id, url, url, title, content, type, status, attempts),
    )
    conn.commit()


def _row(conn, id):
    return conn.execute("select * from entries where id = ?", (id,)).fetchone()


# --- note resolution + provenance through the worker ------------------------


def test_worker_sets_active_and_writes_note_source_body(conn):
    _insert(conn, id="e1", type="page", url="https://x.test/a")
    fetcher = FakePageFetcher(default=PageContent(body_text="Body content " * 50))
    summarizer = FakeSummarizer()

    process_entry(conn, "e1", fetcher=fetcher, summarizer=summarizer)

    row = _row(conn, "e1")
    assert row["status"] == "active"
    assert row["note_source"] == "body"
    assert row["note"].startswith("Summary:")
    assert row["attempts"] == 1
    assert row["error_message"] is None
    assert fetcher.calls == ["https://x.test/a"]  # page body re-fetched, not stored


def test_worker_og_fallback(conn):
    _insert(conn, id="e2", type="page", url="https://x.test/b")
    fetcher = FakePageFetcher(default=PageContent(body_text=None, og_description="teaser copy"))
    process_entry(conn, "e2", fetcher=fetcher, summarizer=FakeSummarizer())
    row = _row(conn, "e2")
    assert row["status"] == "active"
    assert row["note_source"] == "og"
    assert row["note"] == "teaser copy"


def test_worker_title_fallback(conn):
    _insert(conn, id="e3", type="page", url="https://x.test/c", title="Stored Title")
    fetcher = FakePageFetcher(default=PageContent())
    process_entry(conn, "e3", fetcher=fetcher, summarizer=FakeSummarizer())
    row = _row(conn, "e3")
    assert row["status"] == "active"
    assert row["note_source"] == "title"
    assert row["note"] == "Stored Title"


def test_note_type_keeps_user_text_no_summarizer(conn):
    _insert(conn, id="e4", type="note", content="my own thoughts")
    summarizer = FakeSummarizer()
    process_entry(conn, "e4", fetcher=FakePageFetcher(), summarizer=summarizer)
    row = _row(conn, "e4")
    assert row["status"] == "active"
    assert row["note"] == "my own thoughts"
    assert row["note_source"] == "user"
    assert summarizer.calls == []


def test_short_clip_verbatim_no_summarizer(conn):
    _insert(conn, id="e5", type="clip", url="https://x.test/d", content="short highlight")
    summarizer = FakeSummarizer()
    process_entry(conn, "e5", fetcher=FakePageFetcher(), summarizer=summarizer)
    row = _row(conn, "e5")
    assert row["status"] == "active"
    assert row["note"] == "short highlight"
    assert summarizer.calls == []


def test_long_clip_summarized(conn):
    _insert(conn, id="e6", type="clip", url="https://x.test/e", content="word " * 200)
    summarizer = FakeSummarizer()
    process_entry(conn, "e6", fetcher=FakePageFetcher(), summarizer=summarizer)
    row = _row(conn, "e6")
    assert row["status"] == "active"
    assert row["note"].startswith("Summary:")
    assert len(summarizer.calls) == 1


# --- FTS re-indexing --------------------------------------------------------


def test_worker_indexes_note_for_search(conn):
    _insert(conn, id="e7", type="note", content="kubernetes networking notes here")
    process_entry(conn, "e7", fetcher=FakePageFetcher(), summarizer=FakeSummarizer())
    hit = conn.execute(
        "select id from entries_fts where entries_fts match ?", ('"kubernetes"',)
    ).fetchone()
    assert hit is not None and hit[0] == "e7"


# --- retry / failure mechanics (spec §7.4) ----------------------------------


def test_failure_below_ceiling_returns_to_pending(conn):
    _insert(conn, id="e8", type="page", url="https://x.test/f")
    fetcher = FakePageFetcher(raises=RuntimeError("boom"))
    process_entry(conn, "e8", fetcher=fetcher, summarizer=FakeSummarizer(), max_attempts=3)
    row = _row(conn, "e8")
    assert row["status"] == "pending"  # below ceiling -> retryable
    assert row["attempts"] == 1
    assert row["error_message"] is not None


def test_failed_after_ceiling_sets_error_message(conn):
    _insert(conn, id="e9", type="page", url="https://x.test/g", attempts=2)
    fetcher = FakePageFetcher(raises=RuntimeError("still broken"))
    # attempts already 2; this attempt (3rd) reaches the ceiling of 3.
    process_entry(conn, "e9", fetcher=fetcher, summarizer=FakeSummarizer(), max_attempts=3)
    row = _row(conn, "e9")
    assert row["status"] == "failed"
    assert row["attempts"] == 3
    assert "still broken" in row["error_message"]


def test_repeated_summarizer_failure_eventually_fails(conn):
    _insert(conn, id="e10", type="clip", url="https://x.test/h", content="word " * 200)
    summarizer = FakeSummarizer(raises=RuntimeError("gemini down"))
    fetcher = FakePageFetcher()
    for _ in range(3):
        process_entry(conn, "e10", fetcher=fetcher, summarizer=summarizer, max_attempts=3)
        # Backoff is now enforced via next_retry_at; clear the gate so the next attempt
        # (which would happen after the backoff elapsed) can re-claim the row.
        conn.execute("UPDATE entries SET next_retry_at = NULL WHERE id = 'e10'")
        conn.commit()
    row = _row(conn, "e10")
    assert row["status"] == "failed"
    assert row["attempts"] == 3
    assert "gemini down" in row["error_message"]


# --- idempotency / double-pickup guard --------------------------------------


def test_already_active_entry_not_reprocessed(conn):
    _insert(conn, id="e11", type="clip", url="https://x.test/i", content="word " * 200, status="active")
    summarizer = FakeSummarizer()
    process_entry(conn, "e11", fetcher=FakePageFetcher(), summarizer=summarizer)
    # Re-saving does not re-summarize an already-active entry (spec §10).
    assert summarizer.calls == []


def test_processing_status_prevents_double_pickup(conn):
    # An entry already claimed (status=processing) must not be picked again.
    _insert(conn, id="e12", type="clip", url="https://x.test/j", content="word " * 200, status="processing")
    summarizer = FakeSummarizer()
    process_entry(conn, "e12", fetcher=FakePageFetcher(), summarizer=summarizer)
    assert summarizer.calls == []


# --- queue drain ------------------------------------------------------------


def test_process_pending_drains_pending_and_failed(conn):
    _insert(conn, id="p1", type="note", content="alpha")
    _insert(conn, id="p2", type="note", content="beta", status="failed", attempts=1)
    _insert(conn, id="p3", type="note", content="gamma", status="active")  # skipped

    count = process_pending(conn, fetcher=FakePageFetcher(), summarizer=FakeSummarizer(), max_attempts=3)

    assert count == 2
    assert _row(conn, "p1")["status"] == "active"
    assert _row(conn, "p2")["status"] == "active"


def test_process_pending_skips_failed_at_ceiling(conn):
    # A failed entry already at the attempt ceiling is not retried.
    _insert(conn, id="p4", type="note", content="delta", status="failed", attempts=3)
    count = process_pending(conn, fetcher=FakePageFetcher(), summarizer=FakeSummarizer(), max_attempts=3)
    assert count == 0
    assert _row(conn, "p4")["status"] == "failed"


# --- exponential backoff enforcement (spec §7.4) ----------------------------


def test_backoff_defers_reclaim_until_next_retry_at(conn):
    # A transient failure returns the row to 'pending' but stamps next_retry_at in the
    # future, so the immediately-following drain must NOT re-claim it (backoff enforced).
    _insert(conn, id="b1", type="page", url="https://x.test/backoff")
    fetcher = FakePageFetcher(raises=RuntimeError("boom"))
    summarizer = FakeSummarizer()

    process_entry(conn, "b1", fetcher=fetcher, summarizer=summarizer, max_attempts=5)
    row = _row(conn, "b1")
    assert row["status"] == "pending"
    assert row["attempts"] == 1
    assert row["next_retry_at"] is not None  # backoff stamp recorded

    # A second pass within the backoff window must not re-claim/re-increment.
    process_entry(conn, "b1", fetcher=fetcher, summarizer=summarizer, max_attempts=5)
    assert _row(conn, "b1")["attempts"] == 1  # still gated by next_retry_at

    # process_pending must also honor the gate (no activation, no re-claim).
    activated = process_pending(conn, fetcher=fetcher, summarizer=summarizer, max_attempts=5)
    assert activated == 0
    assert _row(conn, "b1")["attempts"] == 1


def test_backoff_elapsed_allows_reclaim(conn):
    # Once next_retry_at is in the past, the row is claimable again.
    _insert(conn, id="b2", type="page", url="https://x.test/backoff2")
    fetcher = FakePageFetcher(raises=RuntimeError("boom"))
    process_entry(conn, "b2", fetcher=fetcher, summarizer=FakeSummarizer(), max_attempts=5)
    # Backdate the retry gate into the past.
    conn.execute(
        "UPDATE entries SET next_retry_at = '2000-01-01T00:00:00+00:00' WHERE id = 'b2'"
    )
    conn.commit()
    process_entry(conn, "b2", fetcher=fetcher, summarizer=FakeSummarizer(), max_attempts=5)
    assert _row(conn, "b2")["attempts"] == 2  # re-claimed after backoff elapsed


def test_successful_processing_clears_next_retry_at(conn):
    _insert(conn, id="b3", type="note", content="hello world")
    process_entry(conn, "b3", fetcher=FakePageFetcher(), summarizer=FakeSummarizer())
    assert _row(conn, "b3")["next_retry_at"] is None


# --- empty-note guard (spec §7.4 no silent black hole) ----------------------


def test_empty_resolved_note_is_failed_not_silently_active(conn):
    # A page with no body, no og/meta, and no title resolves to an empty note. The
    # worker must NOT mark it active+clean; it must surface as a failure to repair.
    _insert(conn, id="n1", type="page", url="https://x.test/empty")
    fetcher = FakePageFetcher(default=PageContent())  # all fields empty
    process_entry(conn, "n1", fetcher=fetcher, summarizer=FakeSummarizer(), max_attempts=1)
    row = _row(conn, "n1")
    assert row["status"] != "active"
    assert row["error_message"] is not None
    assert "https://x.test/empty" in row["error_message"]


def test_empty_clip_content_does_not_activate_blank(conn):
    _insert(conn, id="n2", type="clip", url="https://x.test/blankclip", content="")
    process_entry(conn, "n2", fetcher=FakePageFetcher(), summarizer=FakeSummarizer(), max_attempts=1)
    row = _row(conn, "n2")
    assert row["status"] != "active"
    assert row["error_message"] is not None


# --- claim writes updated_at so staleness is measurable ---------------------


def test_claim_updates_updated_at(conn):
    _insert(conn, id="u1", type="note", content="track me")
    before = _row(conn, "u1")["updated_at"]
    process_entry(conn, "u1", fetcher=FakePageFetcher(), summarizer=FakeSummarizer())
    assert _row(conn, "u1")["updated_at"] != before
