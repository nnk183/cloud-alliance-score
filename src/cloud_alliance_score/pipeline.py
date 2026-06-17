"""Public entry point: score a company end-to-end.

`score_company()` is the one function the API, CLI, and UI all call. It wires
LangSmith tracing, builds (or reuses) the compiled graph, runs it, and returns
a validated `Scorecard`.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from .config import Settings, configure_langsmith, get_settings
from .discovery.runtime import DiscoveryDependencies, run_discovery
from .discovery.schemas import DiscoveryResponse
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


def discover_candidates(
    vendor_pair: str,
    n_candidates: int = 10,
    settings: Optional[Settings] = None,
    deps: Optional[DiscoveryDependencies] = None,
) -> DiscoveryResponse:
    """Discover and rank candidate accounts for a vendor pair.

    Generates company candidates, validates they are real, scores them with the
    existing engine (on the cheaper Discovery model), and returns the top N
    ranked. `n_candidates` is clamped to `discovery_max_candidates` to bound
    public-demo cost.

    Args:
        vendor_pair: e.g. "LangChain × GCP".
        n_candidates: how many top-ranked candidates to return.
        settings: optional override; defaults to process settings.
        deps: optional injected dependencies (tests); defaults from settings.
    """
    vendor_pair = (vendor_pair or "").strip()
    if not vendor_pair:
        raise ValueError("vendor_pair must not be empty")

    settings = settings or get_settings()
    configure_langsmith(settings)

    n = max(1, min(n_candidates, settings.discovery_max_candidates))
    deps = deps or DiscoveryDependencies.from_settings(settings)
    return run_discovery(vendor_pair, n, deps)


__all__ = ["score_company", "discover_candidates"]
