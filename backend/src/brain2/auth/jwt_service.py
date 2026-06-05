"""Brain2 access tokens — short-lived signed JWTs (spec §12).

HS256 with a config secret, carrying ``sub`` = user_id and ``exp``. Verification PINS the
algorithm (rejecting ``alg: none`` and confusion attacks) and REQUIRES ``exp`` so an
unexpiring token can never validate. Built on ``pyjwt`` — no hand-rolled crypto.
"""

import time

import jwt as pyjwt

_ALGORITHM = "HS256"


def issue_token(user_id: str, *, secret: str, ttl: int, typ: str = "access") -> str:
    """Issue a signed token for ``user_id`` valid for ``ttl`` seconds.

    ``typ`` distinguishes a short-lived OAuth ``access`` token from the long-lived
    ``session`` cookie so the two are not interchangeable (a leaked session cookie must not
    work as a Bearer access token for the full session TTL).
    """
    now = int(time.time())
    payload = {"sub": user_id, "iat": now, "exp": now + ttl, "typ": typ}
    return pyjwt.encode(payload, secret, algorithm=_ALGORITHM)


def verify_token(token: str, *, secret: str, expected_typ: str = "access") -> str | None:
    """Verify a token's signature, expiry, and type; return its ``sub`` or None if invalid.

    Pins the algorithm to HS256 (rejecting ``alg: none`` and RS/HS confusion) and requires
    the ``exp`` claim so a token without an expiry is rejected. ``expected_typ`` must match
    the token's ``typ`` claim, so session and access tokens cannot be used interchangeably.
    """
    if not token:
        return None
    try:
        payload = pyjwt.decode(
            token,
            secret,
            algorithms=[_ALGORITHM],
            options={"require": ["exp", "sub"]},
        )
    except pyjwt.InvalidTokenError:
        return None
    if payload.get("typ") != expected_typ:
        return None
    sub = payload.get("sub")
    return sub if isinstance(sub, str) and sub else None
