"""End-to-end graph / pipeline behavior with fakes."""

from __future__ import annotations

from cloud_alliance_score.graph.build import build_scoring_graph
from cloud_alliance_score.pipeline import score_company
from cloud_alliance_score.schemas import Dimension, ScoringResponse, Tier


def test_graph_scores_all_dimensions(fake_deps):
    app = build_scoring_graph(deps=fake_deps)
    result = app.invoke({"company": "Stripe", "optional_context": None})
    resp = result["response"]
    assert isinstance(resp, ScoringResponse)
    # fake_scores: 5+5+4+3+3 = 20 -> Tier 1
    assert resp.composite.total_score == 20
    assert resp.composite.tier == Tier.TIER_1
    assert len(resp.composite.dimension_scores) == len(Dimension)
    # every dimension scored exactly once, in canonical order
    assert [d.dimension for d in resp.composite.dimension_scores] == list(Dimension)


def test_pipeline_passes_context_and_model(fake_deps):
    resp = score_company("Capital One", optional_context="US bank", deps=fake_deps)
    assert resp.company_name == "Capital One"
    assert resp.optional_context == "US bank"
    assert resp.model_used == "test-model"
    assert resp.summary  # summary populated by fake summary LLM


def test_every_dimension_carries_evidence(fake_deps):
    resp = score_company("Sephora", deps=fake_deps)
    for ds in resp.composite.dimension_scores:
        assert ds.evidence, f"{ds.dimension} has no evidence trail"


def test_cache_prevents_recompute(fake_deps):
    gather = fake_deps.gather_fn   # CountingGather
    assess = fake_deps.assessment_llm  # FakeAssessmentLLM

    score_company("Stripe", deps=fake_deps)
    assert gather.calls == len(Dimension)   # one search batch per dimension
    assert assess.calls == len(Dimension)

    # Second run for the same company should be fully served from cache.
    score_company("Stripe", deps=fake_deps)
    assert gather.calls == len(Dimension)   # unchanged
    assert assess.calls == len(Dimension)   # unchanged


def test_empty_company_rejected(fake_deps):
    import pytest

    with pytest.raises(ValueError):
        score_company("   ", deps=fake_deps)
