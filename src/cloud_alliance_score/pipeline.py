"""Public entry point: score a company end-to-end.

`score_company()` is the one function the API, CLI, and UI all call. It wires
LangSmith tracing, builds (or reuses) the compiled graph, runs it, and returns
a validated `Scorecard`.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from .config import Settings, configure_langsmith, get_settings
from .graph.build import ScoringDependencies, build_scoring_graph
from .schemas import ScoringResponse


@lru_cache(maxsize=1)
def _default_graph():
    """Build the default graph once (LLM + Tavily + cache from Settings)."""
    return build_scoring_graph()


def score_company(
    company: str,
    optional_context: Optional[str] = None,
    settings: Optional[Settings] = None,
    deps: Optional[ScoringDependencies] = None,
) -> ScoringResponse:
    """Score a single company and return its `ScoringResponse`.

    Args:
        company: Company name to evaluate.
        optional_context: Optional hint to disambiguate the company.
        settings: Optional override; defaults to process settings.
        deps: Optional injected dependencies (used in tests). When provided, a
            fresh graph is built around them instead of the cached default.
    """
    company = (company or "").strip()
    if not company:
        raise ValueError("company name must not be empty")

    settings = settings or get_settings()
    configure_langsmith(settings)

    graph = build_scoring_graph(deps=deps, settings=settings) if deps else _default_graph()

    # `run_name`/tags surface nicely in LangSmith traces.
    result = graph.invoke(
        {"company": company, "optional_context": optional_context},
        config={"run_name": f"score:{company}", "tags": ["cloud-alliance-score"]},
    )
    return result["response"]


__all__ = ["score_company"]
