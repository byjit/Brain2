"""Tests for the startup queue drain across all user DBs (spec §6, §7.1 step 1).

``drain_all_users`` scans every {user_id}.db under DATA_DIR and processes its queue.
Offline via fakes.
"""

from brain2.db.connection import open_user_db
from brain2.services.providers.page_fetcher import FakePageFetcher
from brain2.services.providers.summarizer import FakeSummarizer
from brain2.services.worker import drain_all_users, reset_stale_processing


def _seed_note(data_dir, user_id, entry_id, text):
    with open_user_db(user_id, data_dir=data_dir) as conn:
        conn.execute(
            """
            INSERT INTO entries (id, url, original_url, title, note, note_source, content,
                                 type, source_url, saved_at, updated_at, status, attempts)
            VALUES (?, NULL, NULL, NULL, NULL, 'body', ?, 'note', NULL,
                    '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z', 'pending', 0)
            """,
            (entry_id, text),
        )
        conn.commit()


def test_drain_all_users_processes_every_db(tmp_path):
    _seed_note(tmp_path, "alice", "a1", "alice note")
    _seed_note(tmp_path, "bob", "b1", "bob note")

    total = drain_all_users(
        tmp_path, fetcher=FakePageFetcher(), summarizer=FakeSummarizer(), max_attempts=3
    )

    assert total == 2
    for user, eid in (("alice", "a1"), ("bob", "b1")):
        with open_user_db(user, data_dir=tmp_path) as conn:
            row = conn.execute("select status from entries where id = ?", (eid,)).fetchone()
            assert row["status"] == "active"


def test_drain_all_users_empty_dir_is_noop(tmp_path):
    assert drain_all_users(tmp_path, fetcher=FakePageFetcher(), summarizer=FakeSummarizer()) == 0


def test_drain_skips_bad_db_and_continues(tmp_path):
    # One unreadable/corrupt DB must not abort draining the rest (loop resilience).
    _seed_note(tmp_path, "good", "g1", "good note")
    (tmp_path / "corrupt.db").write_bytes(b"this is not a sqlite database at all")

    total = drain_all_users(
        tmp_path, fetcher=FakePageFetcher(), summarizer=FakeSummarizer(), max_attempts=3
    )

    assert total == 1  # the good user's entry was still drained
    with open_user_db("good", data_dir=tmp_path) as conn:
        assert conn.execute("select status from entries where id='g1'").fetchone()["status"] == "active"


def test_reset_stale_processing_requeues_old_rows(tmp_path):
    # A row stuck in 'processing' past the lease age (crash mid-pipeline) is requeued.
    with open_user_db("stuck", data_dir=tmp_path) as conn:
        conn.execute(
            """
            INSERT INTO entries (id, url, original_url, title, note, note_source, content,
                                 type, source_url, saved_at, updated_at, status, attempts)
            VALUES ('s1', NULL, NULL, NULL, NULL, 'body', 'stuck note', 'note', NULL,
                    '2026-01-01T00:00:00Z', '2000-01-01T00:00:00+00:00', 'processing', 1)
            """
        )
        # A freshly-claimed row (recent updated_at) must NOT be stolen.
        conn.execute(
            """
            INSERT INTO entries (id, url, original_url, title, note, note_source, content,
                                 type, source_url, saved_at, updated_at, status, attempts)
            VALUES ('s2', NULL, NULL, NULL, NULL, 'body', 'fresh note', 'note', NULL,
                    '2026-01-01T00:00:00Z', ?, 'processing', 1)
            """,
            ("2999-01-01T00:00:00+00:00",),
        )
        conn.commit()

        reset = reset_stale_processing(conn, lease_seconds=300)
        assert reset == 1
        assert conn.execute("select status from entries where id='s1'").fetchone()["status"] == "pending"
        assert conn.execute("select status from entries where id='s2'").fetchone()["status"] == "processing"
