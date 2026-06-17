"""Composite aggregation and tier classification boundaries."""

from __future__ import annotations

import pytest

from cloud_alliance_score.schemas import CompositeScore, Dimension, DimensionScore, Tier


@pytest.mark.parametrize(
    "total,expected",
    [
        (25, Tier.TIER_1),
        (20, Tier.TIER_1),  # lower edge of Tier 1
        (19, Tier.TIER_2),  # upper edge of Tier 2
        (12, Tier.TIER_2),  # lower edge of Tier 2
        (11, Tier.TIER_3),  # upper edge of Tier 3
        (5, Tier.TIER_3),
        (0, Tier.TIER_3),
    ],
)
def test_tier_from_score_boundaries(total, expected):
    assert Tier.from_score(total) == expected


def test_tier_number_mapping():
    assert Tier.TIER_1.number == 1
    assert Tier.TIER_2.number == 2
    assert Tier.TIER_3.number == 3


@pytest.mark.parametrize(
    "values,total,tier",
    [
        ([5, 5, 5, 5, 5], 25, Tier.TIER_1),
        ([4, 4, 4, 4, 4], 20, Tier.TIER_1),
        ([3, 3, 3, 3, 3], 15, Tier.TIER_2),
        ([2, 2, 2, 3, 3], 12, Tier.TIER_2),
        ([2, 2, 2, 2, 3], 11, Tier.TIER_3),
        ([1, 1, 1, 1, 1], 5, Tier.TIER_3),
    ],
)
def test_composite_build_totals_and_tiers(values, total, tier):
    scores = [
        DimensionScore(dimension=d, score=s, reasoning="a. b.")
        for d, s in zip(Dimension, values)
    ]
    comp = CompositeScore.build(scores)
    assert comp.total_score == total
    assert comp.tier == tier


def test_build_is_order_independent():
    forward = [
        DimensionScore(dimension=d, score=s, reasoning="a. b.")
        for d, s in zip(Dimension, [5, 4, 3, 2, 1])
    ]
    comp_a = CompositeScore.build(forward)
    comp_b = CompositeScore.build(list(reversed(forward)))
    assert comp_a.total_score == comp_b.total_score == 15
    assert [d.dimension for d in comp_b.dimension_scores] == list(Dimension)
