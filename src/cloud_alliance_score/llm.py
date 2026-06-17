"""Claude LLM factory.

Centralizes construction of the chat model so every sub-agent shares the same
model id, temperature, and timeout, and so structured-output binding lives in
one place. Sub-agents call `get_assessment_llm()` to get a model that is
guaranteed to return a validated `DimensionAssessment`.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from langchain_anthropic import ChatAnthropic
from langchain_core.runnables import Runnable

from .config import Settings, get_settings
from .schemas import DimensionAssessment


@lru_cache(maxsize=4)
def _build_chat_model(
    model: str,
    temperature: float,
    max_tokens: int,
    timeout: float,
    api_key: str,
) -> ChatAnthropic:
    """Construct (and cache) a ChatAnthropic client for a given config tuple."""
    return ChatAnthropic(
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
        api_key=api_key,
        max_retries=2,
    )


def get_chat_model(
    settings: Optional[Settings] = None, model: Optional[str] = None
) -> ChatAnthropic:
    """Return a shared ChatAnthropic instance built from Settings.

    `model` overrides `settings.model` — used by Discovery Mode to run batch
    scoring on a cheaper model (Haiku) without disturbing the default.
    """
    settings = settings or get_settings()
    return _build_chat_model(
        model=model or settings.model,
        temperature=settings.temperature,
        max_tokens=settings.max_tokens,
        timeout=settings.request_timeout,
        api_key=settings.require_anthropic(),
    )


def get_assessment_llm(settings: Optional[Settings] = None) -> Runnable:
    """Return a model bound to emit a validated `DimensionAssessment`.

    `with_structured_output` makes Claude use tool-calling under the hood and
    returns a parsed Pydantic object, so sub-agents never parse raw text.
    """
    return get_chat_model(settings).with_structured_output(DimensionAssessment)  # type: ignore[arg-type]


__all__ = ["get_chat_model", "get_assessment_llm"]
