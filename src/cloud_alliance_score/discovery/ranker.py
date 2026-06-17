"""Ranker: sort scored candidates by composite score and take the top N."""

from __future__ import annotations

from typing import List

from ..schemas import ScoringResponse
from .schemas import ScoredCandidate


def rank_candidates(scorecards: List[ScoringResponse], n: int) -> List[ScoredCandidate]:
    """Rank by composite score (desc), tie-broken by company name; return top N.

    Returns `ScoredCandidate`s with 1-based ranks.
    """
    ordered = sorted(
        scorecards,
        key=lambda r: (-r.composite.total_score, r.company_name.lower()),
    )
    top = ordered[: max(0, n)]
    return [ScoredCandidate(rank=i + 1, scorecard=sc) for i, sc in enumerate(top)]


__all__ = ["rank_candidates"]
