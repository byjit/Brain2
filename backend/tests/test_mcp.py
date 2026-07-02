"""MCP save/retrieve tools (spec §10).

Tests call the tool implementations directly with an explicit user context, proving:
- save reuses the M1 entries service and routes to the resolved user's DB,
- save then retrieve round-trips over BM25,
- the Bearer token resolves to the dev user id (auth stub; real auth is M7).
"""

import pytest

from brain2.mcp import auth
from brain2.mcp.tools import _window_to_saved_after, list_tool, retrieve_tool, save_tool


@pytest.fixture(autouse=True)
def temp_data_dir(tmp_path, monkeypatch):
    """Point per-user DB routing at a temp dir so tests never touch ./data.

    Also blank GEMINI_API_KEY so retrieve's hybrid leg wires the offline FakeEmbedder
    (the factory selects real-vs-fake by config) — tests never hit the network. The env
    var is set to "" (not unset) so it overrides the repo-root .env, which pydantic
    would otherwise still read.
    """
    from brain2.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GEMINI_API_KEY", "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_valid_api_key_resolves_to_its_user():
    """M7: a real seeded API key (conftest) resolves through auth.db to its owner."""
    import os

    user_id = auth.resolve_token_to_user_id(f"Bearer {os.environ['AUTH_API_KEY']}")
    assert user_id == "test-user"


def test_missing_or_malformed_token_rejected():
    assert auth.resolve_token_to_user_id(None) is None
    assert auth.resolve_token_to_user_id("Token abc") is None
    # An unknown API key no longer resolves to a dev stub — it is rejected (M7).
    assert auth.resolve_token_to_user_id("Bearer br2_live_unknown") is None


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


def _last_accessed(user_id, entry_id):
    from brain2.config import get_settings
    from brain2.db.connection import open_user_db

    with open_user_db(user_id, data_dir=get_settings().data_dir) as conn:
        return conn.execute(
            "select last_accessed_at from entries where id = ?", (entry_id,)
        ).fetchone()["last_accessed_at"]


def test_retrieve_sets_last_accessed_at_on_hits():
    """Task 5: every entry in retrieve's final hit set gets last_accessed_at stamped."""
    from brain2.config import get_settings

    user_id = get_settings().dev_user_id
    with auth.user_scope(user_id):
        saved = save_tool(type="note", note="the quokka is a small marsupial")
        assert _last_accessed(user_id, saved["id"]) is None  # not set on save

        hits = retrieve_tool(query="quokka marsupial")
        assert any(h["id"] == saved["id"] for h in hits)
        # It is not exposed in the compact projection returned to the agent.
        assert all("last_accessed_at" not in h for h in hits)

    stamped = _last_accessed(user_id, saved["id"])
    assert stamped is not None and stamped  # ISO-8601 timestamp written


def test_list_does_not_set_last_accessed_at():
    """Task 5: list is a deterministic browse and must NOT stamp last_accessed_at."""
    from brain2.config import get_settings

    user_id = get_settings().dev_user_id
    with auth.user_scope(user_id):
        saved = save_tool(type="note", note="deterministic browse should not touch access time")
        # Make it surface in list: it must be active. Force it active for the read model.
        from brain2.db.connection import open_user_db

        with open_user_db(user_id, data_dir=get_settings().data_dir) as conn:
            conn.execute("update entries set status='active' where id=?", (saved["id"],))
            conn.commit()

        results = list_tool()
        assert any(r["id"] == saved["id"] for r in results)

    assert _last_accessed(user_id, saved["id"]) is None


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


def test_save_with_agent_tags_canonicalizes_and_persists():
    """Spec §10: agent-supplied tags are normalized + canonicalized before write, merged
    additively into the entry's tags (updating counters/tags_text)."""
    from brain2.config import get_settings
    from brain2.db.connection import open_user_db

    user_id = get_settings().dev_user_id
    with auth.user_scope(user_id):
        saved = save_tool(
            type="note", note="remember the tokio runtime trick", tags=["Rust", "Async"]
        )

    with open_user_db(user_id, data_dir=get_settings().data_dir) as conn:
        edges = {
            r[0] for r in conn.execute(
                "SELECT tag FROM entry_tags WHERE entry_id = ?", (saved["id"],)
            )
        }
        assert edges == {"rust", "async"}  # normalized to lowercase
        for tag in ("rust", "async"):
            assert conn.execute("SELECT count FROM tags WHERE name=?", (tag,)).fetchone()[0] == 1


