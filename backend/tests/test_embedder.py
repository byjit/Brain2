"""Tests for the embedder provider (spec §7.1 step 8, §11 vector half).

All offline: ``FakeEmbedder`` is deterministic AND similarity-meaningful (token-overlap
bag-of-words, unit-normalized) so KNN ordering and RRF are genuinely testable without a
live Gemini key. We assert dimensionality, determinism, unit-length, and that overlapping
text embeds closer (higher cosine) than unrelated text.
"""

import math

from brain2.services.providers.embedder import FakeEmbedder, l2_normalize

_DIM = 768


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def test_dimension_is_768():
    e = FakeEmbedder()
    assert e.dimension == _DIM
    assert len(e.embed("hello world")) == _DIM


def test_deterministic():
    e = FakeEmbedder()
    assert e.embed("rust async http") == e.embed("rust async http")


def test_unit_length():
    e = FakeEmbedder()
    vec = e.embed("kubernetes deployment guide")
    norm = math.sqrt(_dot(vec, vec))
    assert math.isclose(norm, 1.0, abs_tol=1e-6)


def test_overlapping_text_is_closer_than_unrelated():
    e = FakeEmbedder()
    query = e.embed("rust http library")
    overlapping = e.embed("a fast http client written in rust")
    unrelated = e.embed("french cooking recipes for dinner")
    # Cosine == dot (unit vectors). Token overlap must score strictly higher.
    assert _dot(query, overlapping) > _dot(query, unrelated)


def test_empty_text_is_zero_vector():
    # No tokens -> a well-defined zero vector (not NaN from a divide-by-zero norm).
    e = FakeEmbedder()
    vec = e.embed("   ")
    assert vec == [0.0] * _DIM


# --- l2_normalize: the unit that fixes GeminiEmbedder's un-normalized reduced-dim
#     vectors so L2 KNN is monotonic with cosine (matches the production embed path). --


def test_l2_normalize_returns_unit_vector():
    vec = l2_normalize([3.0, 0.0, 4.0])  # norm 5
    assert math.isclose(math.sqrt(_dot(vec, vec)), 1.0, abs_tol=1e-9)
    assert vec == [0.6, 0.0, 0.8]


def test_l2_normalize_preserves_direction_regardless_of_magnitude():
    # Same-direction vectors of different magnitude normalize to the SAME unit vector,
    # so an L2 KNN over normalized vectors ranks by direction (cosine), not magnitude.
    small = l2_normalize([1.0, 0.0, 0.0])
    large = l2_normalize([10.0, 0.0, 0.0])
    assert small == large == [1.0, 0.0, 0.0]


def test_l2_normalize_zero_vector_is_not_nan():
    # A zero vector has no direction; normalizing must not divide by zero / produce NaN.
    assert l2_normalize([0.0, 0.0, 0.0]) == [0.0, 0.0, 0.0]
