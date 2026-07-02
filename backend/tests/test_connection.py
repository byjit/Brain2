"""Tests for the per-user SQLite connection layer (spec §9.2, §12).

Verifies: WAL mode, sqlite-vec loads and vec0 tables exist, the full schema is
applied idempotently, and a tmp DATA_DIR is honored (never the real /data).
"""

import sqlite3

import pytest

from brain2.db.connection import open_user_db, user_db_path

EXPECTED_TABLES = {
    "entries",
    "entry_tags",
    "tags",
    "tag_cooccurrence",
    "tag_aliases",
    "entries_fts",
    "entries_vec",
    "tags_vec",
}


def test_db_path_is_inside_data_dir(tmp_path):
    path = user_db_path("alice", data_dir=tmp_path)
    assert path == tmp_path / "alice.db"


def test_open_creates_file_and_parent_dir(tmp_path):
    data_dir = tmp_path / "users"
    with open_user_db("bob", data_dir=data_dir) as conn:
        assert isinstance(conn, sqlite3.Connection)
    assert (data_dir / "bob.db").exists()


def test_wal_mode_enabled(tmp_path):
    with open_user_db("carol", data_dir=tmp_path) as conn:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal"


def test_busy_timeout_set(tmp_path):
    # Finding #4: busy_timeout must be set deterministically (not left to the driver default).
    with open_user_db("heidi", data_dir=tmp_path) as conn:
        timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]
    assert timeout == 5000


def test_url_has_unique_partial_index(tmp_path):
    # Finding #3: duplicate non-null URLs are rejected, but multiple NULL urls are allowed.
    with open_user_db("ivan", data_dir=tmp_path) as conn:
        conn.execute(
            "insert into entries (id, url, note_source, type, saved_at, updated_at, status, attempts)"
            " values ('a', 'https://example.com/x', 'body', 'page', 'now', 'now', 'pending', 0)"
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "insert into entries (id, url, note_source, type, saved_at, updated_at, status, attempts)"
                " values ('b', 'https://example.com/x', 'body', 'page', 'now', 'now', 'pending', 0)"
            )
        # Multiple NULL urls (notes) remain allowed.
        conn.execute(
            "insert into entries (id, url, note_source, type, saved_at, updated_at, status, attempts)"
            " values ('c', NULL, 'user', 'note', 'now', 'now', 'pending', 0)"
        )
        conn.execute(
            "insert into entries (id, url, note_source, type, saved_at, updated_at, status, attempts)"
            " values ('d', NULL, 'user', 'note', 'now', 'now', 'pending', 0)"
        )


def test_sqlite_vec_loaded(tmp_path):
    with open_user_db("dave", data_dir=tmp_path) as conn:
        version = conn.execute("select vec_version()").fetchone()[0]
    assert version


def test_full_schema_applied(tmp_path):
    with open_user_db("erin", data_dir=tmp_path) as conn:
        rows = conn.execute(
            "select name from sqlite_master where type in ('table','view')"
        ).fetchall()
    names = {r[0] for r in rows}
    assert EXPECTED_TABLES.issubset(names)


def test_vec0_tables_are_768_dim(tmp_path):
    # Inserting a 768-element vector must succeed; a wrong dimension must fail.
    vec768 = "[" + ",".join("0.1" for _ in range(768)) + "]"
    with open_user_db("frank", data_dir=tmp_path) as conn:
        conn.execute("insert into entries_vec(id, embedding) values (?, ?)", ("e1", vec768))
        with pytest.raises(sqlite3.Error):
            conn.execute("insert into entries_vec(id, embedding) values (?, ?)", ("e2", "[1.0,2.0]"))


def test_schema_application_is_idempotent(tmp_path):
    # Opening the same DB twice must not raise (CREATE ... IF NOT EXISTS).
    with open_user_db("grace", data_dir=tmp_path):
        pass
    with open_user_db("grace", data_dir=tmp_path) as conn:
        assert conn.execute("select count(*) from entries").fetchone()[0] == 0


# --- Task 1: the new supporting indexes exist -----------------------------------

def _index_names(conn):
    return {
        r[0]
        for r in conn.execute("select name from sqlite_master where type = 'index'")
    }


def test_new_indexes_exist(tmp_path):
    with open_user_db("idx-user", data_dir=tmp_path) as conn:
        names = _index_names(conn)
    for expected in (
        "idx_entry_tags_tag",
        "idx_entries_type",
        "idx_tag_cooccurrence_tag_b",
    ):
        assert expected in names, f"missing index {expected}"


def test_last_accessed_at_column_exists(tmp_path):
    with open_user_db("lac-user", data_dir=tmp_path) as conn:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(entries)")}
    assert "last_accessed_at" in cols


# --- Task 4b: user_version gating -----------------------------------------------

def test_user_version_stamped_on_open(tmp_path):
    from brain2.db.migrations import SCHEMA_VERSION

    with open_user_db("uv-user", data_dir=tmp_path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION


class _SchemaPathSpy:
    """Wraps the real schema Path and counts each read_text (== one DDL application)."""

    def __init__(self, real):
        self._real = real
        self.reads = 0

    def read_text(self, *a, **k):
        self.reads += 1
        return self._real.read_text(*a, **k)


def test_schema_apply_skipped_when_version_matches(tmp_path, monkeypatch):
    # First open applies + stamps the version. On reopen the version matches, so
    # apply_schema must NOT re-read/re-run the schema DDL (the per-request perf gate).
    import brain2.db.migrations as migrations

    with open_user_db("uv-skip", data_dir=tmp_path):
        pass

    spy = _SchemaPathSpy(migrations._SCHEMA_PATH)
    monkeypatch.setattr(migrations, "_SCHEMA_PATH", spy)
    with open_user_db("uv-skip", data_dir=tmp_path) as conn:
        conn.execute("select 1")
    assert spy.reads == 0, "schema must not be re-applied when user_version matches"


def test_schema_reapplied_on_version_bump(tmp_path, monkeypatch):
    # A DB at an older user_version must have the schema re-applied on next open.
    import brain2.db.migrations as migrations
    from brain2.db.migrations import SCHEMA_VERSION

    with open_user_db("uv-bump", data_dir=tmp_path) as conn:
        conn.execute("PRAGMA user_version = 0")
        conn.commit()

    spy = _SchemaPathSpy(migrations._SCHEMA_PATH)
    monkeypatch.setattr(migrations, "_SCHEMA_PATH", spy)
    with open_user_db("uv-bump", data_dir=tmp_path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    assert spy.reads == 1, "schema must be re-applied when user_version is stale"
