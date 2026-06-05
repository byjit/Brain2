"""MCP save/retrieve tools (spec §10).

Tests call the tool implementations directly with an explicit user context, proving:
- save reuses the M1 entries service and routes to the resolved user's DB,
- save then retrieve round-trips over BM25,
- the Bearer token resolves to the dev user id (auth stub; real auth is M7).
"""

import pytest

from brain2.mcp import auth
from brain2.mcp.tools import retrieve_tool, save_tool


@pytest.fixture(autouse=True)
def temp_data_dir(tmp_path, monkeypatch):
    """Point per-user DB routing at a temp dir so tests never touch ./data."""
    from brain2.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_bearer_token_resolves_to_dev_user():
    from brain2.config import get_settings

    user_id = auth.resolve_token_to_user_id("Bearer br2_live_anything")
    assert user_id == get_settings().dev_user_id


def test_missing_or_malformed_token_rejected():
    assert auth.resolve_token_to_user_id(None) is None
    assert auth.resolve_token_to_user_id("Token abc") is None


def test_save_then_retrieve_round_trip():
    from brain2.config import get_settings

    user_id = get_settings().dev_user_id
    with auth.user_scope(user_id):
        saved = save_tool(url="https://ex.com/hyper", title="Hyper HTTP", type="page")
        assert saved["status"] == "saved"
        assert saved["id"]

        results = retrieve_tool(query="hyper")
        assert any(r["id"] == saved["id"] for r in results)
        top = next(r for r in results if r["id"] == saved["id"])
        assert top["title"] == "Hyper HTTP"


def test_save_routes_to_resolved_user_db(tmp_path):
    """A save under one user's scope lands only in that user's DB file."""
    from brain2.config import get_settings
    from brain2.db.connection import open_user_db

    user_id = get_settings().dev_user_id
    with auth.user_scope(user_id):
        saved = save_tool(type="note", note="private memory")

    with open_user_db(user_id, data_dir=get_settings().data_dir) as conn:
        row = conn.execute("select id, note from entries where id = ?", (saved["id"],)).fetchone()
        assert row is not None
        assert row["note"] == "private memory"


def test_note_save_maps_note_to_captured_text():
    from brain2.config import get_settings

    with auth.user_scope(get_settings().dev_user_id):
        saved = save_tool(type="note", note="remember the tokio runtime trick")
        results = retrieve_tool(query="tokio")
        assert any(r["id"] == saved["id"] for r in results)


def test_save_note_override_populates_note_column_for_page():
    """Spec §10: `note` is an override that survives and is reflected back in retrieve.

    For a URL-backed type (page) the agent-supplied note must land in entries.note
    with note_source='user', not be silently dropped by the page content rule.
    """
    from brain2.config import get_settings
    from brain2.db.connection import open_user_db

    user_id = get_settings().dev_user_id
    with auth.user_scope(user_id):
        saved = save_tool(
            type="page",
            url="https://ex.com/with-note",
            note="agent-supplied summary of this page",
        )

    with open_user_db(user_id, data_dir=get_settings().data_dir) as conn:
        row = conn.execute(
            "select note, note_source from entries where id = ?", (saved["id"],)
        ).fetchone()
        assert row["note"] == "agent-supplied summary of this page"
        assert row["note_source"] == "user"


def test_retrieve_outside_user_scope_raises():
    with pytest.raises(PermissionError):
        retrieve_tool(query="anything")
