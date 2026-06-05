"""Integration tests for POST /entries (spec §7.1 sync portion, §10 save)."""


def _post(client, **body):
    return client.post("/entries", json=body)


def test_save_new_page_returns_saved_status(client):
    r = _post(client, url="https://example.com/article", title="Article", type="page")
    assert r.status_code == 201
    data = r.json()
    assert data["status"] == "saved"
    assert data["id"]


def test_page_content_is_not_persisted(client):
    r = _post(client, url="https://example.com/p", captured_text="long body text", type="page")
    entry_id = r.json()["id"]
    # Inspect via a second request path is not available; query DB through a note round-trip.
    # Instead re-save same URL to confirm dedup, then check content via the entries table.
    row = _fetch_entry(client, entry_id)
    assert row["content"] is None


def test_note_content_is_persisted(client):
    r = _post(client, captured_text="my private note", type="note")
    row = _fetch_entry(client, r.json()["id"])
    assert row["content"] == "my private note"
    assert row["url"] is None


def test_clip_persists_content_and_source_url(client):
    r = _post(
        client,
        url="https://example.com/page",
        captured_text="highlighted snippet",
        type="clip",
        source_url="https://example.com/page",
    )
    row = _fetch_entry(client, r.json()["id"])
    assert row["content"] == "highlighted snippet"
    assert row["source_url"] == "https://example.com/page"


def test_url_is_normalized_on_save(client):
    r = _post(client, url="HTTPS://Example.com/Path/?utm_source=x", type="page")
    row = _fetch_entry(client, r.json()["id"])
    assert row["url"] == "https://example.com/Path"
    assert row["original_url"] == "HTTPS://Example.com/Path/?utm_source=x"


def test_dedup_by_normalized_url_returns_updated(client):
    first = _post(client, url="https://example.com/x?utm_source=a", title="One", type="page")
    second = _post(client, url="https://example.com/x?utm_source=b", title="Two", type="page")
    assert first.json()["status"] == "saved"
    assert second.json()["status"] == "updated"
    # Same id -> it was an update, not a new row.
    assert first.json()["id"] == second.json()["id"]
    row = _fetch_entry(client, second.json()["id"])
    assert row["title"] == "Two"


def test_dedup_update_preserves_title_when_omitted(client):
    # Finding #1: re-saving a known URL without a title must keep the stored title.
    first = _post(client, url="https://example.com/keep", title="Original", type="page")
    second = _post(client, url="https://example.com/keep", type="page")
    assert second.json()["status"] == "updated"
    row = _fetch_entry(client, second.json()["id"])
    assert row["title"] == "Original"


def test_dedup_update_does_not_destroy_persisted_clip_content(client):
    # Finding #1/#5: re-saving a URL first captured as a clip (content is the only copy)
    # as a content-less page must not null the stored content or downgrade the type.
    first = _post(
        client,
        url="https://example.com/highlight",
        captured_text="the only copy of this highlight",
        type="clip",
        source_url="https://example.com/highlight",
    )
    entry_id = first.json()["id"]
    second = _post(client, url="https://example.com/highlight", type="page")
    assert second.json()["id"] == entry_id
    row = _fetch_entry(client, entry_id)
    assert row["content"] == "the only copy of this highlight"


def test_dedup_update_preserves_source_url_when_omitted(client):
    first = _post(
        client,
        url="https://example.com/src",
        captured_text="snippet",
        type="clip",
        source_url="https://example.com/origin",
    )
    second = _post(client, url="https://example.com/src", type="page")
    row = _fetch_entry(client, second.json()["id"])
    assert row["source_url"] == "https://example.com/origin"


def test_note_does_not_store_url_as_dedup_key(client):
    # Finding #2: a note carrying a URL must store url=None so it can never collide
    # with a later URL-backed save of the same normalized URL.
    note = _post(client, url="https://example.com/collide", captured_text="my note", type="note")
    note_id = note.json()["id"]
    note_row = _fetch_entry(client, note_id)
    assert note_row["url"] is None

    # A later page save of the same URL must NOT match/clobber the note.
    page = _post(client, url="https://example.com/collide", type="page", title="Page")
    assert page.json()["status"] == "saved"
    assert page.json()["id"] != note_id
    # The note's text (its only copy) is intact.
    note_row_after = _fetch_entry(client, note_id)
    assert note_row_after["content"] == "my note"
    assert note_row_after["type"] == "note"


def test_notes_never_dedup(client):
    a = _post(client, captured_text="note a", type="note")
    b = _post(client, captured_text="note a", type="note")
    assert a.json()["status"] == "saved"
    assert b.json()["status"] == "saved"
    assert a.json()["id"] != b.json()["id"]


def test_new_entry_status_is_pending(client):
    r = _post(client, url="https://example.com/pending", type="page")
    row = _fetch_entry(client, r.json()["id"])
    assert row["status"] == "pending"
    assert row["attempts"] == 0
    assert row["saved_at"] and row["updated_at"]


def test_note_source_defaults_to_body_for_page(client):
    r = _post(client, url="https://example.com/q", type="page")
    row = _fetch_entry(client, r.json()["id"])
    assert row["note_source"] == "body"


def test_note_type_note_source_is_user(client):
    r = _post(client, captured_text="typed", type="note")
    row = _fetch_entry(client, r.json()["id"])
    assert row["note_source"] == "user"


def test_invalid_type_rejected(client):
    r = _post(client, url="https://example.com/z", type="bogus")
    assert r.status_code == 422


def test_note_without_text_rejected(client):
    # A note has no URL; its text is the only content, so it must be present.
    r = _post(client, type="note")
    assert r.status_code == 422


def test_page_without_url_rejected(client):
    r = _post(client, type="page", captured_text="x")
    assert r.status_code == 422


# --- helper that reads an entry row back through a debug-free path ---------------

def _fetch_entry(client, entry_id):
    """Read a row directly from the test's DB via the app's connection override."""
    from brain2.deps import get_db

    gen = client.app.dependency_overrides[get_db]()
    conn = next(gen)
    try:
        row = conn.execute("select * from entries where id = ?", (entry_id,)).fetchone()
        return dict(row)
    finally:
        gen.close()
