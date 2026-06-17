"""Candidate generator: ask an LLM for real companies fitting a vendor pair.

The model first infers the alliance's ideal customer profile from the vendor
pair, then proposes real, diverse companies. Anti-hallucination framing keeps
the list grounded; the validator (validator.py) is the second net.
"""

from __future__ import annotations

from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import Runnable

from ..config import Settings, get_settings
from .schemas import CandidateList

SYSTEM_PROMPT = """\
You are a partnership-strategy analyst for a cloud/AI alliance between two
vendors: {vendor_pair}.

First, silently infer the alliance's IDEAL TARGET ACCOUNT PROFILE — the kind of
company this pair would jointly pursue. For example, for "LangChain × GCP" that
means companies likely on (or open to) Google Cloud, with production AI
ambitions, in data-heavy or regulated verticals where LLM solutions create value.

Then propose {count} companies that best fit that profile.

Rules:
- Only include companies you are HIGHLY CONFIDENT actually exist and operate
  today. Prefer well-known or established mid-market firms you know well.
  DO NOT invent names or guess.
- MAXIMIZE DIVERSITY — span multiple industries, sizes, and geographies; avoid a
  list of near-identical big-tech names.
- EXCLUDE the two alliance vendors themselves and their direct competitors.
- No duplicates; no parent/subsidiary repeats.
- For each company give its name, its industry, and a one-sentence rationale
  tied to the profile you inferred.
"""


def build_generator_llm(settings: Optional[Settings] = None) -> Runnable:
    """A Discovery-model (Haiku) LLM bound to emit a validated CandidateList."""
    settings = settings or get_settings()
    from ..llm import get_chat_model

    return get_chat_model(settings, model=settings.discovery_model).with_structured_output(
        CandidateList
    )


def generate_candidates(
    vendor_pair: str,
    count: int,
    llm: Runnable,
) -> CandidateList:
    """Generate up to `count` candidate companies for `vendor_pair`."""
    messages = [
        SystemMessage(SYSTEM_PROMPT.format(vendor_pair=vendor_pair, count=count)),
        HumanMessage(
            f"Propose {count} real target-account companies for the "
            f"{vendor_pair} alliance, following the rules."
        ),
    ]
    result = llm.invoke(messages)
    return result if isinstance(result, CandidateList) else CandidateList(**result)


__all__ = ["build_generator_llm", "generate_candidates", "SYSTEM_PROMPT"]
