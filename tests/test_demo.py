"""Demo gallery loading and rate-limiter selection/behavior."""

from __future__ import annotations

from cloud_alliance_score.config import Settings
from cloud_alliance_score.demo import (
    DailyRateLimiter,
    get_rate_limiter,
    list_demo_companies,
    load_demo_scorecard,
)


def test_gallery_lists_committed_fixtures():
    names = {n for n, _ in list_demo_companies()}
    assert {"Stripe", "Capital One", "Sephora"} <= names


def test_load_demo_scorecard_valid():
    resp = load_demo_scorecard("capital-one")
    assert resp is not None
    assert resp.company_name == "Capital One"
    assert len(resp.composite.dimension_scores) == 5


def test_load_demo_scorecard_missing_returns_none():
    assert load_demo_scorecard("nope") is None


def test_daily_limiter_caps_and_resets(tmp_path):
    lim = DailyRateLimiter(cap=2, state_path=tmp_path / "u.json")
    assert lim.remaining() == 2
    assert lim.consume() is True
    assert lim.consume() is True
    assert lim.consume() is False  # cap hit
    assert lim.remaining() == 0
    assert lim.allow() is False


def test_get_rate_limiter_falls_back_to_file(monkeypatch, tmp_path):
    # No Upstash env vars -> file-based limiter.
    monkeypatch.delenv("UPSTASH_REDIS_REST_URL", raising=False)
    monkeypatch.delenv("UPSTASH_REDIS_REST_TOKEN", raising=False)
    settings = Settings(_env_file=None, CAS_CACHE_DIR=str(tmp_path), CAS_DEMO_DAILY_CAP=5)
    lim = get_rate_limiter(settings)
    assert isinstance(lim, DailyRateLimiter)
    assert lim.cap == 5
