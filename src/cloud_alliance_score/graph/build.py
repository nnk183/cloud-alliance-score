"""Compose the scoring graph and its runtime dependencies.

`ScoringDependencies` holds the concrete search + LLM + cache implementations
and the prompt-rendering glue. `build_scoring_graph` wires the supervisor
fan-out, the generic sub-agent, and the aggregator into a compiled LangGraph.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import Runnable
from langgraph.graph import END, START, StateGraph

from ..config import Settings, get_settings
from ..dimensions import get_spec
from ..schemas import Dimension, DimensionAssessment, DimensionScore, Evidence
from ..tools.cache import DimensionCache
from .nodes import fan_out, make_aggregate_node, make_score_dimension_node
from .state import ScoringState

logger = logging.getLogger(__name__)


def _render_evidence(evidence: List[Evidence]) -> str:
    """Format gathered evidence into a compact, citable block for the LLM."""
    if not evidence:
        return "(No web evidence was found for this dimension.)"
    lines = []
    for i, ev in enumerate(evidence, start=1):
        lines.append(f"[{i}] {ev.title}\n    {ev.url}\n    {ev.snippet}")
    return "\n".join(lines)


# Type alias: a function that turns a dimension's queries into evidence.
GatherFn = Callable[[List[str]], List[Evidence]]


@dataclass
class ScoringDependencies:
    """Runtime capabilities for the graph nodes.

    Defaults are built from `Settings`, but every field is injectable so tests
    (and alternate backends) can supply fakes without touching the network.
    """

    assessment_llm: Runnable          # returns a validated DimensionAssessment
    summary_llm: Runnable             # plain chat model for the closing summary
    gather_fn: GatherFn               # (queries) -> list[Evidence]
    cache: Optional[DimensionCache] = None
    model_name: str = ""

    # --- evidence ------------------------------------------------------------

    def gather_evidence(self, company: str, dimension: Dimension) -> List[Evidence]:
        queries = get_spec(dimension).queries(company)
        return self.gather_fn(queries)

    # --- assessment ----------------------------------------------------------

    def assess(
        self, dimension: Dimension, company: str, evidence: List[Evidence]
    ) -> DimensionAssessment:
        spec = get_spec(dimension)
        human = (
            f"Company under evaluation: {company}\n\n"
            f"Evidence gathered for the '{dimension.label}' dimension:\n"
            f"{_render_evidence(evidence)}\n\n"
            f"Score {company} on {dimension.label} per the rubric, and give "
            f"exactly two sentences of reasoning."
        )
        messages = [SystemMessage(spec.system_prompt()), HumanMessage(human)]
        result = self.assessment_llm.invoke(messages)
        if isinstance(result, DimensionAssessment):
            return result
        return DimensionAssessment(**result)  # tolerate dict-returning backends

    # --- cache ---------------------------------------------------------------

    def load_cached_score(
        self, company: str, dimension: Dimension
    ) -> Optional[DimensionScore]:
        if self.cache is None:
            return None
        payload = self.cache.get(company, dimension)
        if payload is None:
            return None
        try:
            return DimensionScore.model_validate(payload)
        except Exception as exc:  # noqa: BLE001 — stale/incompatible cache entry
            logger.warning("ignoring unusable cached score for %s/%s: %s",
                           company, dimension.value, exc)
            return None

    def store_cached_score(
        self, company: str, dimension: Dimension, score: DimensionScore
    ) -> None:
        if self.cache is None:
            return
        self.cache.set(company, dimension, score.model_dump(mode="json"))

    # --- summary -------------------------------------------------------------

    def summarize(self, company: str, scores: List[DimensionScore]) -> str:
        ordered = sorted(scores, key=lambda s: list(Dimension).index(s.dimension))
        total = sum(s.score for s in ordered)
        breakdown = "\n".join(
            f"- {s.dimension.label}: {s.score}/5 — {s.reasoning}" for s in ordered
        )
        prompt = (
            "You are summarizing a cloud-alliance account scorecard for a "
            "LangChain × GCP partnership team.\n\n"
            f"Company: {company}\nComposite: {total}/25\n\n"
            f"Dimension breakdown:\n{breakdown}\n\n"
            "Write a concise one-paragraph (2-4 sentence) synthesis of this "
            "account's alliance fit, noting the strongest and weakest signals "
            "and an overall recommendation. Output only the paragraph."
        )
        try:
            resp = self.summary_llm.invoke([HumanMessage(prompt)])
            text = getattr(resp, "content", resp)
            return text.strip() if isinstance(text, str) else str(text).strip()
        except Exception as exc:  # noqa: BLE001 — summary is non-critical
            logger.warning("summary generation failed: %s", exc)
            return ""

    # --- default construction ------------------------------------------------

    @classmethod
    def from_settings(cls, settings: Optional[Settings] = None) -> "ScoringDependencies":
        settings = settings or get_settings()
        from ..llm import get_assessment_llm, get_chat_model
        from ..tools.search import SearchClient

        search = SearchClient(settings=settings)
        return cls(
            assessment_llm=get_assessment_llm(settings),
            summary_llm=get_chat_model(settings),
            gather_fn=search.gather,
            cache=DimensionCache.from_settings(settings),
            model_name=settings.model,
        )


def build_scoring_graph(
    deps: Optional[ScoringDependencies] = None,
    settings: Optional[Settings] = None,
):
    """Build and compile the scoring graph.

    Topology:
        START ──(fan_out: Send×5)──▶ score_dimension ──▶ aggregate ──▶ END

    The five `score_dimension` branches run concurrently; `aggregate` runs once,
    after all branches converge, because every branch edges into it and the
    additive reducer has merged their scores.
    """
    deps = deps or ScoringDependencies.from_settings(settings)

    graph = StateGraph(ScoringState)
    graph.add_node("score_dimension", make_score_dimension_node(deps))  # type: ignore[call-overload]
    graph.add_node("aggregate", make_aggregate_node(deps))  # type: ignore[call-overload]

    graph.add_conditional_edges(START, fan_out, ["score_dimension"])
    graph.add_edge("score_dimension", "aggregate")
    graph.add_edge("aggregate", END)

    return graph.compile()


__all__ = ["ScoringDependencies", "build_scoring_graph"]
