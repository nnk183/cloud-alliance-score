"""Discovery orchestration: generate → validate → score → rank.

`DiscoveryDependencies` wires the generator, validator, the (reused) scoring
engine, and the cache. `run_discovery` is the pure orchestration over those
capabilities — every dependency is injectable, so the whole flow is testable
offline with fakes.

The scoring step reuses `build_scoring_graph` with Haiku-configured
dependencies; no scoring logic is duplicated.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable, List, Optional

from ..config import Settings, get_settings
from ..schemas import ScoringResponse
from .cache import DiscoveryCache
from .ranker import rank_candidates
from .schemas import Candidate, CandidateIdea, DiscoveryResponse

logger = logging.getLogger(__name__)


@dataclass
class DiscoveryDependencies:
    """Capabilities the Discovery flow needs, all injectable for testing."""

    generate: Callable[[str, int], List[CandidateIdea]]   # (vendor_pair, count) -> ideas
    validate: Callable[[List[CandidateIdea]], List[Candidate]]
    score_one: Callable[[Candidate], ScoringResponse]
    model_name: str
    generate_count: int = 30
    max_score: int = 10
    concurrency: int = 4
    cache: Optional[DiscoveryCache] = None

    @classmethod
    def from_settings(cls, settings: Optional[Settings] = None) -> "DiscoveryDependencies":
        settings = settings or get_settings()
        from ..graph.build import ScoringDependencies, build_scoring_graph
        from ..tools.search import SearchClient
        from .generator import build_generator_llm, generate_candidates
        from .validator import build_confirm_llm, validate_candidates

        search = SearchClient(settings=settings)
        generator_llm = build_generator_llm(settings)
        confirm_llm = build_confirm_llm(settings)

        # Reuse the scoring engine, but on the cheaper Discovery model (Haiku).
        haiku_settings = settings.model_copy(update={"model": settings.discovery_model})
        score_graph = build_scoring_graph(
            deps=ScoringDependencies.from_settings(haiku_settings)
        )

        def _score_one(candidate: Candidate) -> ScoringResponse:
            result = score_graph.invoke(
                {"company": candidate.name, "optional_context": candidate.industry or None}
            )
            return result["response"]

        return cls(
            generate=lambda vp, count: generate_candidates(vp, count, generator_llm).candidates,
            validate=lambda ideas: validate_candidates(
                ideas, search, confirm_llm, settings.discovery_concurrency
            ),
            score_one=_score_one,
            model_name=settings.discovery_model,
            generate_count=settings.discovery_generate_count,
            max_score=settings.discovery_max_score,
            concurrency=settings.discovery_concurrency,
            cache=DiscoveryCache.from_settings(settings),
        )


def run_discovery(
    vendor_pair: str,
    n_candidates: int,
    deps: DiscoveryDependencies,
) -> DiscoveryResponse:
    """Generate, validate, score, and rank candidates for a vendor pair."""
    # Whole-run cache.
    if deps.cache is not None:
        cached = deps.cache.get(vendor_pair, n_candidates)
        if cached is not None:
            logger.info("discovery cache hit for %r (n=%d)", vendor_pair, n_candidates)
            return DiscoveryResponse.model_validate(cached).model_copy(update={"cached": True})

    # 1. Generate candidate ideas.
    ideas = deps.generate(vendor_pair, deps.generate_count)

    # 2. Validate — drop hallucinations.
    validated = [c for c in deps.validate(ideas) if c.validated]

    # 3. Cap how many we actually score (the dominant cost), then score in parallel.
    to_score = validated[: deps.max_score]
    scorecards = _score_all(to_score, deps)

    # 4. Rank and take the top N.
    ranked = rank_candidates(scorecards, n_candidates)

    response = DiscoveryResponse(
        vendor_pair=vendor_pair,
        requested=n_candidates,
        generated=len(ideas),
        validated=len(validated),
        scored=len(scorecards),
        results=ranked,
        model_used=deps.model_name,
    )

    if deps.cache is not None:
        deps.cache.set(vendor_pair, n_candidates, response.model_dump(mode="json"))
    return response


def _score_all(
    candidates: List[Candidate], deps: DiscoveryDependencies
) -> List[ScoringResponse]:
    """Score candidates with bounded concurrency; skip any that fail."""
    if not candidates:
        return []
    workers = max(1, min(deps.concurrency, len(candidates)))

    def _safe(candidate: Candidate) -> Optional[ScoringResponse]:
        try:
            return deps.score_one(candidate)
        except Exception as exc:  # noqa: BLE001 — one bad candidate shouldn't kill the run
            logger.warning("scoring failed for %r: %s", candidate.name, exc)
            return None

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(_safe, candidates))
    return [r for r in results if r is not None]


__all__ = ["DiscoveryDependencies", "run_discovery"]
