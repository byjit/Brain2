"""Identity provider tests (M7 deliverable 2): fake + factory selection.

The real GoogleIdentityProvider calls Google (not exercised offline). FakeIdentityProvider
returns canned identities so the whole auth suite runs without contacting Google. The
factory selects real-vs-fake by config, mirroring the M3/M4/M5 provider pattern.
"""

import httpx
import pytest

from brain2.auth.providers.identity import (
    FakeIdentityProvider,
    GoogleIdentityProvider,
    GoogleIdentity,
    build_identity_provider,
)
from brain2.config import Settings


def test_fake_provider_returns_canned_identity():
    provider = FakeIdentityProvider(
        {"code-1": GoogleIdentity(google_sub="sub-1", email="a@b.com")}
    )
    identity = provider.exchange_code(code="code-1", redirect_uri="https://app/cb")
    assert identity.google_sub == "sub-1"
    assert identity.email == "a@b.com"


def test_fake_provider_default_identity_for_unknown_code():
    provider = FakeIdentityProvider()
    identity = provider.exchange_code(code="anything", redirect_uri="https://app/cb")
    assert identity.google_sub  # a deterministic canned identity is returned
    assert identity.email


def test_factory_returns_fake_without_google_config():
    settings = Settings(google_client_id=None, google_client_secret=None)
    provider = build_identity_provider(settings)
    assert isinstance(provider, FakeIdentityProvider)


def test_factory_returns_google_when_configured():
    settings = Settings(google_client_id="cid", google_client_secret="csecret")
    provider = build_identity_provider(settings)
    assert isinstance(provider, GoogleIdentityProvider)


# --- Real provider audience binding (confused-deputy defense) --------------------------


def _mock_transport(*, token_response: dict, tokeninfo_claims: dict) -> httpx.MockTransport:
    """A transport that fakes Google's /token and /tokeninfo responses."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token") and request.method == "POST":
            return httpx.Response(200, json=token_response)
        return httpx.Response(200, json=tokeninfo_claims)

    return httpx.MockTransport(handler)


def test_google_provider_accepts_matching_audience():
    provider = GoogleIdentityProvider(
        client_id="cid",
        client_secret="csecret",
        transport=_mock_transport(
            token_response={"id_token": "tok"},
            tokeninfo_claims={
                "sub": "sub-1",
                "email": "a@b.com",
                "email_verified": "true",
                "aud": "cid",
                "iss": "https://accounts.google.com",
            },
        ),
    )
    identity = provider.exchange_code(code="c", redirect_uri="https://app/cb")
    assert identity.google_sub == "sub-1"
    assert identity.email == "a@b.com"


def test_google_provider_rejects_foreign_audience():
    """An id_token minted for a DIFFERENT OAuth client must be rejected (confused-deputy)."""
    provider = GoogleIdentityProvider(
        client_id="cid",
        client_secret="csecret",
        transport=_mock_transport(
            token_response={"id_token": "tok"},
            tokeninfo_claims={
                "sub": "attacker-sub",
                "email": "evil@b.com",
                "aud": "some-other-client-id",
                "iss": "https://accounts.google.com",
            },
        ),
    )
    with pytest.raises(ValueError):
        provider.exchange_code(code="c", redirect_uri="https://app/cb")


def test_google_provider_rejects_bad_issuer():
    provider = GoogleIdentityProvider(
        client_id="cid",
        client_secret="csecret",
        transport=_mock_transport(
            token_response={"id_token": "tok"},
            tokeninfo_claims={
                "sub": "sub-1",
                "email": "a@b.com",
                "aud": "cid",
                "iss": "https://evil.example.com",
            },
        ),
    )
    with pytest.raises(ValueError):
        provider.exchange_code(code="c", redirect_uri="https://app/cb")


# --- email_verified gating (do not trust an unverified email) --------------------------


def test_google_provider_trusts_verified_email():
    """A tokeninfo with email_verified true (Google returns the string "true") is trusted."""
    provider = GoogleIdentityProvider(
        client_id="cid",
        client_secret="csecret",
        transport=_mock_transport(
            token_response={"id_token": "tok"},
            tokeninfo_claims={
                "sub": "sub-1",
                "email": "a@b.com",
                "email_verified": "true",
                "aud": "cid",
                "iss": "https://accounts.google.com",
            },
        ),
    )
    identity = provider.exchange_code(code="c", redirect_uri="https://app/cb")
    assert identity.google_sub == "sub-1"
    assert identity.email == "a@b.com"


def test_google_provider_does_not_trust_unverified_email():
    """An unverified email must NOT be populated; google_sub still resolves the identity."""
    provider = GoogleIdentityProvider(
        client_id="cid",
        client_secret="csecret",
        transport=_mock_transport(
            token_response={"id_token": "tok"},
            tokeninfo_claims={
                "sub": "sub-1",
                "email": "unverified@b.com",
                "email_verified": "false",
                "aud": "cid",
                "iss": "https://accounts.google.com",
            },
        ),
    )
    identity = provider.exchange_code(code="c", redirect_uri="https://app/cb")
    assert identity.google_sub == "sub-1"
    assert identity.email is None


def test_google_provider_does_not_trust_email_when_verified_absent():
    """When email_verified is absent entirely, the email is not trusted either."""
    provider = GoogleIdentityProvider(
        client_id="cid",
        client_secret="csecret",
        transport=_mock_transport(
            token_response={"id_token": "tok"},
            tokeninfo_claims={
                "sub": "sub-1",
                "email": "a@b.com",
                "aud": "cid",
                "iss": "https://accounts.google.com",
            },
        ),
    )
    identity = provider.exchange_code(code="c", redirect_uri="https://app/cb")
    assert identity.google_sub == "sub-1"
    assert identity.email is None
