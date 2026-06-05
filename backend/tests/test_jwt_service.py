"""Brain2 access-token (JWT) service tests (M7 deliverable 3b, security-critical).

Issue -> verify happy path; expired rejected; tampered rejected; the algorithm is
pinned (alg=none / wrong-secret rejected); the sub claim round-trips.
"""

import time

import jwt as pyjwt
import pytest

from brain2.auth import jwt_service

_SECRET = "test-secret"


def test_issue_then_verify_round_trips_sub():
    token = jwt_service.issue_token("user-123", secret=_SECRET, ttl=60)
    assert jwt_service.verify_token(token, secret=_SECRET) == "user-123"


def test_expired_token_rejected():
    token = jwt_service.issue_token("user-123", secret=_SECRET, ttl=1)
    time.sleep(1.2)
    assert jwt_service.verify_token(token, secret=_SECRET) is None


def test_tampered_token_rejected():
    token = jwt_service.issue_token("user-123", secret=_SECRET, ttl=60)
    # Flip a character in the signature segment.
    head, payload, sig = token.split(".")
    tampered = f"{head}.{payload}.{sig[:-2] + ('AA' if sig[-2:] != 'AA' else 'BB')}"
    assert jwt_service.verify_token(tampered, secret=_SECRET) is None


def test_wrong_secret_rejected():
    token = jwt_service.issue_token("user-123", secret=_SECRET, ttl=60)
    assert jwt_service.verify_token(token, secret="other-secret") is None


def test_alg_none_rejected():
    # An attacker-forged unsigned token must never validate (alg is pinned to HS256).
    forged = pyjwt.encode({"sub": "user-123", "exp": time.time() + 60}, key="", algorithm="none")
    assert jwt_service.verify_token(forged, secret=_SECRET) is None


def test_missing_exp_rejected():
    forged = pyjwt.encode({"sub": "user-123"}, _SECRET, algorithm="HS256")
    assert jwt_service.verify_token(forged, secret=_SECRET) is None


def test_garbage_rejected():
    assert jwt_service.verify_token("not.a.jwt", secret=_SECRET) is None
    assert jwt_service.verify_token("", secret=_SECRET) is None


def test_token_type_must_match():
    """A token of one type must not validate when another type is required."""
    session = jwt_service.issue_token("u", secret=_SECRET, ttl=60, typ="session")
    access = jwt_service.issue_token("u", secret=_SECRET, ttl=60, typ="access")
    # Each validates as its own type.
    assert jwt_service.verify_token(session, secret=_SECRET, expected_typ="session") == "u"
    assert jwt_service.verify_token(access, secret=_SECRET, expected_typ="access") == "u"
    # A session token is rejected where an access token is required, and vice versa.
    assert jwt_service.verify_token(session, secret=_SECRET, expected_typ="access") is None
    assert jwt_service.verify_token(access, secret=_SECRET, expected_typ="session") is None
