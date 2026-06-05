"""The entries_fts index must stay in lockstep with the entries table (spec §9.2).

These tests drive the save service through a real per-user DB (via open_user_db) and
assert the FTS row is created/updated/removed alongside the relational row.
"""

import pytest

from brain2.db.connection import open_user_db
from brain2.models.entries import CreateEntryRequest
from brain2.services.entries import delete_entry, save_entry


@pytest.fixture
def conn(tmp_path):
    with open_user_db("fts-user", data_dir=tmp_path) as c:
        yield c


def _fts_row(conn, entry_id):
    """Return the entries_fts row for an entry as a dict, or None."""
    row = conn.execute(
        "select id, title, tags_text, content from entries_fts where id = ?",
        (entry_id,),
    ).fetchone()
    return dict(row) if row else None


def test_insert_writes_fts_row(conn):
    res = save_entry(conn, CreateEntryRequest(type="page", url="https://ex.com/a", title="Hello World"))
    fts = _fts_row(conn, res.id)
    assert fts is not None
    assert fts["title"] == "Hello World"
    # Tags are empty until auto-tagging lands (M5).
    assert fts["tags_text"] == ""


def test_note_content_is_indexed(conn):
    res = save_entry(conn, CreateEntryRequest(type="note", captured_text="my searchable note body"))
    fts = _fts_row(conn, res.id)
    assert fts["content"] == "my searchable note body"


def test_page_content_not_indexed(conn):
    # page content is not persisted, so the FTS content column must be empty/None.
    res = save_entry(conn, CreateEntryRequest(type="page", url="https://ex.com/p", captured_text="body"))
    fts = _fts_row(conn, res.id)
    assert not fts["content"]


def test_update_rewrites_fts_row_in_lockstep(conn):
    first = save_entry(conn, CreateEntryRequest(type="page", url="https://ex.com/u", title="Original Title"))
    save_entry(conn, CreateEntryRequest(type="page", url="https://ex.com/u", title="Updated Title"))
    fts = _fts_row(conn, first.id)
    assert fts["title"] == "Updated Title"
    # Still exactly one FTS row for the entry (update, not duplicate insert).
    count = conn.execute("select count(*) from entries_fts where id = ?", (first.id,)).fetchone()[0]
    assert count == 1


def test_delete_removes_fts_row(conn):
    res = save_entry(conn, CreateEntryRequest(type="note", captured_text="to be deleted"))
    assert _fts_row(conn, res.id) is not None
    deleted = delete_entry(conn, res.id)
    assert deleted is True
    assert _fts_row(conn, res.id) is None
    # The relational row is gone too.
    assert conn.execute("select count(*) from entries where id = ?", (res.id,)).fetchone()[0] == 0


def test_delete_missing_entry_returns_false(conn):
    assert delete_entry(conn, "does-not-exist") is False


def test_concurrent_first_save_of_same_url_converges_to_update(conn, monkeypatch):
    """TOCTOU race: two callers both read None, then both INSERT the same URL.

    The losing INSERT hits the partial unique index. We simulate the stale read by
    forcing the existing-id lookup to return None even though a row already exists,
    so save_entry takes the INSERT path against a duplicate URL. It must catch the
    IntegrityError and converge on the existing row, returning UPDATED (spec §10
    idempotent re-save), not raise an unhandled sqlite3.IntegrityError.
    """
    from brain2.services import entries as entries_mod

    url = "https://ex.com/race"
    first = save_entry(conn, CreateEntryRequest(type="page", url=url, title="First"))
    assert first.status.value == "saved"

    # Simulate the stale-read window: the PRE-insert lookup misses the existing row
    # (returns None), but the post-conflict recovery lookup runs for real and finds it.
    real_lookup = entries_mod._find_by_normalized_url
    calls = {"n": 0}

    def flaky_lookup(c, u):
        calls["n"] += 1
        if calls["n"] == 1:
            return None  # stale read: row not yet visible
        return real_lookup(c, u)  # recovery: row is now committed

    monkeypatch.setattr(entries_mod, "_find_by_normalized_url", flaky_lookup)
    second = save_entry(conn, CreateEntryRequest(type="page", url=url, title="Second"))

    assert second.status.value == "updated"
    assert second.id == first.id
