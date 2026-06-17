"""Simple disk-based cache for scoring results.

Keyed on ``(company_name, dimension, model)`` with a TTL (default 24h). Caches
the *full* per-dimension result, so re-scoring the same company during
development is a cache hit that spends zero Tavily and zero Anthropic credits.

Dependency-free: one JSON file per key under the configured cache directory.
The cache is schema-agnostic — it stores and returns plain dicts; callers
handle (de)serialization to/from Pydantic models.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Optional

from ..config import Settings, get_settings
from ..schemas import Dimension

logger = logging.getLogger(__name__)

# Bump when the cached payload shape changes, to invalidate stale entries.
CACHE_VERSION = "v1"


class DimensionCache:
    """JSON file cache for per-dimension scoring results."""

    def __init__(
        self,
        cache_dir: str,
        ttl_seconds: int,
        enabled: bool = True,
        model: str = "",
    ) -> None:
        self.enabled = enabled
        self.ttl_seconds = ttl_seconds
        self.model = model
        self._dir = Path(cache_dir)

    @classmethod
    def from_settings(cls, settings: Optional[Settings] = None) -> "DimensionCache":
        settings = settings or get_settings()
        return cls(
            cache_dir=settings.cache_dir,
            ttl_seconds=settings.cache_ttl_seconds,
            enabled=settings.cache_enabled,
            model=settings.model,
        )

    # --- key / path ----------------------------------------------------------

    def _key(self, company: str, dimension: Dimension) -> str:
        raw = f"{CACHE_VERSION}|{self.model}|{company.strip().lower()}|{dimension.value}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]

    def _path(self, company: str, dimension: Dimension) -> Path:
        return self._dir / f"{self._key(company, dimension)}.json"

    # --- get / set -----------------------------------------------------------

    def get(self, company: str, dimension: Dimension) -> Optional[dict]:
        """Return cached payload dict, or None on miss / expiry / error."""
        if not self.enabled:
            return None
        path = self._path(company, dimension)
        try:
            if not path.exists():
                return None
            entry = json.loads(path.read_text(encoding="utf-8"))
            age = time.time() - entry.get("stored_at", 0)
            if age > self.ttl_seconds:
                path.unlink(missing_ok=True)  # evict expired entry
                return None
            logger.debug("cache hit: %s / %s (age %.0fs)", company, dimension.value, age)
            return entry.get("data")
        except Exception as exc:  # noqa: BLE001 — a bad cache file must never break a run
            logger.warning("cache read failed for %s/%s: %s", company, dimension.value, exc)
            return None

    def set(self, company: str, dimension: Dimension, data: dict) -> None:
        """Write a payload dict to the cache (best-effort; failures are logged)."""
        if not self.enabled:
            return
        path = self._path(company, dimension)
        entry = {
            "stored_at": time.time(),
            "company": company,
            "dimension": dimension.value,
            "model": self.model,
            "version": CACHE_VERSION,
            "data": data,
        }
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            # Atomic-ish write: temp file then replace.
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(entry, ensure_ascii=False), encoding="utf-8")
            tmp.replace(path)
        except Exception as exc:  # noqa: BLE001 — caching is best-effort
            logger.warning("cache write failed for %s/%s: %s", company, dimension.value, exc)

    def clear(self) -> int:
        """Delete all cache files; return the number removed."""
        if not self._dir.exists():
            return 0
        removed = 0
        for f in self._dir.glob("*.json"):
            try:
                f.unlink()
                removed += 1
            except OSError:
                pass
        return removed


__all__ = ["DimensionCache", "CACHE_VERSION"]
