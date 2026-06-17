"""Candidate validator: confirm each generated company is real.

For each candidate we run one Tavily search and then a cheap Haiku confirmation
over the snippets. Candidates with no search evidence, or that the model judges
not to be a real operating company, are marked `validated=False` and dropped by
the orchestrator. The confirmation also enriches the candidate (canonical name +
industry).
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import Runnable

from ..config import Settings, get_settings
from ..tools.search import SearchClient
from .schemas import Candidate, CandidateIdea, ExistenceCheck

logger = logging.getLogger(__name__)

CONFIRM_SYSTEM = """\
You verify whether a named entity is a real, currently-operating company, using
web-search snippets. Be strict: if the snippets don't clearly describe a real
company by this name, set exists=false. When it is real, return its canonical
(official) name and primary industry.
"""


def build_confirm_llm(settings: Optional[Settings] = None) -> Runnable:
    """A Discovery-model (Haiku) LLM bound to emit a validated ExistenceCheck."""
    settings = settings or get_settings()
    from ..llm import get_chat_model

    return get_chat_model(settings, model=settings.discovery_model).with_structured_output(
        ExistenceCheck
    )


def validate_one(
    idea: CandidateIdea,
    search: SearchClient,
    confirm_llm: Runnable,
) -> Candidate:
    """Validate a single candidate; never raises (returns validated=False on any issue)."""
    try:
        evidence = search.search_one(f'"{idea.name}" company', max_results=3)
    except Exception as exc:  # noqa: BLE001
        logger.warning("validation search failed for %r: %s", idea.name, exc)
        evidence = []

    if not evidence:
        return Candidate(name=idea.name, industry=idea.industry, rationale=idea.rationale)

    snippets = "\n".join(f"- {e.title}: {e.snippet}" for e in evidence)
    try:
        check = confirm_llm.invoke(
            [
                SystemMessage(CONFIRM_SYSTEM),
                HumanMessage(f"Candidate: {idea.name}\n\nSnippets:\n{snippets}"),
            ]
        )
        if not isinstance(check, ExistenceCheck):
            check = ExistenceCheck(**check)
    except Exception as exc:  # noqa: BLE001 — if the check fails, treat as unvalidated
        logger.warning("existence check failed for %r: %s", idea.name, exc)
        return Candidate(name=idea.name, industry=idea.industry, rationale=idea.rationale)

    return Candidate(
        name=check.canonical_name.strip() or idea.name,
        industry=check.industry.strip() or idea.industry,
        rationale=idea.rationale,
        validated=check.exists,
        source_url=evidence[0].url,
    )


def validate_candidates(
    ideas: List[CandidateIdea],
    search: SearchClient,
    confirm_llm: Runnable,
    concurrency: int = 4,
) -> List[Candidate]:
    """Validate candidates concurrently. Returns ALL candidates (validated flag set);
    the orchestrator filters to `validated=True`."""
    if not ideas:
        return []
    workers = max(1, min(concurrency, len(ideas)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(lambda i: validate_one(i, search, confirm_llm), ideas))


__all__ = ["build_confirm_llm", "validate_one", "validate_candidates", "CONFIRM_SYSTEM"]
