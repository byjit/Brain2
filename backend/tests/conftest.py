"""Shared pytest fixtures.

Auth test seam (M7): a session-scoped tmp ``auth.db`` is configured via settings and
seeded with a known user + API key, so any test can authenticate offline with a real
Bearer credential (``AUTH_API_KEY``) without contacting Google. REST tests additionally
override ``get_current_user`` to inject the known user directly; MCP/transport tests send
the real Bearer header, which resolves through the seeded auth.db.
"""

import os

import pytest
from fastapi.testclient import TestClient

from brain2.db.connection import open_user_db
from brain2.deps import get_current_user, get_db
from brain2.main import create_app

# The known test user and the env-routed auth.db are wired by `_auth_seam` below.
_DEV_USER = "test-user"


@pytest.fixture(scope="session")
def _auth_db_path(tmp_path_factory):
    """A session-wide auth.db path so every test shares one seeded credential store."""
    return tmp_path_factory.mktemp("auth") / "auth.db"


@pytest.fixture(autouse=True)
def _auth_seam(_auth_db_path, monkeypatch):
    """Point settings at the tmp auth.db and seed a known user + API key (offline seam).

    Exposes the raw key on ``os.environ['AUTH_API_KEY']`` for MCP/transport tests that
    send a real Bearer header. The JWT secret is pinned so issued access tokens verify.
    """
    from brain2.auth import api_keys
    from brain2.auth.store import open_auth_db
    from brain2.config import get_settings

    monkeypatch.setenv("AUTH_DB_PATH", str(_auth_db_path))
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret")
    get_settings.cache_clear()

    with open_auth_db(_auth_db_path) as conn:
        existing = conn.execute(
            "SELECT user_id FROM users WHERE user_id=?", (_DEV_USER,)
        ).fetchone()
        if existing is None:
            conn.execute(
                "INSERT INTO users (user_id, google_sub, email, created_at) VALUES (?,?,?,?)",
                (_DEV_USER, "test-sub", "test@example.com", "2026-01-01T00:00:00Z"),
            )
            conn.commit()
            created = api_keys.create_key(conn, user_id=_DEV_USER, name="test")
            os.environ["AUTH_API_KEY"] = created.api_key
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _offline_unless_key_in_environ(monkeypatch):
    """Keep the default suite offline and deterministic.

    The repo ``.env`` is read by config, so ``Settings.gemini_api_key`` can be populated
    from the file even when ``GEMINI_API_KEY`` is absent from the process environment. The
    optional live smoke tests gate on ``os.environ`` directly; everything else must run
    offline with fakes. When the key is NOT exported to the environment, we force the
    cached settings' ``gemini_api_key`` to None so the provider factory selects fakes —
    matching the documented contract (AGENTS.md) and the smoke-test skip condition. With
    the key exported (the smoke-test run), real providers are used as before.
    """
    import brain2.config as config

    if os.environ.get("GEMINI_API_KEY"):
        yield
        return

    # Wrap the cached accessor so EVERY settings instance (including ones built after a
    # test calls get_settings.cache_clear() to pick up a patched DATA_DIR) has the key
    # forced to None. This is robust to fixture ordering and cache clears.
    real_get_settings = config.get_settings

    def _offline_get_settings():
        settings = real_get_settings()
        object.__setattr__(settings, "gemini_api_key", None)
        # Force the offline FakeIdentityProvider too: the repo .env carries real Google
        # creds, but no test may contact Google (M7). The factory selection is unit-tested
        # in test_identity_provider.py by constructing Settings directly.
        object.__setattr__(settings, "google_client_id", None)
        object.__setattr__(settings, "google_client_secret", None)
        return settings

    _offline_get_settings.cache_clear = real_get_settings.cache_clear
    monkeypatch.setattr(config, "get_settings", _offline_get_settings)
    # Patch the already-imported references in modules that bound the name directly.
    for module_name in (
        "brain2.services.worker",
        "brain2.mcp.tools",
        "brain2.api.entries",
        "brain2.api.auth",
        "brain2.api.settings_tokens",
        "brain2.auth.deps",
        "brain2.deps",
        "brain2.mcp.auth",
    ):
        import importlib

        try:
            module = importlib.import_module(module_name)
        except ImportError:
            continue
        if getattr(module, "get_settings", None) is real_get_settings:
            monkeypatch.setattr(module, "get_settings", _offline_get_settings)
    yield


@pytest.fixture
def client(tmp_path):
    # Disable the background worker loop: API tests drive a tmp DATA_DIR via overrides,
    # and the loop would otherwise scan the real configured data dir.
    app = create_app(enable_worker=False)

    def _override_get_db():
        with open_user_db(_DEV_USER, data_dir=tmp_path) as conn:
            yield conn

    app.dependency_overrides[get_current_user] = lambda: _DEV_USER
    app.dependency_overrides[get_db] = _override_get_db

    with TestClient(app) as c:
        yield c
