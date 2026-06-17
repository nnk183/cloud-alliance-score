#!/usr/bin/env python3
"""Thin wrapper so the CLI runs without installing the package.

    python scripts/score_cli.py "Stripe" --context "payments platform"

Equivalent to the installed `score-company` console script.
"""

import sys
from pathlib import Path

# Make `src/` importable when running from a checkout.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from cloud_alliance_score.scripts_entry import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
