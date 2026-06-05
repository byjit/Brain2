"""Pydantic request/response models for the auth + token-management endpoints (spec §12)."""

from pydantic import BaseModel, Field


class CreateTokenRequest(BaseModel):
    """Body for creating a Personal Access Token."""

    name: str | None = Field(default=None, max_length=100, description="Human label for the key")


class CreateTokenResponse(BaseModel):
    """Result of creating a key — the raw ``api_key`` is shown EXACTLY ONCE."""

    id: str
    api_key: str = Field(description="The raw key, returned only at creation — store it now")
    prefix: str


class TokenInfo(BaseModel):
    """One key in the dashboard listing — never includes the secret or its hash."""

    id: str
    prefix: str
    name: str | None
    created_at: str
    last_used_at: str | None
    revoked: bool


class RevokeTokenResponse(BaseModel):
    """Result of revoking a key."""

    revoked: bool


class CurrentUserResponse(BaseModel):
    """The authenticated dashboard user (GET /auth/me)."""

    user_id: str
    email: str | None
    created_at: str
