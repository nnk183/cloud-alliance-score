"""Schema validation and the public contract."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from cloud_alliance_score.schemas import (
    CompositeScore,
    Dimension,
    DimensionAssessment,
    DimensionScore,
    Evidence,
    ScoringRequest,
    ScoringResponse,
    Tier,
)


def _all_scores(values):
    return [
        DimensionScore(dimension=d, score=s, reasoning="One. Two.")
        for d, s in zip(Dimension, values)
    ]


def test_dimension_score_bounds():
    with pytest.raises(ValidationError):
        DimensionScore(dimension=Dimension.GCP_COMMIT, score=6, reasoning="x")
    with pytest.raises(ValidationError):
        DimensionScore(dimension=Dimension.GCP_COMMIT, score=0, reasoning="x")


def test_dimension_name_is_serialized():
    ds = DimensionScore(dimension=Dimension.LANGCHAIN_FOOTPRINT, score=4, reasoning="a. b.")
    dumped = ds.model_dump()
    assert dumped["dimension_name"] == "LangChain Footprint"


def test_evidence_requires_content():
    with pytest.raises(ValidationError):
        Evidence(title="", url="https://x.com", snippet="s")
    with pytest.raises(ValidationError):
        Evidence(title="t", url="https://x.com", snippet="   ")


def test_assessment_reasoning_non_empty():
    with pytest.raises(ValidationError):
        DimensionAssessment(score=3, reasoning="   ")


def test_composite_build_derives_total_and_tier():
    comp = CompositeScore.build(_all_scores([5, 5, 4, 4, 3]))  # 21
    assert comp.total_score == 21
    assert comp.tier == Tier.TIER_1
    assert comp.tier_number == 1
    # dimension_scores returned in canonical order
    assert [d.dimension for d in comp.dimension_scores] == list(Dimension)


def test_composite_rejects_missing_dimension():
    partial = _all_scores([5, 5, 4, 4])[:4]  # only 4 dimensions
    with pytest.raises(ValidationError):
        CompositeScore(total_score=18, tier=Tier.TIER_2, dimension_scores=partial)


def test_composite_rejects_total_mismatch():
    with pytest.raises(ValidationError):
        CompositeScore(
            total_score=99, tier=Tier.TIER_1, dimension_scores=_all_scores([5, 5, 4, 4, 3])
        )


def test_composite_rejects_wrong_tier():
    with pytest.raises(ValidationError):
        CompositeScore(
            total_score=21, tier=Tier.TIER_3, dimension_scores=_all_scores([5, 5, 4, 4, 3])
        )


def test_scoring_request_trims_and_requires_name():
    req = ScoringRequest(company_name="  Stripe  ")
    assert req.company_name == "Stripe"
    with pytest.raises(ValidationError):
        ScoringRequest(company_name="   ")


def test_scoring_response_build_roundtrips_json():
    resp = ScoringResponse.build(
        "Stripe", _all_scores([5, 5, 4, 4, 3]), summary="ok", model_used="claude"
    )
    data = resp.model_dump(mode="json")
    assert data["composite"]["total_score"] == 21
    assert data["composite"]["tier"] == "Tier 1"
    assert "evidence" in data["composite"]["dimension_scores"][0]
    # Re-validate to confirm the serialized form is itself valid.
    ScoringResponse.model_validate(data)
