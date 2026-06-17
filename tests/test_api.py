"""FastAPI endpoint behavior (with the scorer stubbed out)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from cloud_alliance_score import api
from cloud_alliance_score import pipeline
from cloud_alliance_score.config import Settings
from cloud_alliance_score.schemas import Dimension, DimensionScore, ScoringResponse


@pytest.fixture
def client():
    return TestClient(api.app)


def _fake_response(company: str, context=None) -> ScoringResponse:
    scores = [
        DimensionScore(dimension=d, score=s, reasoning="a. b.")
        for d, s in zip(Dimension, [5, 5, 4, 4, 3])
    ]
    return ScoringResponse.build(
        company, scores, summary="fit summary", model_used="test-model",
        optional_context=context,
    )


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert set(body["keys_configured"]) == {"anthropic", "tavily", "langsmith"}
    assert "demo_mode" in body


def test_score_happy_path(client, monkeypatch):
    # /score does a lazy `from .pipeline import score_company`, so patch there.
    monkeypatch.setattr(
        pipeline, "score_company",
        lambda company, optional_context=None: _fake_response(company, optional_context),
    )
    resp = client.post("/score", json={"company_name": "Stripe", "optional_context": "payments"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["company_name"] == "Stripe"
    assert body["composite"]["total_score"] == 21
    assert body["composite"]["tier"] == "Tier 1"
    assert body["optional_context"] == "payments"
    assert len(body["composite"]["dimension_scores"]) == 5


def test_score_validation_error(client):
    resp = client.post("/score", json={"company_name": "   "})
    assert resp.status_code == 422


def test_score_missing_keys_returns_503(client, monkeypatch):
    def _boom(company, optional_context=None):
        raise RuntimeError("ANTHROPIC_API_KEY is not set.")

    monkeypatch.setattr(pipeline, "score_company", _boom)
    resp = client.post("/score", json={"company_name": "Stripe"})
    assert resp.status_code == 503
    assert "ANTHROPIC_API_KEY" in resp.json()["detail"]


def test_score_unexpected_error_returns_500(client, monkeypatch):
    def _boom(company, optional_context=None):
        raise ValueError("kaboom")

    monkeypatch.setattr(pipeline, "score_company", _boom)
    resp = client.post("/score", json={"company_name": "Stripe"})
    assert resp.status_code == 500


# --- demo gallery + rate limiting ------------------------------------------


def test_demo_companies_lists_fixtures(client):
    resp = client.get("/demo/companies")
    assert resp.status_code == 200
    slugs = {c["slug"] for c in resp.json()}
    assert {"stripe", "capital-one", "sephora"} <= slugs


def test_demo_scorecard_roundtrip(client):
    resp = client.get("/demo/scorecard/stripe")
    assert resp.status_code == 200
    body = resp.json()
    assert body["company_name"] == "Stripe"
    assert 0 <= body["composite"]["total_score"] <= 25


def test_demo_scorecard_unknown_404(client):
    assert client.get("/demo/scorecard/does-not-exist").status_code == 404


def test_score_rate_limited_returns_429(client, monkeypatch):
    # Force demo mode on and an exhausted limiter.
    monkeypatch.setattr(api, "get_settings", lambda: Settings(_env_file=None, CAS_DEMO_MODE=True))

    class _Exhausted:
        cap = 0
        def consume(self):
            return False

    monkeypatch.setattr(api, "get_rate_limiter", lambda settings: _Exhausted())
    resp = client.post("/score", json={"company_name": "Stripe"})
    assert resp.status_code == 429
    assert "limit" in resp.json()["detail"].lower()
