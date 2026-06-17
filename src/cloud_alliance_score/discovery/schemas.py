"""Schemas for Discovery Mode.

Discovery generates candidate companies for a vendor pair, validates that they
are real, scores them with the existing engine, and ranks them. These models
are kept separate from the core `schemas.py` but reuse `ScoringResponse`
wholesale — the scoring contract is not duplicated.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from pydantic import BaseModel, Field, computed_field, field_validator

from ..schemas import ScoringResponse, Tier


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------


class DiscoveryRequest(BaseModel):
    """Input to Discovery Mode."""

    vendor_pair: str = Field(..., description="Alliance pair, e.g. 'LangChain × GCP'.")
    n_candidates: int = Field(
        default=10, ge=1, description="Number of top-ranked candidates to return."
    )

    @field_validator("vendor_pair")
    @classmethod
    def _require_pair(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("vendor_pair must not be empty")
        return v


# ---------------------------------------------------------------------------
# Candidate generation (LLM-facing) + validation
# ---------------------------------------------------------------------------


class CandidateIdea(BaseModel):
    """One proposed company from the generator (pre-validation)."""

    name: str = Field(..., description="Company name.")
    industry: str = Field(default="", description="Best-guess industry.")
    rationale: str = Field(default="", description="One line: why it fits the pair.")

    @field_validator("name")
    @classmethod
    def _require_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("candidate name must not be empty")
        return v


class CandidateList(BaseModel):
    """The generator's structured output: a batch of candidate ideas."""

    candidates: List[CandidateIdea] = Field(default_factory=list)


class ExistenceCheck(BaseModel):
    """The validator's structured confirmation that a candidate is a real company."""

    exists: bool = Field(..., description="True if the snippets confirm a real company.")
    canonical_name: str = Field(default="", description="Cleaned/official company name.")
    industry: str = Field(default="", description="Industry inferred from evidence.")


class Candidate(BaseModel):
    """A candidate after validation."""

    name: str
    industry: str = ""
    rationale: str = ""
    validated: bool = False
    source_url: Optional[str] = None


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------


class ScoredCandidate(BaseModel):
    """A ranked, scored candidate. Wraps the existing ScoringResponse."""

    rank: int = Field(..., ge=1)
    scorecard: ScoringResponse

    @computed_field  # type: ignore[prop-decorator]
    @property
    def composite_score(self) -> int:
        return self.scorecard.composite.total_score

    @computed_field  # type: ignore[prop-decorator]
    @property
    def tier(self) -> Tier:
        return self.scorecard.composite.tier


class DiscoveryResponse(BaseModel):
    """The full Discovery result: top-N ranked candidates + run metadata."""

    vendor_pair: str
    requested: int
    generated: int = 0
    validated: int = 0
    scored: int = 0
    results: List[ScoredCandidate] = Field(default_factory=list)
    model_used: str = ""
    cached: bool = False
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


__all__ = [
    "DiscoveryRequest",
    "CandidateIdea",
    "CandidateList",
    "ExistenceCheck",
    "Candidate",
    "ScoredCandidate",
    "DiscoveryResponse",
]
