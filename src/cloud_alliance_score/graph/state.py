"""Graph state for the scoring run.

The supervisor fans out to five sub-agents that run concurrently. Each returns
its own `DimensionScore`; the `operator.add` reducer on `dimension_scores`
appends them as they complete, so the parallel branches never clobber each
other. The aggregator reads the merged list once all branches converge.
"""

from __future__ import annotations

import operator
from typing import Annotated, List, Optional, TypedDict

from ..schemas import Dimension, DimensionScore, ScoringResponse


class ScoringState(TypedDict, total=False):
    """State shared across the graph.

    `dimension` is a transient field set on each fan-out branch via `Send`; the
    sub-agent node reads it to know which dimension it is scoring.
    """

    company: str
    optional_context: Optional[str]
    dimension: Optional[Dimension]
    dimension_scores: Annotated[List[DimensionScore], operator.add]
    response: Optional[ScoringResponse]


__all__ = ["ScoringState"]
