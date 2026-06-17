"""Graph nodes: supervisor fan-out, generic scoring sub-agent, aggregator.

The node *logic* lives here as factory functions that close over a dependencies
object (search + LLM + cache). `build.py` wires them into a `StateGraph`.
Injecting deps makes every node unit-testable with fakes — no network or keys.
"""

from __future__ import annotations

from typing import Callable, List, Optional, Protocol

from langgraph.types import Send

from ..schemas import (
    Dimension,
    DimensionAssessment,
    DimensionScore,
    Evidence,
    ScoringResponse,
)
from .state import ScoringState


class Deps(Protocol):
    """The capabilities a node needs, supplied by `ScoringDependencies`."""

    model_name: str

    def gather_evidence(self, company: str, dimension: Dimension) -> List[Evidence]: ...
    def assess(
        self, dimension: Dimension, company: str, evidence: List[Evidence]
    ) -> DimensionAssessment: ...
    def load_cached_score(
        self, company: str, dimension: Dimension
    ) -> Optional[DimensionScore]: ...
    def store_cached_score(
        self, company: str, dimension: Dimension, score: DimensionScore
    ) -> None: ...
    def summarize(self, company: str, scores: List[DimensionScore]) -> str: ...


# ---------------------------------------------------------------------------
# Supervisor: fan out one branch per dimension
# ---------------------------------------------------------------------------


def fan_out(state: ScoringState) -> List[Send]:
    """Route to a `score_dimension` branch for each of the five dimensions.

    Using `Send` lets all five sub-agents run in the same superstep (parallel),
    each receiving its own `dimension` in an isolated state payload.
    """
    company = state["company"]
    return [
        Send("score_dimension", {"company": company, "dimension": dimension})
        for dimension in Dimension
    ]


# ---------------------------------------------------------------------------
# Sub-agent: gather evidence, then score one dimension (cache-aware)
# ---------------------------------------------------------------------------


def make_score_dimension_node(deps: Deps) -> Callable[[ScoringState], dict]:
    def score_dimension(state: ScoringState) -> dict:
        company = state["company"]
        dimension = state["dimension"]
        assert dimension is not None, "fan_out must set `dimension` on each branch"

        # Cache first — a hit spends zero Tavily and zero Anthropic credits.
        cached = deps.load_cached_score(company, dimension)
        if cached is not None:
            return {"dimension_scores": [cached]}

        evidence = deps.gather_evidence(company, dimension)
        assessment = deps.assess(dimension, company, evidence)
        score = DimensionScore.from_assessment(dimension, assessment, evidence)
        deps.store_cached_score(company, dimension, score)

        # The additive reducer on `dimension_scores` merges this into the list.
        return {"dimension_scores": [score]}

    return score_dimension


# ---------------------------------------------------------------------------
# Aggregator: composite + tier + summary, wrapped as a ScoringResponse
# ---------------------------------------------------------------------------


def make_aggregate_node(deps: Deps) -> Callable[[ScoringState], dict]:
    def aggregate(state: ScoringState) -> dict:
        company = state["company"]
        scores = state["dimension_scores"]
        summary = deps.summarize(company, scores)
        # ScoringResponse.build derives the composite (total + tier) and validates
        # that all five dimensions are present.
        response = ScoringResponse.build(
            company_name=company,
            dimension_scores=scores,
            summary=summary,
            model_used=deps.model_name,
            optional_context=state.get("optional_context"),
        )
        return {"response": response}

    return aggregate


__all__ = [
    "Deps",
    "fan_out",
    "make_score_dimension_node",
    "make_aggregate_node",
]
