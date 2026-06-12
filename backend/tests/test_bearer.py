"""Bearer credential resolution tests (M7 deliverable 4, security-critical).

Routes an API key (br2_live_ prefix) to the api_keys table and a Brain2 JWT otherwise;
resolves both to the right user_id; rejects missing/garbage/expired/revoked. Two distinct
credentials map to two isolated user_ids.
"""

import time

import pytest

from brain2.auth import api_keys, bearer, jwt_service
from brain2.auth.store import open_auth_db

_SECRET = "test-secret"


@pytest.fixture
def conn(tmp_path):
    with open_auth_db(tmp_path / "auth.db") as c:
        for uid, sub in (("u1", "s1"), ("u2", "s2")):
            c.execute(
                "INSERT INTO users (user_id, google_sub, email, created_at) VALUES (?,?,?,?)",
                (uid, sub, f"{uid}@b.com", "2026-01-01T00:00:00Z"),
            )
        c.commit()
        yield c


def test_api_key_bearer_resolves_to_user(conn):
    created = api_keys.create_key(conn, user_id="u1", name="cli")
    assert bearer.resolve_bearer(
        f"Bearer {created.api_key}", conn=conn, secret=_SECRET
    ) == "u1"


def test_jwt_bearer_resolves_to_user(conn):
    token = jwt_service.issue_token("u2", secret=_SECRET, ttl=60)
    assert bearer.resolve_bearer(f"Bearer {token}", conn=conn, secret=_SECRET) == "u2"


def test_two_credentials_map_to_two_users(conn):
    key1 = api_keys.create_key(conn, user_id="u1", name="cli").api_key
    jwt2 = jwt_service.issue_token("u2", secret=_SECRET, ttl=60)
    assert bearer.resolve_bearer(f"Bearer {key1}", conn=conn, secret=_SECRET) == "u1"
    assert bearer.resolve_bearer(f"Bearer {jwt2}", conn=conn, secret=_SECRET) == "u2"


def test_missing_header_rejected(conn):
    assert bearer.resolve_bearer(None, conn=conn, secret=_SECRET) is None
    assert bearer.resolve_bearer("", conn=conn, secret=_SECRET) is None
    assert bearer.resolve_bearer("Token abc", conn=conn, secret=_SECRET) is None


def test_garbage_token_rejected(conn):
    assert bearer.resolve_bearer("Bearer garbage", conn=conn, secret=_SECRET) is None
    assert bearer.resolve_bearer(
        "Bearer br2_live_unknown", conn=conn, secret=_SECRET
    ) is None


def test_expired_jwt_rejected(conn):
    token = jwt_service.issue_token("u1", secret=_SECRET, ttl=1)
    time.sleep(1.2)
    assert bearer.resolve_bearer(f"Bearer {token}", conn=conn, secret=_SECRET) is None


def test_revoked_api_key_rejected(conn):
    created = api_keys.create_key(conn, user_id="u1", name="cli")
    api_keys.revoke_key(conn, "u1", created.id)
    assert bearer.resolve_bearer(
        f"Bearer {created.api_key}", conn=conn, secret=_SECRET
    ) is None


def test_jwt_bearer_rejected_if_user_not_in_db(conn):
    token = jwt_service.issue_token("u_nonexistent", secret=_SECRET, ttl=60)
    assert bearer.resolve_bearer(f"Bearer {token}", conn=conn, secret=_SECRET) is None

