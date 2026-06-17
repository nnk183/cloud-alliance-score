"""Whole-run cache for Discovery Mode.

Keyed on ``(vendor_pair, n_candidates, model)`` with a 24h TTL, so re-running
Discovery for the same pair returns instantly and spends nothing. (Per-candidate
scores are *also* cached by the core DimensionCache, so even a cache miss reuses
any overlapping company scores.)
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Optional

from ..config import Settings, get_settings

logger = logging.getLogger(__name__)

CACHE_VERSION = "v1"


class DiscoveryCache:
    """JSON file cache for full Discovery runs."""

    def __init__(self, cache_dir: str, ttl_seconds: int, enabled: bool = True, model: str = ""):
        self.enabled = enabled
        self.ttl_seconds = ttl_seconds
        self.model = model
        self._dir = Path(cache_dir) / "discovery"

    @classmethod
    def from_settings(cls, settings: Optional[Settings] = None) -> "DiscoveryCache":
        settings = settings or get_settings()
        return cls(
            cache_dir=settings.cache_dir,
            ttl_seconds=settings.discovery_cache_ttl_seconds,
            enabled=settings.cache_enabled,
            model=settings.discovery_model,
        )

    def _path(self, vendor_pair: str, n: int) -> Path:
        raw = f"{CACHE_VERSION}|{self.model}|{vendor_pair.strip().lower()}|{n}"
        key = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
        return self._dir / f"{key}.json"

    def get(self, vendor_pair: str, n: int) -> Optional[dict]:
        if not self.enabled:
            return None
        path = self._path(vendor_pair, n)
        try:
            if not path.exists():
                return None
            entry = json.loads(path.read_text(encoding="utf-8"))
            if time.time() - entry.get("stored_at", 0) > self.ttl_seconds:
                path.unlink(missing_ok=True)
                return None
            return entry.get("data")
        except Exception as exc:  # noqa: BLE001
            logger.warning("discovery cache read failed: %s", exc)
            return None

    def set(self, vendor_pair: str, n: int, data: dict) -> None:
        if not self.enabled:
            return
        path = self._path(vendor_pair, n)
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(
                json.dumps({"stored_at": time.time(), "data": data}, ensure_ascii=False),
                encoding="utf-8",
            )
            tmp.replace(path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("discovery cache write failed: %s", exc)


__all__ = ["DiscoveryCache", "CACHE_VERSION"]
