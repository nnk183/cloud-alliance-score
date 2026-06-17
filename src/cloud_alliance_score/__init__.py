"""Cloud Alliance Score — multi-agent account scorer for LangChain × GCP.

Scores companies as potential cloud alliance accounts across five dimensions
using a LangGraph supervisor that fans out to parallel scoring sub-agents.
"""

from .schemas import (
    CompositeScore,
    Dimension,
    DimensionAssessment,
    DimensionScore,
    Evidence,
    ScoringRequest,
    ScoringResponse,
    Tier,
)

__version__ = "0.1.0"

__all__ = [
    "CompositeScore",
    "Dimension",
    "DimensionAssessment",
    "DimensionScore",
    "Evidence",
    "ScoringRequest",
    "ScoringResponse",
    "Tier",
    "__version__",
]
