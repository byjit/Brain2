"""The background worker loop is wired into the FastAPI lifespan (spec §6).

We point DATA_DIR at a tmp dir holding one pending entry, run the app through its
lifespan with a short poll, and assert the entry was drained to ``active`` offline
(no GEMINI_API_KEY -> fake providers via the factory).
"""

import time

from fastapi.testclient import TestClient

from brain2.config import get_settings
from brain2.db.connection import open_user_db
from brain2.main import create_app


def _seed_pending_note(data_dir, user_id, entry_id):
    with open_user_db(user_id, data_dir=data_dir) as conn:
        conn.execute(
            """
            INSERT INTO entries (id, url, original_url, title, note, note_source, content,
                                 type, source_url, saved_at, updated_at, status, attempts)
            VALUES (?, NULL, NULL, NULL, NULL, 'body', 'lifespan note', 'note', NULL,
                    '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z', 'pending', 0)
            """,
            (entry_id,),
        )
        conn.commit()


def test_lifespan_worker_drains_queue(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    get_settings.cache_clear()  # pick up the patched DATA_DIR / absent key

    _seed_pending_note(tmp_path, "test-user", "life1")

    app = create_app(enable_worker=True)
    with TestClient(app):  # entering runs the lifespan -> starts the worker loop
        # The loop drains on startup; poll briefly for the activation.
        for _ in range(50):
            with open_user_db("test-user", data_dir=tmp_path) as conn:
                status = conn.execute(
                    "select status from entries where id = 'life1'"
                ).fetchone()["status"]
            if status == "active":
                break
            time.sleep(0.05)

    assert status == "active"
    get_settings.cache_clear()
