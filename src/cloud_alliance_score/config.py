"""Application configuration and observability wiring.

Loads settings from environment / `.env` via pydantic-settings, and provides a
single `configure_langsmith()` entry point so tracing is set up consistently
whether the scorer is invoked from the API, the CLI, the UI, or a test.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, sourced from environment variables / `.env`.

    Field names map to env vars case-insensitively; the `CAS_` prefix namespaces
    our own tuning knobs while the provider keys keep their conventional names.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Provider credentials -------------------------------------------------
    anthropic_api_key: Optional[str] = Field(default=None, alias="ANTHROPIC_API_KEY")
    tavily_api_key: Optional[str] = Field(default=None, alias="TAVILY_API_KEY")
    langsmith_api_key: Optional[str] = Field(default=None, alias="LANGSMITH_API_KEY")

    # --- LangSmith / observability -------------------------------------------
    langsmith_tracing: bool = Field(default=False, alias="LANGSMITH_TRACING")
    langsmith_project: str = Field(default="cloud-alliance-score", alias="LANGSMITH_PROJECT")
    langsmith_endpoint: str = Field(
        default="https://api.smith.langchain.com", alias="LANGSMITH_ENDPOINT"
    )

    # --- Scoring tuning -------------------------------------------------------
    model: str = Field(default="claude-sonnet-4-6", alias="CAS_MODEL")
    search_max_results: int = Field(default=5, alias="CAS_SEARCH_MAX_RESULTS")
    temperature: float = Field(default=0.0, alias="CAS_TEMPERATURE")
    request_timeout: float = Field(default=60.0, alias="CAS_REQUEST_TIMEOUT")
    max_tokens: int = Field(default=1024, alias="CAS_MAX_TOKENS")

    # --- Tavily retry / backoff ----------------------------------------------
    search_retries: int = Field(default=3, alias="CAS_SEARCH_RETRIES")
    search_backoff_base: float = Field(default=0.5, alias="CAS_SEARCH_BACKOFF_BASE")
    search_backoff_max: float = Field(default=8.0, alias="CAS_SEARCH_BACKOFF_MAX")

    # --- Disk cache -----------------------------------------------------------
    cache_enabled: bool = Field(default=True, alias="CAS_CACHE_ENABLED")
    cache_dir: str = Field(default=".cache/cloud_alliance_score", alias="CAS_CACHE_DIR")
    cache_ttl_seconds: int = Field(default=86_400, alias="CAS_CACHE_TTL_SECONDS")

    # --- Public demo guardrails (used when CAS_DEMO_MODE=true) -----------------
    # Protect a public deployment from burning your API credits: a curated
    # gallery renders for free, and live scoring is capped per day and per visitor.
    demo_mode: bool = Field(default=False, alias="CAS_DEMO_MODE")
    demo_daily_cap: int = Field(default=25, alias="CAS_DEMO_DAILY_CAP")
    demo_session_cap: int = Field(default=3, alias="CAS_DEMO_SESSION_CAP")

    # --- Discovery Mode -------------------------------------------------------
    # Surface + score candidate accounts for a vendor pair. Uses a cheaper model
    # (Haiku) for batch scoring, and caps how many candidates are actually scored
    # (the dominant cost) independently of how many names are generated.
    discovery_model: str = Field(default="claude-haiku-4-5", alias="CAS_DISCOVERY_MODEL")
    discovery_generate_count: int = Field(default=30, alias="CAS_DISCOVERY_GENERATE_COUNT")
    discovery_max_score: int = Field(default=10, alias="CAS_DISCOVERY_MAX_SCORE")
    discovery_max_candidates: int = Field(default=10, alias="CAS_DISCOVERY_MAX_CANDIDATES")
    discovery_concurrency: int = Field(default=4, alias="CAS_DISCOVERY_CONCURRENCY")
    discovery_cache_ttl_seconds: int = Field(default=86_400, alias="CAS_DISCOVERY_CACHE_TTL_SECONDS")

    def require_anthropic(self) -> str:
        if not self.anthropic_api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add your key."
            )
        return self.anthropic_api_key

    def require_tavily(self) -> str:
        if not self.tavily_api_key:
            raise RuntimeError(
                "TAVILY_API_KEY is not set. Copy .env.example to .env and add your key."
            )
        return self.tavily_api_key


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance (read once per process)."""
    return Settings()


def configure_langsmith(settings: Optional[Settings] = None) -> bool:
    """Wire LangSmith tracing via the env vars the LangChain SDK reads.

    LangChain/LangGraph auto-instrument when `LANGSMITH_TRACING=true` and an API
    key are present in the environment. We set those from our Settings so a
    single source of truth (the `.env`) drives observability everywhere.

    Returns True if tracing was enabled, False otherwise.
    """
    settings = settings or get_settings()

    if not (settings.langsmith_tracing and settings.langsmith_api_key):
        # Make sure stale tracing flags don't leak in from the ambient env.
        os.environ["LANGSMITH_TRACING"] = "false"
        return False

    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key
    os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project
    os.environ["LANGSMITH_ENDPOINT"] = settings.langsmith_endpoint
    return True


__all__ = ["Settings", "get_settings", "configure_langsmith"]
