"""Shared pytest fixtures.

A TestClient wired to a temp DATA_DIR so tests never touch the real ./data.
The get_db dependency is overridden to open a per-test user DB under tmp_path.
"""

import os

import pytest
from fastapi.testclient import TestClient

from brain2.db.connection import open_user_db
from brain2.deps import get_current_user, get_db
from brain2.main import create_app

_DEV_USER = "test-user"


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
        return settings

    _offline_get_settings.cache_clear = real_get_settings.cache_clear
    monkeypatch.setattr(config, "get_settings", _offline_get_settings)
    # Patch the already-imported references in modules that bound the name directly.
    for module_name in ("brain2.services.worker", "brain2.mcp.tools", "brain2.api.entries"):
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
