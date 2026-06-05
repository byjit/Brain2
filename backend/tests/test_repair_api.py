"""PATCH /entries/{id} repair + GET /entries/failed surface (spec §7.4).

Drives the REST endpoints through the TestClient (offline fakes). PATCH re-enriches a
failed entry from the user note and flips it active; GET /entries/failed lists only failed
rows + a total count for the 'needs attention' badge (spec §7.4/§8).
"""

from brain2.db.connection import open_user_db

_DEV_USER = "test-user"


def _insert(conn, entry_id, *, status="failed", type="page", url=None, error="boom"):
    conn.execute(
        """
        INSERT INTO entries (id, url, original_url, title, note, note_source, content,
                             type, source_url, saved_at, updated_at, status, attempts,
                             error_message)
        VALUES (?, ?, ?, ?, NULL, 'body', NULL, ?, NULL, '2026-01-01T00:00:00Z',
                '2026-01-01T00:00:00Z', ?, 3, ?)
        """,
        (entry_id, url, url, f"Title {entry_id}", type, status, error),
    )
    conn.commit()


def test_patch_repair_flips_failed_to_active(client, tmp_path):
    with open_user_db(_DEV_USER, data_dir=tmp_path) as conn:
        _insert(conn, "e1", status="failed", type="page", url="https://x.test/blocked")

    resp = client.patch("/entries/e1", json={"note": "user-written description of this page"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == "e1"
    assert body["status"] == "active"
    assert body["note"] == "user-written description of this page"
    assert body["note_source"] == "user"
    assert body["error_message"] is None


def test_patch_missing_entry_returns_404(client):
    resp = client.patch("/entries/nope", json={"note": "anything"})
    assert resp.status_code == 404


def test_get_failed_returns_only_failed_rows_and_count(client, tmp_path):
    with open_user_db(_DEV_USER, data_dir=tmp_path) as conn:
        _insert(conn, "f1", status="failed", url="https://x.test/1", error="rate limited")
        _insert(conn, "f2", status="failed", url="https://x.test/2", error="no content")
        _insert(conn, "a1", status="active", url="https://x.test/3", error=None)
        _insert(conn, "p1", status="pending", url="https://x.test/4", error=None)

    resp = client.get("/entries/failed")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    ids = {e["id"] for e in body["entries"]}
    assert ids == {"f1", "f2"}
    # Each row carries the §7.4 fields needed for the repair surface.
    sample = body["entries"][0]
    assert set(sample) >= {"id", "url", "title", "note", "error_message", "updated_at"}


def test_get_failed_empty_when_none_failed(client, tmp_path):
    with open_user_db(_DEV_USER, data_dir=tmp_path) as conn:
        _insert(conn, "a1", status="active", url="https://x.test/3", error=None)

    resp = client.get("/entries/failed")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0
    assert body["entries"] == []
