"""Canonicalize-on-write + tag embedding layer (spec §7.2 mechanism 3, §9.3).

Offline with FakeEmbedder (similarity-meaningful). Covers: snap-to-existing on a close
description (reuse, no duplicate), create-new on a distant one (with description embedded
into tags_vec), the per-entry cap, exact-name reuse, and reuse-over-invention bias.
"""

import pytest

from brain2.db.connection import open_user_db
from brain2.services.canonicalize import TagCandidate, canonicalize_candidates
from brain2.services.providers.embedder import FakeEmbedder
from brain2.services.tags_vector import index_tag_vector, nearest_tags


@pytest.fixture
def conn(tmp_path):
    with open_user_db("canon-test", data_dir=tmp_path) as c:
        yield c


def _seed_tag(conn, name, description, embedder):
    """Insert an existing tag + its description embedding (as canonicalize would)."""
    conn.execute(
        "INSERT INTO tags (name, description, count) VALUES (?, ?, 1)", (name, description)
    )
    index_tag_vector(conn, name, embedder.embed(description))
    conn.commit()


def test_nearest_tags_returns_conceptually_close(conn):
    embedder = FakeEmbedder()
    _seed_tag(conn, "python", "Python programming language scripting backend", embedder)
    _seed_tag(conn, "cooking", "Recipes food kitchen meals cuisine", embedder)

    query = embedder.embed("Python programming language tutorial backend")
    nearest = nearest_tags(conn, query, limit=2)

    assert nearest[0][0] == "python"  # closest existing tag
    assert nearest[0][1] > nearest[1][1]  # python more similar than cooking


def test_nearest_tags_skips_null_distance_zero_vector(conn):
    """A zero-magnitude query (empty basis) yields NULL cosine distance in sqlite-vec.

    The KNN must treat that as no match and return [] rather than crashing on ``1 - None``,
    so an empty-basis entry routes through the worker's blank-note failure path (spec §7.4)
    with an actionable message instead of a cryptic TypeError.
    """
    embedder = FakeEmbedder()
    _seed_tag(conn, "rust", "Systems programming language memory safety", embedder)

    zero_vector = embedder.embed("")  # no tokens -> all-zero vector
    assert nearest_tags(conn, zero_vector, limit=5) == []


def test_candidate_snaps_to_existing_when_above_threshold(conn):
    embedder = FakeEmbedder()
    _seed_tag(conn, "python", "Python programming language scripting backend", embedder)

    # An identical description embeds to cosine 1.0 -> must snap (reuse), not duplicate.
    cand = TagCandidate(name="python3", description="Python programming language scripting backend")
    final = canonicalize_candidates(
        conn, [cand], embedder=embedder, threshold=0.90, max_tags=5
    )

    assert final == ["python"]
    # No new tag created.
    assert conn.execute("SELECT count(*) FROM tags").fetchone()[0] == 1


def test_genuinely_new_candidate_creates_tag_and_embeds_description(conn):
    embedder = FakeEmbedder()
    _seed_tag(conn, "python", "Python programming language scripting backend", embedder)

    cand = TagCandidate(name="gardening", description="Growing plants flowers vegetables soil outdoors")
    final = canonicalize_candidates(
        conn, [cand], embedder=embedder, threshold=0.90, max_tags=5
    )

    assert final == ["gardening"]
    row = conn.execute("SELECT description FROM tags WHERE name = 'gardening'").fetchone()
    assert row["description"] == "Growing plants flowers vegetables soil outdoors"
    # Its DESCRIPTION embedding is now in tags_vec (findable as nearest to itself).
    nearest = nearest_tags(conn, embedder.embed(cand.description), limit=1)
    assert nearest[0][0] == "gardening"


def test_reuse_over_invention_bias(conn):
    """Given a near-existing tag, no new tag is created (spec §13 criterion 4)."""
    embedder = FakeEmbedder()
    _seed_tag(conn, "rust", "Rust programming language systems async cli", embedder)

    cand = TagCandidate(name="rustlang", description="Rust programming language systems async cli")
    canonicalize_candidates(conn, [cand], embedder=embedder, threshold=0.90, max_tags=5)

    assert conn.execute("SELECT count(*) FROM tags").fetchone()[0] == 1  # no invention


def test_cap_enforced(conn):
    embedder = FakeEmbedder()
    cands = [TagCandidate(name=f"topic-{i}", description=f"unique concept number {i}") for i in range(8)]
    final = canonicalize_candidates(
        conn, cands, embedder=embedder, threshold=0.90, max_tags=3
    )
    assert len(final) == 3


def test_exact_name_reuse_no_new_vector(conn):
    embedder = FakeEmbedder()
    _seed_tag(conn, "flask", "Flask python web micro framework", embedder)

    # A candidate whose normalized name equals an existing tag reuses it directly,
    # regardless of (a possibly different) description — description stays stable (§9.3).
    cand = TagCandidate(name="Flask", description="something totally different")
    final = canonicalize_candidates(conn, [cand], embedder=embedder, threshold=0.90, max_tags=5)

    assert final == ["flask"]
    desc = conn.execute("SELECT description FROM tags WHERE name = 'flask'").fetchone()["description"]
    assert desc == "Flask python web micro framework"  # not regenerated on reuse
