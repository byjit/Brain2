"""Personal Access Token service tests (M7 deliverable 3a, security-critical).

Only the SHA-256 hash is stored (never the raw key); verification is a constant-time
hash compare; revoked keys are rejected; last_used is bumped on a successful verify.
"""

import pytest

from brain2.auth import api_keys
from brain2.auth.store import open_auth_db


@pytest.fixture
def conn(tmp_path):
    with open_auth_db(tmp_path / "auth.db") as c:
        c.execute(
            "INSERT INTO users (user_id, google_sub, email, created_at) VALUES (?,?,?,?)",
            ("u1", "sub1", "a@b.com", "2026-01-01T00:00:00Z"),
        )
        c.commit()
        yield c


def test_generate_returns_raw_key_once_and_stores_only_hash(conn):
    created = api_keys.create_key(conn, user_id="u1", name="laptop")
    raw = created.api_key
    assert raw.startswith("br2_live_")
    # The stored row must NOT contain the raw key anywhere.
    row = conn.execute("SELECT * FROM api_keys WHERE id=?", (created.id,)).fetchone()
    assert raw not in dict(row).values()
    assert row["token_hash"] != raw
    # The display prefix is a short non-secret fragment of the key.
    assert raw.startswith(created.prefix)
    assert len(created.prefix) < len(raw)


def test_verify_resolves_to_user_and_bumps_last_used(conn):
    created = api_keys.create_key(conn, user_id="u1", name="laptop")
    assert conn.execute(
        "SELECT last_used_at FROM api_keys WHERE id=?", (created.id,)
    ).fetchone()["last_used_at"] is None

    user_id = api_keys.verify_key(conn, created.api_key)
    assert user_id == "u1"

    last_used = conn.execute(
        "SELECT last_used_at FROM api_keys WHERE id=?", (created.id,)
    ).fetchone()["last_used_at"]
    assert last_used is not None


def test_verify_rejects_unknown_and_garbage_keys(conn):
    assert api_keys.verify_key(conn, "br2_live_does_not_exist") is None
    assert api_keys.verify_key(conn, "not-even-a-key") is None
    assert api_keys.verify_key(conn, "") is None


def test_revoked_key_is_rejected(conn):
    created = api_keys.create_key(conn, user_id="u1", name="laptop")
    assert api_keys.verify_key(conn, created.api_key) == "u1"
    assert api_keys.revoke_key(conn, "u1", created.id) is True
    assert api_keys.verify_key(conn, created.api_key) is None


def test_revoke_only_affects_owner(conn):
    conn.execute(
        "INSERT INTO users (user_id, google_sub, email, created_at) VALUES (?,?,?,?)",
        ("u2", "sub2", "c@d.com", "2026-01-01T00:00:00Z"),
    )
    created = api_keys.create_key(conn, user_id="u1", name="laptop")
    # A different user cannot revoke u1's key.
    assert api_keys.revoke_key(conn, "u2", created.id) is False
    assert api_keys.verify_key(conn, created.api_key) == "u1"


def test_list_keys_never_leaks_secret(conn):
    created = api_keys.create_key(conn, user_id="u1", name="laptop")
    api_keys.create_key(conn, user_id="u1", name="ci")
    listed = api_keys.list_keys(conn, "u1")
    assert len(listed) == 2
    for item in listed:
        assert "token_hash" not in item
        assert "api_key" not in item
        assert created.api_key not in item.values()
        assert {"id", "prefix", "name", "created_at", "last_used_at", "revoked"} <= set(item)


def test_has_api_key_prefix():
    assert api_keys.has_api_key_prefix("br2_live_abc") is True
    assert api_keys.has_api_key_prefix("eyJhbGciOi.jwt.token") is False
