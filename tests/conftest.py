"""Shared pytest fixtures and fakes.

Everything here lets the full graph/pipeline run deterministically with no
network calls and no API keys — the LLM and Tavily are replaced by fakes.
"""

from __future__ import annotations

from typing import Dict, List

import pytest

from cloud_alliance_score.config import Settings
from cloud_alliance_score.graph.build import ScoringDependencies
from cloud_alliance_score.schemas import Dimension, DimensionAssessment, Evidence
from cloud_alliance_score.tools.cache import DimensionCache


class FakeAssessmentLLM:
    """Returns a deterministic DimensionAssessment based on the dimension.

    The dimension is inferred from the system prompt's label so each dimension
    can be given a distinct score, exercising composite/tier logic.
    """

    def __init__(self, scores: Dict[Dimension, int]):
        self.scores = scores
        self.calls = 0

    def invoke(self, messages):
        self.calls += 1
        system = messages[0].content
        score = 3
        for dim, val in self.scores.items():
            if dim.label in system:
                score = val
                break
        return DimensionAssessment(
            score=score, reasoning="Deterministic test reasoning. Second sentence."
        )


class FakeSummaryLLM:
    def __init__(self, text: str = "Test summary paragraph."):
        self.text = text
        self.calls = 0

    def invoke(self, messages):
        self.calls += 1

        class _Resp:
            content = self.text

        return _Resp()


class CountingGather:
    """Fake evidence gatherer that records how many times it ran."""

    def __init__(self):
        self.calls = 0

    def __call__(self, queries: List[str]) -> List[Evidence]:
        self.calls += 1
        return [
            Evidence(
                title="Source",
                url="https://example.com/" + queries[0].replace(" ", "_"),
                snippet="evidence snippet for " + queries[0],
            )
        ]


@pytest.fixture
def fake_scores() -> Dict[Dimension, int]:
    # GCP 5, AI 5, Industry 4, LangChain 3, Strategic 3 -> 20 -> Tier 1
    return {
        Dimension.GCP_COMMIT: 5,
        Dimension.AI_MATURITY: 5,
        Dimension.INDUSTRY_FIT: 4,
        Dimension.LANGCHAIN_FOOTPRINT: 3,
        Dimension.STRATEGIC_SIGNALS: 3,
    }


@pytest.fixture
def fake_deps(fake_scores, tmp_path):
    """ScoringDependencies wired entirely with fakes + a temp-dir cache."""
    cache = DimensionCache(
        cache_dir=str(tmp_path / "cache"), ttl_seconds=999, enabled=True, model="test-model"
    )
    return ScoringDependencies(
        assessment_llm=FakeAssessmentLLM(fake_scores),
        summary_llm=FakeSummaryLLM(),
        gather_fn=CountingGather(),
        cache=cache,
        model_name="test-model",
    )


@pytest.fixture
def no_env_settings() -> Settings:
    """Settings that ignore any ambient .env / environment file."""
    return Settings(_env_file=None)
