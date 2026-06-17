"""Disk cache: hit/miss, TTL, keying, and disabled behavior."""

from __future__ import annotations

from cloud_alliance_score.schemas import Dimension, DimensionScore, Evidence
from cloud_alliance_score.tools.cache import DimensionCache


def _payload(score: int = 5) -> dict:
    return DimensionScore(
        dimension=Dimension.GCP_COMMIT,
        score=score,
        reasoning="a. b.",
        evidence=[Evidence(title="t", url="https://x.com", snippet="s")],
    ).model_dump(mode="json")


def test_miss_then_set_then_hit(tmp_path):
    cache = DimensionCache(str(tmp_path), ttl_seconds=999, enabled=True, model="m1")
    assert cache.get("Stripe", Dimension.GCP_COMMIT) is None
    cache.set("Stripe", Dimension.GCP_COMMIT, _payload(5))
    got = cache.get("Stripe", Dimension.GCP_COMMIT)
    assert got is not None and got["score"] == 5


def test_keyed_on_model(tmp_path):
    c1 = DimensionCache(str(tmp_path), ttl_seconds=999, enabled=True, model="m1")
    c2 = DimensionCache(str(tmp_path), ttl_seconds=999, enabled=True, model="m2")
    c1.set("Stripe", Dimension.GCP_COMMIT, _payload())
    assert c2.get("Stripe", Dimension.GCP_COMMIT) is None  # different model -> miss


def test_keyed_on_company_is_case_insensitive(tmp_path):
    cache = DimensionCache(str(tmp_path), ttl_seconds=999, enabled=True, model="m1")
    cache.set("Stripe", Dimension.GCP_COMMIT, _payload(4))
    assert cache.get("  stripe ", Dimension.GCP_COMMIT)["score"] == 4


def test_ttl_expiry_evicts(tmp_path):
    cache = DimensionCache(str(tmp_path), ttl_seconds=0, enabled=True, model="m1")
    cache.set("Stripe", Dimension.GCP_COMMIT, _payload())
    assert cache.get("Stripe", Dimension.GCP_COMMIT) is None  # immediately expired


def test_disabled_is_noop(tmp_path):
    cache = DimensionCache(str(tmp_path), ttl_seconds=999, enabled=False, model="m1")
    cache.set("Stripe", Dimension.GCP_COMMIT, _payload())
    assert cache.get("Stripe", Dimension.GCP_COMMIT) is None


def test_corrupt_file_is_ignored(tmp_path):
    cache = DimensionCache(str(tmp_path), ttl_seconds=999, enabled=True, model="m1")
    cache.set("Stripe", Dimension.GCP_COMMIT, _payload())
    # Corrupt the on-disk entry.
    path = cache._path("Stripe", Dimension.GCP_COMMIT)
    path.write_text("{ not json", encoding="utf-8")
    assert cache.get("Stripe", Dimension.GCP_COMMIT) is None  # degrades, no raise


def test_clear_removes_entries(tmp_path):
    cache = DimensionCache(str(tmp_path), ttl_seconds=999, enabled=True, model="m1")
    cache.set("A", Dimension.GCP_COMMIT, _payload())
    cache.set("B", Dimension.AI_MATURITY, _payload())
    assert cache.clear() == 2
    assert cache.get("A", Dimension.GCP_COMMIT) is None
