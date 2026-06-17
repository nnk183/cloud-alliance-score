"""Tavily web-search wrapper that yields typed `Evidence`.

Sub-agents call `gather_evidence()` with a dimension's queries; it runs each
query, normalizes Tavily results into `Evidence`, de-duplicates by URL, and
caps the total. Search failures degrade gracefully to an empty list so one
flaky query never crashes the whole scoring run.
"""

from __future__ import annotations

import logging
import time
from typing import List, Optional, Protocol, Sequence

from ..config import Settings, get_settings
from ..schemas import Evidence

logger = logging.getLogger(__name__)


class _Searcher(Protocol):
    """Minimal interface we need from a Tavily client (eases testing/mocking)."""

    def search(self, query: str, **kwargs: object) -> dict: ...


class SearchClient:
    """Thin wrapper around `tavily-python` returning typed `Evidence`."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        client: Optional[_Searcher] = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._client = client  # injectable for tests; lazily created otherwise

    def _get_client(self) -> _Searcher:
        if self._client is None:
            # Imported lazily so the package imports without the SDK installed.
            from tavily import TavilyClient

            self._client = TavilyClient(api_key=self._settings.require_tavily())
        return self._client

    def search_one(self, query: str, max_results: Optional[int] = None) -> List[Evidence]:
        """Run a single query with retry/backoff.

        Tries up to ``search_retries`` times with exponential backoff between
        attempts. If every attempt fails, returns [] (logged, never raised) so a
        single flaky query can't crash the whole scoring run.
        """
        max_results = max_results or self._settings.search_max_results
        attempts = max(1, self._settings.search_retries)
        last_exc: Optional[Exception] = None

        for attempt in range(attempts):
            try:
                raw = self._get_client().search(
                    query=query,
                    max_results=max_results,
                    search_depth="basic",
                )
                results = raw.get("results", []) if isinstance(raw, dict) else []
                return _results_to_evidence(results)
            except Exception as exc:  # noqa: BLE001 — retry on any SDK/network error
                last_exc = exc
                if attempt < attempts - 1:
                    delay = self._backoff_delay(attempt)
                    logger.warning(
                        "Tavily search failed for %r (attempt %d/%d): %s — retrying in %.1fs",
                        query, attempt + 1, attempts, exc, delay,
                    )
                    time.sleep(delay)

        logger.warning(
            "Tavily search gave up for %r after %d attempts: %s", query, attempts, last_exc
        )
        return []

    def _backoff_delay(self, attempt: int) -> float:
        """Exponential backoff: base * 2**attempt, capped at backoff_max."""
        base = self._settings.search_backoff_base
        return min(base * (2 ** attempt), self._settings.search_backoff_max)

    def gather(
        self,
        queries: Sequence[str],
        max_total: Optional[int] = None,
    ) -> List[Evidence]:
        """Run several queries, de-duplicate by URL, and cap the total count."""
        max_total = max_total or self._settings.search_max_results
        collected: List[Evidence] = []
        seen_urls: set[str] = set()

        for query in queries:
            for ev in self.search_one(query):
                if ev.url in seen_urls:
                    continue
                seen_urls.add(ev.url)
                collected.append(ev)

        return collected[:max_total]


def _results_to_evidence(results: Sequence[dict]) -> List[Evidence]:
    """Convert raw Tavily result dicts to validated `Evidence`, skipping junk."""
    evidence: List[Evidence] = []
    for r in results:
        url = (r.get("url") or "").strip()
        title = (r.get("title") or "").strip()
        snippet = (r.get("content") or r.get("snippet") or "").strip()
        if not url or not snippet:
            continue
        try:
            evidence.append(
                Evidence(title=title or url, url=url, snippet=snippet)
            )
        except Exception as exc:  # noqa: BLE001 — never let one bad row break the batch
            logger.debug("Skipping malformed Tavily result %r: %s", r, exc)
    return evidence


def gather_evidence(
    queries: Sequence[str],
    settings: Optional[Settings] = None,
    client: Optional[SearchClient] = None,
    max_total: Optional[int] = None,
) -> List[Evidence]:
    """Convenience entry point used by the sub-agent node."""
    client = client or SearchClient(settings=settings)
    return client.gather(queries, max_total=max_total)


__all__ = ["SearchClient", "gather_evidence"]
