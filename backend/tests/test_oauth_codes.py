"""OAuth authorization-code store + PKCE S256 tests (M7 deliverable 6, security-critical).

Codes are single-use, short-lived, and bound to the S256 code_challenge + redirect_uri.
Reuse, expiry, a wrong code_verifier, and the 'plain' method are all rejected.
"""

import base64
import hashlib
import time

import pytest

from brain2.auth import oauth_codes
from brain2.auth.store import open_auth_db


def _challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


@pytest.fixture
def conn(tmp_path):
    with open_auth_db(tmp_path / "auth.db") as c:
        c.execute(
            "INSERT INTO users (user_id, google_sub, email, created_at) VALUES (?,?,?,?)",
            ("u1", "sub1", "a@b.com", "2026-01-01T00:00:00Z"),
        )
        c.commit()
        yield c


def test_issue_then_consume_happy_path(conn):
    verifier = "a" * 64
    code = oauth_codes.issue_code(
        conn,
        user_id="u1",
        code_challenge=_challenge(verifier),
        redirect_uri="https://app/cb",
        ttl=60,
    )
    user_id = oauth_codes.consume_code(
        conn, code=code, code_verifier=verifier, redirect_uri="https://app/cb"
    )
    assert user_id == "u1"


def test_reused_code_rejected(conn):
    verifier = "a" * 64
    code = oauth_codes.issue_code(
        conn, user_id="u1", code_challenge=_challenge(verifier),
        redirect_uri="https://app/cb", ttl=60,
    )
    assert oauth_codes.consume_code(
        conn, code=code, code_verifier=verifier, redirect_uri="https://app/cb"
    ) == "u1"
    # Second use must fail (single-use).
    assert oauth_codes.consume_code(
        conn, code=code, code_verifier=verifier, redirect_uri="https://app/cb"
    ) is None


def test_wrong_verifier_rejected(conn):
    verifier = "a" * 64
    code = oauth_codes.issue_code(
        conn, user_id="u1", code_challenge=_challenge(verifier),
        redirect_uri="https://app/cb", ttl=60,
    )
    assert oauth_codes.consume_code(
        conn, code=code, code_verifier="b" * 64, redirect_uri="https://app/cb"
    ) is None


def test_expired_code_rejected(conn):
    verifier = "a" * 64
    code = oauth_codes.issue_code(
        conn, user_id="u1", code_challenge=_challenge(verifier),
        redirect_uri="https://app/cb", ttl=-1,
    )
    assert oauth_codes.consume_code(
        conn, code=code, code_verifier=verifier, redirect_uri="https://app/cb"
    ) is None


def test_redirect_uri_mismatch_rejected(conn):
    verifier = "a" * 64
    code = oauth_codes.issue_code(
        conn, user_id="u1", code_challenge=_challenge(verifier),
        redirect_uri="https://app/cb", ttl=60,
    )
    assert oauth_codes.consume_code(
        conn, code=code, code_verifier=verifier, redirect_uri="https://evil/cb"
    ) is None


def test_unknown_code_rejected(conn):
    assert oauth_codes.consume_code(
        conn, code="nope", code_verifier="x", redirect_uri="https://app/cb"
    ) is None


def test_verify_pkce_s256():
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    assert oauth_codes.verify_pkce_s256(verifier, _challenge(verifier)) is True
    assert oauth_codes.verify_pkce_s256("wrong", _challenge(verifier)) is False
