"""Resilient async enrichment worker (spec §7.1 async portion, §7.4).

Turns ``pending``/``failed`` entries into ``active`` ones: resolve the note basis via
the fallback ladder, summarize, record provenance, re-index FTS, set active. On failure
it retries below a ceiling (gated by an enforced exponential-backoff ``next_retry_at``)
and marks the entry ``failed`` with an ``error_message`` once the ceiling is reached. A
crash mid-pipeline leaves a ``processing`` row that the startup reaper requeues, and an
empty resolved note is surfaced as a failure rather than a silently-active blank (spec §7.4).

The core ``process_entry`` / ``process_pending`` functions are synchronous and take the
external providers injected, so they are directly unit-testable offline. ``run_worker_loop``
wires a background drain into the FastAPI lifespan over all user DBs. Embeddings, vector
indexing, and auto-tagging are later milestones and intentionally not done here.
"""

import asyncio
import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from brain2.config import get_settings
from brain2.services.providers.factory import build_providers
from brain2.db.connection import open_user_db
from brain2.services.fts import index_entry
from brain2.services.note_resolver import resolve_note
from brain2.services.providers.embedder import Embedder
from brain2.services.providers.page_fetcher import PageFetcher
from brain2.services.providers.summarizer import Summarizer
from brain2.services.vector import index_entry_vector

logger = logging.getLogger(__name__)

# Statuses the worker is allowed to claim. ``active`` is never reprocessed (spec §10
# "re-saving does not re-summarize"); ``processing`` is already claimed by another run
# so it is skipped to prevent double-pickup.
_CLAIMABLE = ("pending", "failed")

# A ``processing`` row whose ``updated_at`` is older than this was claimed by a worker
# that crashed mid-pipeline; it is reset to ``pending`` on startup so it is reprocessed
# instead of becoming a silent black hole (spec §7.4).
_STALE_PROCESSING_LEASE_SECONDS = 600

# Upper bound on characters sent to the embedder. The embedding API has an input token
# limit, so a very large note (tens of KB) would fail to embed on every attempt and turn
# an otherwise-valid entry into a permanent failure. We embed a bounded prefix instead so
# the entry still gets a (representative) semantic vector and stays activatable; FTS still
# indexes the full content (spec §7.4 no silent black hole). ~8k chars stays comfortably
# under the model's token budget while capturing the note's gist.
_EMBED_INPUT_MAX_CHARS = 8_000


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _backoff_seconds(attempts: int) -> int:
    """Exponential backoff delay for the next retry (1st retry -> 2s, then 4s, 8s...)."""
    return 2**attempts


