"""Google identity provider behind an interface, with an offline fake (spec §12).

The dashboard's ``/api/auth/callback/google`` exchanges a Google authorization code for the user's
verified identity (``google_sub`` + ``email``). The real provider talks to Google's token
and tokeninfo endpoints; the fake returns canned identities so the entire auth suite runs
offline without ever contacting Google. ``build_identity_provider`` selects real-vs-fake
by config, mirroring the M3/M4/M5 ``factory.build_providers`` pattern.
"""

from dataclasses import dataclass
from typing import Protocol

import httpx

from brain2.config import Settings

_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"
# Accepted ``iss`` values for a Google-issued id_token.
_GOOGLE_ISSUERS = frozenset(
    {"accounts.google.com", "https://accounts.google.com"}
)


@dataclass(frozen=True)
class GoogleIdentity:
    """A verified Google identity returned by the provider."""

    google_sub: str
    email: str | None


class IdentityProvider(Protocol):
    """Exchanges a Google authorization code for a verified identity."""

    def exchange_code(self, *, code: str, redirect_uri: str) -> GoogleIdentity: ...


class GoogleIdentityProvider:
    """Real provider: exchanges the auth code at Google's token endpoint and verifies the
    returned ``id_token`` via Google's tokeninfo endpoint.

    tokeninfo validates the signature server-side, but a valid signature only proves the
    token is a genuine Google token — NOT that it was minted for *this* app. We therefore
    explicitly assert the ``aud`` (audience) equals our ``client_id`` and the ``iss`` is
    Google, rejecting otherwise. Without this, an id_token issued for any other Google
    OAuth client would be accepted (confused-deputy / token-substitution).
    """

    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        # Optional injected transport keeps the provider unit-testable without network.
        self._transport = transport

    def exchange_code(self, *, code: str, redirect_uri: str) -> GoogleIdentity:
        with httpx.Client(timeout=10.0, transport=self._transport) as client:
            token_resp = client.post(
                _GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
            token_resp.raise_for_status()
            id_token = token_resp.json()["id_token"]
            # tokeninfo validates the signature and returns the decoded claims.
            info_resp = client.get(_GOOGLE_TOKENINFO_URL, params={"id_token": id_token})
            info_resp.raise_for_status()
            claims = info_resp.json()
        # Audience + issuer binding: the token must have been minted FOR this app BY Google.
        if claims.get("aud") != self._client_id:
            raise ValueError("id_token audience does not match this client")
        if claims.get("iss") not in _GOOGLE_ISSUERS:
            raise ValueError("id_token issuer is not Google")
        # Only trust the email when Google asserts it is verified. tokeninfo returns
        # email_verified as the string "true" (id_token JWT claims use a real bool), so we
        # accept either. Identity stays bound to google_sub regardless; an unverified or
        # absent email is simply not populated (never trusted for display/account linking).
        return GoogleIdentity(
            google_sub=claims["sub"],
            email=claims.get("email") if _is_verified(claims.get("email_verified")) else None,
        )


def _is_verified(value: object) -> bool:
    """True iff Google's email_verified claim is truthy (bool ``True`` or string ``"true"``)."""
    return value is True or (isinstance(value, str) and value.lower() == "true")


class FakeIdentityProvider:
    """Offline fake: returns canned identities keyed by code so auth tests never hit Google."""

    def __init__(self, identities: dict[str, GoogleIdentity] | None = None) -> None:
        self._identities = identities or {}

    def exchange_code(self, *, code: str, redirect_uri: str) -> GoogleIdentity:
        if code in self._identities:
            return self._identities[code]
        # Deterministic default identity for any unconfigured code.
        return GoogleIdentity(google_sub=f"fake-sub-{code}", email=f"{code}@example.com")


def build_identity_provider(settings: Settings) -> IdentityProvider:
    """Return the real Google provider when configured, else the offline fake."""
    if settings.google_client_id and settings.google_client_secret:
        return GoogleIdentityProvider(
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
        )
    return FakeIdentityProvider()
