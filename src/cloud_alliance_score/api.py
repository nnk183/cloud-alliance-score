"""FastAPI application exposing the scorer over HTTP.

Endpoints:
    GET  /health                  -> liveness + which API keys are configured
    POST /score                   -> score a company (ScoringRequest -> ScoringResponse)
    GET  /demo/companies          -> curated gallery list (pre-computed, free)
    GET  /demo/scorecard/{slug}   -> a pre-computed scorecard (free, no API calls)

The heavy scoring pipeline is imported lazily inside /score, so importing this
module (and serving the homepage / gallery) stays cheap and cold-start-friendly.
"""

from __future__ import annotations

import logging
from typing import List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .config import get_settings
from .demo import get_rate_limiter, list_demo_companies, load_demo_scorecard
from .discovery.schemas import DiscoveryRequest, DiscoveryResponse
from .schemas import ScoringRequest, ScoringResponse

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Cloud Alliance Score",
    version=__version__,
    description=(
        "Score companies as potential cloud alliance accounts for a "
        "LangChain × GCP partnership across five dimensions."
    ),
)

# Allow the static frontend (same origin on Vercel, localhost in dev) to call us.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    """Liveness probe + configuration sanity (without leaking key values)."""
    settings = get_settings()
    return {
        "status": "ok",
        "version": __version__,
        "model": settings.model,
        "keys_configured": {
            "anthropic": bool(settings.anthropic_api_key),
            "tavily": bool(settings.tavily_api_key),
            "langsmith": bool(settings.langsmith_api_key),
        },
        "langsmith_tracing": settings.langsmith_tracing and bool(settings.langsmith_api_key),
        "cache_enabled": settings.cache_enabled,
        "demo_mode": settings.demo_mode,
    }


@app.get("/demo/companies")
def demo_companies() -> List[dict]:
    """List the pre-computed gallery scorecards (free, no API calls)."""
    return [{"company_name": name, "slug": slug} for name, slug in list_demo_companies()]


@app.get("/demo/scorecard/{slug}", response_model=ScoringResponse)
def demo_scorecard(slug: str) -> ScoringResponse:
    """Return a pre-computed scorecard by slug."""
    resp = load_demo_scorecard(slug)
    if resp is None:
        raise HTTPException(status_code=404, detail=f"no demo scorecard for {slug!r}")
    return resp


@app.post("/score", response_model=ScoringResponse)
def score(request: ScoringRequest) -> ScoringResponse:
    """Score a single company and return its full scorecard.

    In demo mode a global daily cap protects the owner's API credits; when the
    cap is exhausted we return 429 so the UI can steer visitors to the gallery.
    """
    settings = get_settings()

    if settings.demo_mode:
        limiter = get_rate_limiter(settings)
        if not limiter.consume():
            raise HTTPException(
                status_code=429,
                detail="Daily demo limit reached. Browse the gallery, or try again tomorrow.",
            )

    # Lazy import keeps cold starts cheap for non-scoring routes.
    from .pipeline import score_company

    try:
        return score_company(
            company=request.company_name,
            optional_context=request.optional_context,
        )
    except RuntimeError as exc:
        # Missing API keys etc. — a configuration problem, not a server fault.
        logger.warning("scoring misconfiguration: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("scoring failed for %r", request.company_name)
        raise HTTPException(status_code=500, detail=f"scoring failed: {exc}") from exc


@app.post("/discover", response_model=DiscoveryResponse)
def discover(request: DiscoveryRequest) -> DiscoveryResponse:
    """Discover and rank candidate accounts for a vendor pair.

    Discovery is far more expensive than a single score (it scores many
    companies), so in demo mode it consumes the daily cap and `n_candidates`
    is clamped to `discovery_max_candidates` by the pipeline.
    """
    settings = get_settings()

    if settings.demo_mode:
        limiter = get_rate_limiter(settings)
        if not limiter.consume():
            raise HTTPException(
                status_code=429,
                detail="Daily demo limit reached. Try a pre-computed example, or come back tomorrow.",
            )

    from .pipeline import discover_candidates

    try:
        return discover_candidates(
            vendor_pair=request.vendor_pair, n_candidates=request.n_candidates
        )
    except RuntimeError as exc:
        logger.warning("discovery misconfiguration: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("discovery failed for %r", request.vendor_pair)
        raise HTTPException(status_code=500, detail=f"discovery failed: {exc}") from exc


__all__ = ["app"]
