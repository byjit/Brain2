"""Personal Access Token management endpoints (spec §12, §6 /settings/tokens).

Back the dashboard's API-key UI. All require an authenticated dashboard session (cookie)
or a Bearer credential. The raw key is returned ONCE on creation; the listing never leaks
the secret or its hash.
"""

import sqlite3

from fastapi import APIRouter, Depends, status

from brain2.auth import api_keys
from brain2.auth.deps import get_auth_db, get_session_user, require_same_origin
from brain2.models.auth import (
    CreateTokenRequest,
    CreateTokenResponse,
    RevokeTokenResponse,
    TokenInfo,
)

router = APIRouter(prefix="/settings/tokens", tags=["auth"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=CreateTokenResponse,
    dependencies=[Depends(require_same_origin)],
)
def create_token(
    req: CreateTokenRequest,
    user_id: str = Depends(get_session_user),
    conn: sqlite3.Connection = Depends(get_auth_db),
) -> CreateTokenResponse:
    """Create a Personal Access Token; the raw key is shown exactly once (spec §12)."""
    created = api_keys.create_key(conn, user_id=user_id, name=req.name)
    return CreateTokenResponse(id=created.id, api_key=created.api_key, prefix=created.prefix)


@router.get("", response_model=list[TokenInfo])
def list_tokens(
    user_id: str = Depends(get_session_user),
    conn: sqlite3.Connection = Depends(get_auth_db),
) -> list[TokenInfo]:
    """List the user's keys (prefix, name, timestamps, revoked) — never the secret."""
    return [TokenInfo(**row) for row in api_keys.list_keys(conn, user_id)]


@router.delete(
    "/{token_id}",
    response_model=RevokeTokenResponse,
    dependencies=[Depends(require_same_origin)],
)
def revoke_token(
    token_id: str,
    user_id: str = Depends(get_session_user),
    conn: sqlite3.Connection = Depends(get_auth_db),
) -> RevokeTokenResponse:
    """Revoke one of the user's keys (only the owner can revoke it)."""
    return RevokeTokenResponse(revoked=api_keys.revoke_key(conn, user_id, token_id))
