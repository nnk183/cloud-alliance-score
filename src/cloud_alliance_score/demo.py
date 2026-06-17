"""Public-demo support: a curated gallery + a daily live-scoring rate limit.

For a public portfolio deployment we want two things:
  1. A **gallery** of pre-computed real scorecards that render instantly and
     cost nothing (no API calls) — the showcase.
  2. A **global daily cap** on live scoring so visitors can try their own
     company without draining the owner's Anthropic/Tavily credits.

The gallery is loaded from committed JSON in ``demo/scorecards/``. The limiter
is a single JSON counter file that resets each calendar day (UTC).
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Protocol, Tuple

from .config import Settings, get_settings
from .schemas import ScoringResponse

logger = logging.getLogger(__name__)

# demo/scorecards lives at the repo root, two levels up from this file's package.
_DEMO_DIR = Path(__file__).resolve().parent.parent.parent / "demo" / "scorecards"


# ---------------------------------------------------------------------------
# Curated gallery (pre-computed, free)
# ---------------------------------------------------------------------------


def list_demo_companies() -> List[Tuple[str, str]]:
    """Return ``(company_name, slug)`` for every committed demo scorecard."""
    if not _DEMO_DIR.exists():
        return []
    out: List[Tuple[str, str]] = []
    for path in sorted(_DEMO_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            out.append((data["company_name"], path.stem))
        except Exception as exc:  # noqa: BLE001 — skip a malformed fixture
            logger.warning("skipping demo fixture %s: %s", path, exc)
    return out


def load_demo_scorecard(slug: str) -> Optional[ScoringResponse]:
    """Load a committed scorecard by slug; None if missing/invalid."""
    path = _DEMO_DIR / f"{slug}.json"
    if not path.exists():
        return None
    try:
        return ScoringResponse.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not load demo scorecard %s: %s", slug, exc)
        return None


# ---------------------------------------------------------------------------
# Daily rate limit for live scoring
# ---------------------------------------------------------------------------


def _today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class DailyRateLimiter:
    """A simple global counter that caps live scorings per calendar day (UTC).

    Backed by one JSON file so the count survives process restarts within a day.
    Not perfectly atomic under heavy concurrency, but more than adequate as a
    credit-protection backstop for a portfolio demo.
    """

    def __init__(self, cap: int, state_path: Path):
        self.cap = cap
        self.path = state_path

    @classmethod
    def from_settings(cls, settings: Optional[Settings] = None) -> "DailyRateLimiter":
        settings = settings or get_settings()
        state = Path(settings.cache_dir) / "demo_usage.json"
        return cls(cap=settings.demo_daily_cap, state_path=state)

    def _read(self) -> Tuple[str, int]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data.get("date", ""), int(data.get("count", 0))
        except Exception:  # noqa: BLE001 — missing/corrupt -> fresh day
            return "", 0

    def _write(self, date: str, count: int) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps({"date": date, "count": count}), encoding="utf-8")
        except Exception as exc:  # noqa: BLE001 — best effort
            logger.warning("could not persist demo usage: %s", exc)

    def remaining(self) -> int:
        date, count = self._read()
        if date != _today_utc():
            return self.cap
        return max(0, self.cap - count)

    def allow(self) -> bool:
        return self.remaining() > 0

    def consume(self) -> bool:
        """Record one use. Returns False (and records nothing) if over the cap."""
        today = _today_utc()
        date, count = self._read()
        if date != today:
            date, count = today, 0
        if count >= self.cap:
            return False
        self._write(today, count + 1)
        return True


class RateLimiter(Protocol):
    """Common interface for the daily live-scoring guard."""

    cap: int

    def remaining(self) -> int: ...
    def allow(self) -> bool: ...
    def consume(self) -> bool: ...


class RedisDailyRateLimiter:
    """Daily cap backed by Upstash Redis — correct across serverless instances.

    Vercel's filesystem is ephemeral and per-instance, so a file counter can't
    enforce a *global* cap there. Upstash (REST Redis) gives us a shared counter.
    Auto-selected when ``UPSTASH_REDIS_REST_URL`` / ``_TOKEN`` are present.
    """

    def __init__(self, cap: int, client: object):
        self.cap = cap
        self._client = client

    @staticmethod
    def _key() -> str:
        return f"cas:demo:count:{_today_utc()}"

    def remaining(self) -> int:
        try:
            val = self._client.get(self._key())  # type: ignore[attr-defined]
            count = int(val) if val is not None else 0
        except Exception as exc:  # noqa: BLE001 — fail open-but-bounded
            logger.warning("redis remaining() failed: %s", exc)
            return self.cap
        return max(0, self.cap - count)

    def allow(self) -> bool:
        return self.remaining() > 0

    def consume(self) -> bool:
        key = self._key()
        try:
            count = int(self._client.incr(key))  # type: ignore[attr-defined]
            if count == 1:
                # First hit today — expire the key after 2 days to self-clean.
                self._client.expire(key, 172_800)  # type: ignore[attr-defined]
            return count <= self.cap
        except Exception as exc:  # noqa: BLE001
            logger.warning("redis consume() failed, allowing this request: %s", exc)
            return True


def get_rate_limiter(settings: Optional[Settings] = None) -> RateLimiter:
    """Return the best available limiter: Upstash Redis if configured, else file.

    Tests and local runs use the file-based limiter (no network); Vercel uses
    Redis automatically once the Upstash integration injects its env vars.
    """
    settings = settings or get_settings()
    url = os.environ.get("UPSTASH_REDIS_REST_URL")
    token = os.environ.get("UPSTASH_REDIS_REST_TOKEN")
    if url and token:
        try:
            from upstash_redis import Redis

            return RedisDailyRateLimiter(
                cap=settings.demo_daily_cap, client=Redis(url=url, token=token)
            )
        except Exception as exc:  # noqa: BLE001 — fall back to file counter
            logger.warning("Upstash unavailable (%s); using file-based limiter", exc)
    return DailyRateLimiter.from_settings(settings)


__all__ = [
    "list_demo_companies",
    "load_demo_scorecard",
    "DailyRateLimiter",
    "RedisDailyRateLimiter",
    "RateLimiter",
    "get_rate_limiter",
]