def test_list_returns_active_entries_for_resolved_user():
    """list routes to the resolved user's DB and returns active entries (no query)."""
    from brain2.config import get_settings
    from brain2.db.connection import open_user_db

    user_id = get_settings().dev_user_id
    with auth.user_scope(user_id):
        saved = save_tool(type="note", note="a listable memory")
        # save lands rows as 'pending'; the worker activates them. Force active here so
        # the deterministic list surfaces it without running the async pipeline.
        with open_user_db(user_id, data_dir=get_settings().data_dir) as conn:
            conn.execute("UPDATE entries SET status='active' WHERE id=?", (saved["id"],))
            conn.commit()

        rows = list_tool()
        assert any(r["id"] == saved["id"] for r in rows)
        assert all("score" not in r for r in rows)  # deterministic list carries no score


def test_list_outside_user_scope_raises():
    with pytest.raises(PermissionError):
        list_tool()


def test_list_negative_limit_rejected_with_clear_error():
    from brain2.config import get_settings

    with auth.user_scope(get_settings().dev_user_id):
        with pytest.raises(ValueError, match="limit must be >= 0"):
            list_tool(limit=-1)


def test_window_to_saved_after_translates_units():
    """A relative window resolves to now-minus-window, ISO-8601 UTC (matches saved_at)."""
    from datetime import datetime, timezone

    now = datetime(2026, 6, 27, 12, 0, 0, tzinfo=timezone.utc)
    assert _window_to_saved_after("30m", now=now) == "2026-06-27T11:30:00+00:00"
    assert _window_to_saved_after("24h", now=now) == "2026-06-26T12:00:00+00:00"
    assert _window_to_saved_after("3d", now=now) == "2026-06-24T12:00:00+00:00"
    assert _window_to_saved_after("2w", now=now) == "2026-06-13T12:00:00+00:00"
    # Unit letter is case-insensitive and surrounding whitespace is tolerated.
    assert _window_to_saved_after(" 1H ", now=now) == "2026-06-27T11:00:00+00:00"


def test_window_rejects_unparseable_value():
    with pytest.raises(ValueError, match="window must be"):
        _window_to_saved_after("yesterday")


def test_list_window_filters_to_recent_entries():
    """list(window=...) keeps entries saved within the window, drops older ones."""
    from brain2.config import get_settings
    from brain2.db.connection import open_user_db

    user_id = get_settings().dev_user_id
    with auth.user_scope(user_id):
        recent = save_tool(type="note", note="saved just now")
        old = save_tool(type="note", note="saved long ago")
        with open_user_db(user_id, data_dir=get_settings().data_dir) as conn:
            conn.execute(
                "UPDATE entries SET status='active' WHERE id IN (?, ?)",
                (recent["id"], old["id"]),
            )
            # Pin the old entry well outside any plausible recent window.
            conn.execute(
                "UPDATE entries SET saved_at='2026-01-01T00:00:00+00:00' WHERE id=?",
                (old["id"],),
            )
            conn.commit()

        ids = {r["id"] for r in list_tool(window="24h")}
        assert recent["id"] in ids
        assert old["id"] not in ids


def test_retrieve_outside_user_scope_raises():
    with pytest.raises(PermissionError):
        retrieve_tool(query="anything")


def test_retrieve_negative_limit_rejected_with_clear_error():
    # A negative limit otherwise reaches vec0 KNN (raw OperationalError) on one leg and
    # becomes unbounded LIMIT -1 on the other; reject it at the boundary instead.
    from brain2.config import get_settings

    with auth.user_scope(get_settings().dev_user_id):
        with pytest.raises(ValueError, match="limit must be >= 0"):
            retrieve_tool(query="anything", limit=-1)
