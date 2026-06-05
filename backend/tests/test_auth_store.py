"""Auth store (auth.db) tests: schema, WAL, idempotent open (M7 deliverable 1)."""

import brain2.auth.store as store
from brain2.auth.store import open_auth_db


def test_open_auth_db_creates_schema_and_wal(tmp_path):
    db_path = tmp_path / "auth.db"
    with open_auth_db(db_path) as conn:
        tables = {
            r["name"]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert {"users", "api_keys"} <= tables
        # WAL is enforced for concurrent reads during writes (spec §12).
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode.lower() == "wal"


def test_open_auth_db_is_idempotent(tmp_path):
    db_path = tmp_path / "auth.db"
    with open_auth_db(db_path) as conn:
        conn.execute(
            "INSERT INTO users (user_id, google_sub, email, created_at) VALUES (?,?,?,?)",
            ("u1", "sub1", "a@b.com", "2026-01-01T00:00:00Z"),
        )
        conn.commit()
    # Re-opening must not wipe data or fail re-applying the schema.
    with open_auth_db(db_path) as conn:
        row = conn.execute("SELECT email FROM users WHERE user_id='u1'").fetchone()
        assert row["email"] == "a@b.com"


def test_schema_script_runs_once_per_path(tmp_path, monkeypatch):
    """The full schema script must be applied only ONCE per auth.db path, not per request.

    Re-running executescript on every connection is self-inflicted load amplification. We
    spy on the schema read (the source of the script) and assert it happens at most once
    across several opens of the same path, while WAL stays enforced and auth still works.
    """
    db_path = tmp_path / "auth.db"
    store.reset_initialized_paths()

    calls = {"n": 0}
    real_read_text = type(store._SCHEMA_PATH).read_text

    def _counting_read_text(self, *args, **kwargs):
        calls["n"] += 1
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(type(store._SCHEMA_PATH), "read_text", _counting_read_text)

    for _ in range(3):
        with open_auth_db(db_path) as conn:
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            assert mode.lower() == "wal"
    # Schema source read at most once for this path despite 3 opens.
    assert calls["n"] <= 1

    # Auth still works: the schema was applied, so the tables exist and accept writes.
    with open_auth_db(db_path) as conn:
        conn.execute(
            "INSERT INTO users (user_id, google_sub, email, created_at) VALUES (?,?,?,?)",
            ("u2", "sub2", "c@d.com", "2026-01-01T00:00:00Z"),
        )
        conn.commit()
        assert conn.execute("SELECT email FROM users WHERE user_id='u2'").fetchone()[
            "email"
        ] == "c@d.com"


def test_users_table_has_expected_columns(tmp_path):
    with open_auth_db(tmp_path / "auth.db") as conn:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(users)")}
        assert {"user_id", "google_sub", "email", "created_at"} <= cols
        key_cols = {r["name"] for r in conn.execute("PRAGMA table_info(api_keys)")}
        assert {
            "id",
            "user_id",
            "token_hash",
            "prefix",
            "name",
            "created_at",
            "last_used_at",
            "revoked_at",
        } <= key_cols
