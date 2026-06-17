"""Typed schemas for the cloud alliance account scorer.

These models are the contract between the search tools, the scoring sub-agents,
the aggregator, and the API/UI layers. Keeping them in one place means the
LangGraph nodes, FastAPI responses, and tests all speak the same language.

Public contract:
    ScoringRequest   -> input (company_name + optional_context)
    DimensionScore   -> one dimension's score + reasoning + evidence trail
    CompositeScore   -> total_score (/25) + tier + the five DimensionScores
    ScoringResponse  -> CompositeScore wrapped with run metadata
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, computed_field, field_validator, model_validator

# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class Dimension(str, Enum):
    """The five scoring dimensions for a cloud alliance account."""

    GCP_COMMIT = "gcp_commit"
    AI_MATURITY = "ai_maturity"
    INDUSTRY_FIT = "industry_fit"
    LANGCHAIN_FOOTPRINT = "langchain_footprint"
    STRATEGIC_SIGNALS = "strategic_signals"

    @property
    def label(self) -> str:
        """Human-readable label for reports and UI."""
        return {
            Dimension.GCP_COMMIT: "GCP Commit Size",
            Dimension.AI_MATURITY: "AI Maturity",
            Dimension.INDUSTRY_FIT: "Industry Fit",
            Dimension.LANGCHAIN_FOOTPRINT: "LangChain Footprint",
            Dimension.STRATEGIC_SIGNALS: "Strategic Signals",
        }[self]


class Tier(str, Enum):
    """Account priority tier derived from the composite score."""

    TIER_1 = "Tier 1"  # 20-25: prioritize, high alliance potential
    TIER_2 = "Tier 2"  # 12-19: nurture, moderate potential
    TIER_3 = "Tier 3"  # <12: deprioritize, low potential

    @classmethod
    def from_score(cls, total: int) -> "Tier":
        """Classify a total score (0-25) into a tier."""
        if total >= 20:
            return cls.TIER_1
        if total >= 12:
            return cls.TIER_2
        return cls.TIER_3

    @property
    def number(self) -> int:
        """The tier as an integer (1/2/3)."""
        return {Tier.TIER_1: 1, Tier.TIER_2: 2, Tier.TIER_3: 3}[self]


# Score bounds — single source of truth shared by validators and prompts.
MIN_DIMENSION_SCORE = 1
MAX_DIMENSION_SCORE = 5
MAX_TOTAL_SCORE = MAX_DIMENSION_SCORE * len(Dimension)  # 25


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------


class Evidence(BaseModel):
    """A single piece of web evidence (search snippet) a sub-agent relied on."""

    title: str = Field(..., description="Title of the source page.")
    url: str = Field(..., description="Source URL.")
    snippet: str = Field(..., description="Relevant excerpt that informed the score.")

    @field_validator("title", "snippet")
    @classmethod
    def _strip_and_require(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be empty")
        return v


# ---------------------------------------------------------------------------
# LLM-facing structured output
# ---------------------------------------------------------------------------


class DimensionAssessment(BaseModel):
    """The structured output a scoring sub-agent's LLM must return.

    Deliberately minimal: the LLM only decides the score and the reasoning.
    Dimension identity and the supporting evidence are attached by our code,
    not trusted to the model.
    """

    score: int = Field(
        ...,
        ge=MIN_DIMENSION_SCORE,
        le=MAX_DIMENSION_SCORE,
        description="Integer score from 1 (weak) to 5 (strong).",
    )
    reasoning: str = Field(
        ...,
        description="Exactly two sentences justifying the score, citing evidence.",
    )

    @field_validator("reasoning")
    @classmethod
    def _non_empty_reasoning(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("reasoning must not be empty")
        return v


# ---------------------------------------------------------------------------
# Aggregated results
# ---------------------------------------------------------------------------


class DimensionScore(BaseModel):
    """A completed score for one dimension, with its supporting evidence trail."""

    dimension: Dimension = Field(..., description="Which dimension this scores.")
    score: int = Field(..., ge=MIN_DIMENSION_SCORE, le=MAX_DIMENSION_SCORE)
    reasoning: str = Field(..., description="Two-sentence justification.")
    evidence: List[Evidence] = Field(
        default_factory=list,
        description="Search snippets the sub-agent used to justify the score.",
    )

    @computed_field  # type: ignore[prop-decorator]  # serialized for auditable JSON
    @property
    def dimension_name(self) -> str:
        return self.dimension.label

    @classmethod
    def from_assessment(
        cls,
        dimension: Dimension,
        assessment: DimensionAssessment,
        evidence: List[Evidence],
    ) -> "DimensionScore":
        """Combine an LLM assessment with the evidence our code collected."""
        return cls(
            dimension=dimension,
            score=assessment.score,
            reasoning=assessment.reasoning,
            evidence=evidence,
        )


class CompositeScore(BaseModel):
    """The aggregate score across all five dimensions."""

    total_score: int = Field(..., ge=0, le=MAX_TOTAL_SCORE, description="Sum out of 25.")
    tier: Tier
    dimension_scores: List[DimensionScore]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def tier_number(self) -> int:
        """Tier as an integer (1/2/3) for convenient client-side use."""
        return self.tier.number

    @model_validator(mode="after")
    def _check_consistency(self) -> "CompositeScore":
        # Every dimension must be scored exactly once.
        seen = [ds.dimension for ds in self.dimension_scores]
        missing = set(Dimension) - set(seen)
        if missing:
            raise ValueError(
                f"missing scores for dimensions: {sorted(d.value for d in missing)}"
            )
        if len(seen) != len(set(seen)):
            raise ValueError("duplicate dimension scores present")

        # total_score must equal the sum of dimension scores.
        expected = sum(ds.score for ds in self.dimension_scores)
        if self.total_score != expected:
            raise ValueError(
                f"total_score {self.total_score} != sum of dimensions {expected}"
            )

        # tier must match the total.
        expected_tier = Tier.from_score(self.total_score)
        if self.tier != expected_tier:
            raise ValueError(
                f"tier {self.tier} inconsistent with total {self.total_score} "
                f"(expected {expected_tier})"
            )
        return self

    @classmethod
    def build(cls, dimension_scores: List[DimensionScore]) -> "CompositeScore":
        """Construct a composite, deriving total + tier from the scores.

        This is the canonical constructor so total and tier can never drift
        out of sync with the underlying dimension scores.
        """
        ordered = sorted(
            dimension_scores, key=lambda ds: list(Dimension).index(ds.dimension)
        )
        total = sum(ds.score for ds in ordered)
        return cls(
            total_score=total,
            tier=Tier.from_score(total),
            dimension_scores=ordered,
        )


# ---------------------------------------------------------------------------
# API request / response
# ---------------------------------------------------------------------------


class ScoringRequest(BaseModel):
    """Input to the scorer."""

    company_name: str = Field(..., description="Company to evaluate.")
    optional_context: Optional[str] = Field(
        default=None,
        description="Optional hint to disambiguate (e.g. domain, industry, ticker).",
    )

    @field_validator("company_name")
    @classmethod
    def _require_company(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("company_name must not be empty")
        return v


class ScoringResponse(BaseModel):
    """The full scorecard returned to API/UI callers: composite + metadata."""

    company_name: str
    composite: CompositeScore
    summary: str = Field(
        default="",
        description="One-paragraph synthesis of the account's alliance fit.",
    )
    model_used: str = Field(default="", description="LLM model id used for scoring.")
    optional_context: Optional[str] = Field(default=None)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("company_name")
    @classmethod
    def _require_company(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("company_name must not be empty")
        return v

    @classmethod
    def build(
        cls,
        company_name: str,
        dimension_scores: List[DimensionScore],
        summary: str = "",
        model_used: str = "",
        optional_context: Optional[str] = None,
        generated_at: Optional[datetime] = None,
    ) -> "ScoringResponse":
        """Assemble a response, deriving the composite from the dimension scores."""
        composite = CompositeScore.build(dimension_scores)
        kwargs = dict(
            company_name=company_name,
            composite=composite,
            summary=summary,
            model_used=model_used,
            optional_context=optional_context,
        )
        if generated_at is not None:
            kwargs["generated_at"] = generated_at
        return cls(**kwargs)


__all__ = [
    "Dimension",
    "Tier",
    "Evidence",
    "DimensionAssessment",
    "DimensionScore",
    "CompositeScore",
    "ScoringRequest",
    "ScoringResponse",
    "MIN_DIMENSION_SCORE",
    "MAX_DIMENSION_SCORE",
    "MAX_TOTAL_SCORE",
]
