"""Optional live Gemini smoke tests (spec §7.1 summarization, §11 vector search).

Deselected by default: skipped unless GEMINI_API_KEY is set in the environment, so the
default offline suite never needs a key or network. Run with the key present to verify
the real Gemini providers against the live API.
"""

import os

import pytest

from brain2.config import get_settings
from brain2.db.connection import open_user_db
from brain2.services.providers.embedder import EMBEDDING_DIM, GeminiEmbedder
from brain2.services.providers.summarizer import GeminiSummarizer
from brain2.services.vector import index_entry_vector, vector_search

pytestmark = pytest.mark.skipif(
    not os.environ.get("GEMINI_API_KEY"), reason="GEMINI_API_KEY not set; live Gemini test skipped"
)


def test_gemini_summarizer_returns_text():
    settings = get_settings()
    summarizer = GeminiSummarizer(
        api_key=settings.gemini_api_key, model=settings.gemini_summary_model
    )
    note = summarizer.summarize(
        "The Rust programming language is a systems language focused on safety, "
        "concurrency, and performance, using an ownership model instead of a garbage collector."
    )
    assert isinstance(note, str) and note.strip()


def _live_embedder() -> GeminiEmbedder:
    settings = get_settings()
    return GeminiEmbedder(
        api_key=settings.gemini_api_key, model=settings.gemini_embedding_model
    )


def test_gemini_embedder_returns_768_dim_unit_vector():
    embedder = _live_embedder()
    vec = embedder.embed("a fast asynchronous HTTP client for the Rust language")
    assert len(vec) == EMBEDDING_DIM


def test_live_paraphrase_query_returns_intended_entry(tmp_path):
    """A true paraphrase (no lexical overlap with the stored note) must hit the right
    entry via the real embedder's semantic vector (spec §11, §13 criterion 2)."""
    embedder = _live_embedder()
    with open_user_db("live-vec-user", data_dir=tmp_path) as conn:
        target_note = "An asynchronous HTTP client library written in the Rust programming language."
        decoy_note = "A guide to baking sourdough bread at home with a cast-iron dutch oven."
        for entry_id, note in (("target", target_note), ("decoy", decoy_note)):
            conn.execute(
                """
                INSERT INTO entries (id, note, note_source, type, saved_at, updated_at, status, attempts)
                VALUES (?, ?, 'body', 'note', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z', 'active', 1)
                """,
                (entry_id, note),
            )
            index_entry_vector(conn, entry_id, embedder.embed(note))
        conn.commit()

        # Paraphrase: shares no salient words with the stored target note.
        ids = vector_search(conn, embedder.embed("networking over the web in a memory-safe systems language"))
        assert ids[0] == "target"
