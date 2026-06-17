"""Command-line entry point: score a company from the terminal.

Installed as the ``score-company`` console script (see pyproject). Run:

    score-company "Stripe"
    score-company "Capital One" --context "US bank" --json
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional

from .pipeline import score_company
from .schemas import ScoringResponse


def _format_human(resp: ScoringResponse) -> str:
    c = resp.composite
    lines: List[str] = []
    lines.append("=" * 64)
    lines.append(f"  {resp.company_name}")
    if resp.optional_context:
        lines.append(f"  context: {resp.optional_context}")
    lines.append("=" * 64)
    for ds in c.dimension_scores:
        bar = "█" * ds.score + "·" * (5 - ds.score)
        lines.append(f"  {ds.dimension_name:<22} [{bar}] {ds.score}/5")
        lines.append(f"      {ds.reasoning}")
        if ds.evidence:
            lines.append(f"      evidence: {len(ds.evidence)} source(s)")
            for ev in ds.evidence[:2]:
                lines.append(f"        - {ev.url}")
    lines.append("-" * 64)
    lines.append(f"  COMPOSITE: {c.total_score}/25   →   {c.tier.value}")
    if resp.summary:
        lines.append("")
        lines.append(f"  {resp.summary}")
    lines.append("=" * 64)
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="score-company",
        description="Score a company as a cloud alliance account (LangChain × GCP).",
    )
    parser.add_argument("company", help="Company name to evaluate.")
    parser.add_argument(
        "--context",
        default=None,
        help="Optional disambiguating context (e.g. domain, industry, ticker).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the full ScoringResponse as JSON instead of a formatted report.",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        resp = score_company(args.company, optional_context=args.context)
    except RuntimeError as exc:
        # Config error (missing keys) — actionable message, non-zero exit.
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001
        print(f"scoring failed: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(resp.model_dump(mode="json"), indent=2))
    else:
        print(_format_human(resp))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
