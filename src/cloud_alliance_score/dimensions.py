"""Definitions for the five scoring dimensions.

Each `DimensionSpec` bundles everything a sub-agent needs to be distinct:
- the search queries it issues to Tavily to gather evidence, and
- the rubric / system prompt that tells Claude how to map evidence to a 1-5 score.

The LangGraph sub-agent node is generic; the *behavior* per dimension lives
entirely in these specs, which keeps the graph code DRY and the scoring logic
reviewable in one place.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from .schemas import Dimension, MAX_DIMENSION_SCORE, MIN_DIMENSION_SCORE


@dataclass(frozen=True)
class DimensionSpec:
    """Per-dimension search + scoring configuration."""

    dimension: Dimension
    description: str
    # Search query templates; `{company}` is substituted at runtime.
    query_templates: List[str]
    # Rubric lines describing what a low (1) vs high (5) score looks like.
    rubric: str

    def queries(self, company: str) -> List[str]:
        return [t.format(company=company) for t in self.query_templates]

    def system_prompt(self) -> str:
        """Build the system prompt that frames this dimension's scoring task."""
        return SYSTEM_PROMPT_TEMPLATE.format(
            label=self.dimension.label,
            description=self.description,
            rubric=self.rubric.strip(),
            min_score=MIN_DIMENSION_SCORE,
            max_score=MAX_DIMENSION_SCORE,
        )


SYSTEM_PROMPT_TEMPLATE = """\
You are a cloud-alliance analyst evaluating a company as a potential joint
account for a LangChain × Google Cloud (GCP) partnership.

Your focus is a single dimension: **{label}**.
{description}

You will be given web-search evidence about the company. Score the company on
this dimension using an integer from {min_score} (weak) to {max_score} (strong),
following this rubric:

{rubric}

Rules:
- Base your score ONLY on the supplied evidence. Do not invent facts.
- If evidence is thin or absent, score conservatively (toward {min_score}) and
  say so in your reasoning.
- Provide EXACTLY TWO sentences of reasoning that cite what the evidence shows.
"""


# ---------------------------------------------------------------------------
# The five specs
# ---------------------------------------------------------------------------

DIMENSION_SPECS: Dict[Dimension, DimensionSpec] = {
    Dimension.GCP_COMMIT: DimensionSpec(
        dimension=Dimension.GCP_COMMIT,
        description=(
            "Estimate the company's likely commitment to / spend on Google Cloud. "
            "Proxies: job postings mentioning GCP, BigQuery, Vertex AI, or GKE; "
            "public GCP customer references / case studies; announced cloud "
            "commitments or migrations; signals of overall cloud spend."
        ),
        query_templates=[
            "{company} Google Cloud Platform customer case study",
            "{company} jobs GCP BigQuery Vertex AI GKE",
            "{company} cloud migration Google Cloud commitment",
        ],
        rubric="""
- 5: Public, sizable GCP commitment — named GCP customer/case study, multiple GCP-heavy roles, or announced multi-year deal.
- 4: Clear GCP usage signals — several job posts citing GCP services or a public GCP reference.
- 3: Mixed/multi-cloud with some GCP presence, or indirect indicators of GCP spend.
- 2: Minimal GCP signal; primarily another cloud (AWS/Azure) with little GCP mention.
- 1: No evidence of GCP usage or cloud spend at all.
""",
    ),
    Dimension.AI_MATURITY: DimensionSpec(
        dimension=Dimension.AI_MATURITY,
        description=(
            "Assess how mature the company is at building and shipping AI/ML in "
            "production. Proxies: production AI deployments, public case studies, "
            "ML/AI platform investments, and AI-focused hiring patterns."
        ),
        query_templates=[
            "{company} production machine learning AI deployment case study",
            "{company} AI ML engineering team hiring",
            "{company} generative AI LLM product launch",
        ],
        rubric="""
- 5: Multiple production AI systems and public case studies; clearly AI-native with a strong ML org.
- 4: Demonstrated production AI plus active AI/ML hiring.
- 3: Some AI initiatives or pilots; emerging ML capability.
- 2: Early experimentation or aspirational AI talk with little shipped.
- 1: No evidence of AI/ML capability.
""",
    ),
    Dimension.INDUSTRY_FIT: DimensionSpec(
        dimension=Dimension.INDUSTRY_FIT,
        description=(
            "Judge how well the company's industry fits high-value GenAI use "
            "cases for this alliance. Favor regulated industries (finance, "
            "healthcare, insurance), digital-native companies, and data-heavy "
            "verticals where LLM + cloud solutions create clear value."
        ),
        query_templates=[
            "{company} industry sector business model overview",
            "{company} regulated data privacy compliance industry",
            "{company} digital native data platform vertical",
        ],
        rubric="""
- 5: Regulated and/or highly data-heavy vertical (e.g. fintech, healthcare, insurance) with obvious GenAI value.
- 4: Digital-native or data-rich business with strong AI applicability.
- 3: Moderate fit — some data/AI applicability but not a core driver.
- 2: Limited fit; industry rarely an early GenAI adopter.
- 1: Poor fit; low data intensity and little GenAI relevance.
""",
    ),
    Dimension.LANGCHAIN_FOOTPRINT: DimensionSpec(
        dimension=Dimension.LANGCHAIN_FOOTPRINT,
        description=(
            "Detect existing usage of or affinity for LangChain / LangGraph / "
            "LangSmith. Proxies: engineering-blog mentions, public GitHub usage, "
            "conference talks, job posts listing LangChain in the stack."
        ),
        query_templates=[
            "{company} LangChain engineering blog",
            "{company} LangGraph LangSmith GitHub",
            "{company} jobs LangChain LLM framework tech stack",
        ],
        rubric="""
- 5: Public, documented LangChain/LangGraph usage — engineering blog posts, talks, or GitHub repos.
- 4: Multiple signals (job posts + community mentions) of LangChain in the stack.
- 3: Some indication of LangChain interest or one credible mention.
- 2: Uses LLMs but no LangChain-specific signal.
- 1: No evidence of LangChain ecosystem usage.
""",
    ),
    Dimension.STRATEGIC_SIGNALS: DimensionSpec(
        dimension=Dimension.STRATEGIC_SIGNALS,
        description=(
            "Capture top-down strategic momentum toward AI. Proxies: Chief AI "
            "Officer or VP of AI hires, AI emphasis in earnings calls / investor "
            "communications, recent GenAI investments, partnerships, or funding."
        ),
        query_templates=[
            "{company} Chief AI Officer hire executive",
            "{company} earnings call generative AI strategy",
            "{company} recent AI investment partnership announcement 2025 2026",
        ],
        rubric="""
- 5: Clear executive-level AI commitment — e.g. Chief AI Officer, AI as an earnings-call priority, major GenAI investment.
- 4: Strong strategic signals such as senior AI leadership or announced GenAI initiatives.
- 3: Some strategic intent — AI mentioned by leadership or modest investment.
- 2: Faint signals; AI not a stated priority.
- 1: No strategic AI signals.
""",
    ),
}


def get_spec(dimension: Dimension) -> DimensionSpec:
    return DIMENSION_SPECS[dimension]


def all_specs() -> List[DimensionSpec]:
    """All specs in canonical Dimension order."""
    return [DIMENSION_SPECS[d] for d in Dimension]


__all__ = ["DimensionSpec", "DIMENSION_SPECS", "get_spec", "all_specs"]
