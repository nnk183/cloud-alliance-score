"""Vercel Python entrypoint.

Vercel serves this file as a serverless function. All `/api/*` requests are
rewritten here (see vercel.json), and the inner FastAPI app is mounted under
`/api`, so e.g. `/api/score` maps to the app's `/score` route.

The static frontend in `public/` is served directly by Vercel's CDN and calls
these `/api/*` endpoints.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make the `src/` package importable in the Vercel build sandbox.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fastapi import FastAPI  # noqa: E402

from cloud_alliance_score.api import app as inner_app  # noqa: E402

app = FastAPI()
app.mount("/api", inner_app)