def process_entry(
    conn: sqlite3.Connection,
    entry_id: str,
    *,
    fetcher: PageFetcher,
    summarizer: Summarizer,
    embedder: Embedder | None = None,
    max_attempts: int | None = None,
) -> bool:
    """Process a single entry. Returns True if it was claimed and run, else False.

    Idempotent and safe to re-run: only ``pending``/``failed`` entries below the retry
    ceiling are claimed (atomically flipped to ``processing`` so a concurrent run cannot
    pick the same row). ``active``/``processing`` rows are skipped.

    When an ``embedder`` is provided, the resolved note is embedded and upserted into
    ``entries_vec`` (clearing any prior vector) so the vector half of retrieval is in
    lockstep with the note (spec §7.1 step 8). The production loop always supplies one;
    it is optional only so note-only unit tests need not wire an embedder.
    """
    ceiling = max_attempts if max_attempts is not None else get_settings().worker_max_attempts

    # Atomically claim the row: only succeeds for a claimable status below the ceiling
    # whose backoff window has elapsed, flipping it to 'processing' so no other worker
    # picks it up (double-pickup guard). ``updated_at`` is stamped so a crash mid-pipeline
    # leaves a measurable staleness for the reaper (spec §7.4).
    now = _now_iso()
    claimed = conn.execute(
        f"""
        UPDATE entries SET status = 'processing', attempts = attempts + 1, updated_at = ?
         WHERE id = ?
           AND status IN ({",".join("?" * len(_CLAIMABLE))})
           AND attempts < ?
           AND (next_retry_at IS NULL OR next_retry_at <= ?)
        """,
        (now, entry_id, *_CLAIMABLE, ceiling, now),
    )
    if claimed.rowcount == 0:
        conn.commit()  # release the implicit transaction; nothing to do
        return False
    conn.commit()

    row = conn.execute("select * from entries where id = ?", (entry_id,)).fetchone()
    try:
        resolved = resolve_note(dict(row), fetcher=fetcher, summarizer=summarizer)
        if not (resolved.note or "").strip():
            # No usable content was extracted. Marking this 'active' would leave a blank,
            # unrepairable entry — the silent black hole spec §7.4 forbids — so route it
            # through the retry/fail path with an actionable message instead.
            conn.rollback()
            target = row["url"] or entry_id
            _record_failure(conn, entry_id, f"no extractable content from {target}", ceiling)
            return True
        conn.execute(
            """
            UPDATE entries
               SET note = ?, note_source = ?, status = 'active',
                   error_message = NULL, next_retry_at = NULL, updated_at = ?
             WHERE id = ?
            """,
            (resolved.note, resolved.note_source, _now_iso(), entry_id),
        )
        # Re-index FTS from the effective row so the (new) note's content stays searchable
        # alongside title + tags + any persisted body.
        effective = conn.execute(
            "select title, content from entries where id = ?", (entry_id,)
        ).fetchone()
        index_entry(conn, entry_id, effective["title"], effective["content"])
        # Embed the NOTE (not the body) into entries_vec for semantic search (spec §11);
        # delete-then-insert keeps exactly one vector per entry across re-enrichment.
        if embedder is not None:
            # Bound the embedder input so an oversized note cannot fail every attempt and
            # block activation; FTS above already indexed the full content.
            index_entry_vector(
                conn, entry_id, embedder.embed(resolved.note[:_EMBED_INPUT_MAX_CHARS])
            )
        conn.commit()
        return True
    except Exception as exc:  # noqa: BLE001 — any provider error is a processing failure
        conn.rollback()
        _record_failure(conn, entry_id, str(exc), ceiling)
        return True


def _record_failure(conn: sqlite3.Connection, entry_id: str, message: str, ceiling: int) -> None:
    """Mark a failed attempt: ``failed`` at the ceiling, else back to ``pending`` (spec §7.4)."""
    attempts = conn.execute(
        "select attempts from entries where id = ?", (entry_id,)
    ).fetchone()["attempts"]

    if attempts >= ceiling:
        # Exhausted retries -> surface to the user for repair (spec §7.4).
        conn.execute(
            "UPDATE entries SET status = 'failed', error_message = ?, updated_at = ? WHERE id = ?",
            (message, _now_iso(), entry_id),
        )
    else:
        # Transient: return to the queue for a later retry, gated by an exponential
        # backoff stamp so the next poll cannot re-claim it before the delay elapses
        # (spec §7.4). ``next_retry_at`` is enforced by the claim UPDATE / drain SELECT.
        delay = _backoff_seconds(attempts)
        next_retry_at = (_now() + timedelta(seconds=delay)).isoformat()
        conn.execute(
            """
            UPDATE entries
               SET status = 'pending', error_message = ?, next_retry_at = ?, updated_at = ?
             WHERE id = ?
            """,
            (f"retry in {delay}s: {message}", next_retry_at, _now_iso(), entry_id),
        )
    conn.commit()


def process_pending(
    conn: sqlite3.Connection,
    *,
    fetcher: PageFetcher,
    summarizer: Summarizer,
    embedder: Embedder | None = None,
    max_attempts: int | None = None,
) -> int:
    """Drain all claimable entries in one DB. Returns the number successfully activated."""
    ceiling = max_attempts if max_attempts is not None else get_settings().worker_max_attempts
    ids = [
        r[0]
        for r in conn.execute(
            f"""
            SELECT id FROM entries
             WHERE status IN ({",".join("?" * len(_CLAIMABLE))}) AND attempts < ?
               AND (next_retry_at IS NULL OR next_retry_at <= ?)
             ORDER BY saved_at
            """,
            (*_CLAIMABLE, ceiling, _now_iso()),
        ).fetchall()
    ]
    activated = 0
    for entry_id in ids:
        process_entry(
            conn, entry_id, fetcher=fetcher, summarizer=summarizer,
            embedder=embedder, max_attempts=ceiling,
        )
        row = conn.execute("select status from entries where id = ?", (entry_id,)).fetchone()
        if row["status"] == "active":
            activated += 1
    return activated


def reset_stale_processing(
    conn: sqlite3.Connection, *, lease_seconds: int = _STALE_PROCESSING_LEASE_SECONDS
) -> int:
    """Requeue ``processing`` rows abandoned by a crashed worker (spec §7.4).

    A row stuck in ``processing`` whose ``updated_at`` is older than the lease was claimed
    by a worker that died mid-pipeline; it is flipped back to ``pending`` so it is
    reprocessed. The age guard avoids stealing a genuinely in-flight row in a multi-process
    deploy. Returns the number of rows reset.
    """
    cutoff = (_now() - timedelta(seconds=lease_seconds)).isoformat()
    reset = conn.execute(
        """
        UPDATE entries
           SET status = 'pending', updated_at = ?
         WHERE status = 'processing' AND updated_at <= ?
        """,
        (_now_iso(), cutoff),
    )
    conn.commit()
    return reset.rowcount


def drain_all_users(
    data_dir: Path,
    *,
    fetcher: PageFetcher,
    summarizer: Summarizer,
    embedder: Embedder | None = None,
    max_attempts: int | None = None,
) -> int:
    """Scan every ``{user_id}.db`` under ``data_dir`` and drain its queue (spec §6, §7.1).

    Returns the total number of entries activated across all user DBs. Each DB is opened
    in isolation, honoring per-user isolation. A failure draining one DB (locked, corrupt,
    truncated) is logged and skipped so it never aborts the rest of the scan. Safe on a
    missing/empty directory.
    """
    if not data_dir.exists():
        return 0
    total = 0
    for db_file in sorted(data_dir.glob("*.db")):
        user_id = db_file.stem
        try:
            with open_user_db(user_id, data_dir=data_dir) as conn:
                reset_stale_processing(conn)
                total += process_pending(
                    conn, fetcher=fetcher, summarizer=summarizer,
                    embedder=embedder, max_attempts=max_attempts,
                )
        except Exception:  # noqa: BLE001 — one bad DB must not abort the whole drain
            logger.exception("Failed to drain user DB %s; skipping", user_id)
    return total


async def run_worker_loop(*, poll_interval: float = 10.0) -> None:
    """Background drain loop for the FastAPI lifespan (spec §6, §7.1).

    On startup and then every ``poll_interval`` seconds it scans all user DBs and drains
    their queues. Providers are wired from config (real Gemini when keyed, else fakes).
    Blocking DB work runs in a thread so the event loop stays responsive; the loop ends
    cleanly when the surrounding task is cancelled at shutdown.
    """
    settings = get_settings()
    summarizer, fetcher, embedder = build_providers(settings)
    while True:
        try:
            await asyncio.to_thread(
                drain_all_users,
                settings.data_dir,
                fetcher=fetcher,
                summarizer=summarizer,
                embedder=embedder,
            )
        except asyncio.CancelledError:
            # Graceful shutdown: stop draining and let the task unwind.
            raise
        except Exception:  # noqa: BLE001 — an unexpected cycle error must not kill the loop
            logger.exception("Worker drain cycle failed; continuing to next poll")
        await asyncio.sleep(poll_interval)
