# ☁️ Cloud Alliance Score

![CI](https://github.com/nnk183/cloud-alliance-score/actions/workflows/ci.yml/badge.svg)

A **multi-agent account scorer** that evaluates companies as potential cloud
alliance accounts for a **LangChain × Google Cloud (GCP)** partnership.

Give it a company name; it returns a structured scorecard across **five
dimensions**, a composite score out of 25, a priority tier, and an evidence
trail for every judgment.

Built on **LangGraph** (supervisor → 5 parallel sub-agents → aggregator),
**Claude** for scoring, **Tavily** for web evidence, and **LangSmith** for
observability.

It runs in two modes:
- **Single Company Score** — name a company, get its scorecard.
- **Discovery Mode** — name a *vendor pair* (e.g. "LangChain × GCP"); it
  generates candidate companies, validates they're real, scores them with the
  same engine (on cheaper **Claude Haiku**), and returns a ranked shortlist.

---

## How it works

```
                         ┌──────────────────────────────────────────┐
                         │            Supervisor (fan-out)           │
                         │      Send × 5  →  parallel sub-agents      │
                         └──────────────────────────────────────────┘
            ┌───────────────┬───────────────┬───────────────┬───────────────┐
            ▼               ▼               ▼               ▼               ▼
     ┌───────────┐   ┌───────────┐   ┌───────────┐   ┌───────────┐   ┌───────────┐
     │ GCP Commit│   │AI Maturity│   │Industry Fit│  │ LangChain │   │ Strategic │
     │  sub-agent│   │ sub-agent │   │  sub-agent │  │ Footprint │   │  Signals  │
     └─────┬─────┘   └─────┬─────┘   └─────┬─────┘   └─────┬─────┘   └─────┬─────┘
           │  each: Tavily search → evidence → Claude scores 1–5 + reasoning │
           └───────────────┴───────────────┴───────────────┴───────────────┘
                                          ▼
                         ┌──────────────────────────────────────────┐
                         │  Aggregator → composite /25 → Tier 1/2/3  │
                         │           + one-paragraph summary          │
                         └──────────────────────────────────────────┘
```

Each sub-agent runs the **same generic node** parameterized by a per-dimension
spec (search queries + scoring rubric), so all dimension-specific behavior lives
in one reviewable place (`src/cloud_alliance_score/dimensions.py`).

### The five dimensions

| Dimension | What it proxies |
|---|---|
| **GCP Commit Size** | Job posts citing GCP/BigQuery/Vertex AI/GKE, public GCP case studies, cloud-spend signals |
| **AI Maturity** | Production AI deployments, public case studies, AI-focused hiring |
| **Industry Fit** | Regulated / digital-native / data-heavy verticals where GenAI creates value |
| **LangChain Footprint** | Engineering-blog mentions, GitHub usage, LangChain in the tech stack |
| **Strategic Signals** | Chief AI Officer hires, AI in earnings calls, recent GenAI investment |

### Tiers

| Tier | Composite (out of 25) | Meaning |
|---|---|---|
| **Tier 1** | 20–25 | Prioritize — high alliance potential |
| **Tier 2** | 12–19 | Nurture — moderate potential |
| **Tier 3** | < 12 | Deprioritize — low potential |

---

## Setup

Requires **Python 3.11+**.

```bash
# 1. Install (editable, with dev + ui extras)
make setup            # == pip install -e ".[dev,ui]"  +  cp .env.example .env

# ...or manually:
python -m pip install -e ".[dev,ui]"
cp .env.example .env
```

### API key configuration

Edit `.env` (created from `.env.example`):

| Variable | Required? | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | **Yes** | Claude — the LLM behind every sub-agent |
| `TAVILY_API_KEY` | **Yes** | Web search for evidence gathering |
| `LANGSMITH_API_KEY` | Optional | Tracing/observability of the LangGraph run |

Get keys from [Anthropic Console](https://console.anthropic.com/settings/keys),
[Tavily](https://app.tavily.com/), and [LangSmith](https://smith.langchain.com/).

Optional tuning knobs (model, search retries, cache TTL, …) are documented
inline in `.env.example`.

---

## Usage

### CLI

```bash
# Formatted report
python scripts/score_cli.py "Stripe" --context "payments platform"
# ...or, once installed:  score-company "Stripe"

# Machine-readable JSON
python scripts/score_cli.py "Capital One" --json

# Via make
make score COMPANY="Sephora"
```

### HTTP API (FastAPI)

```bash
make api          # uvicorn on http://localhost:8000  (docs at /docs)
```

```bash
curl -s http://localhost:8000/score \
  -H "Content-Type: application/json" \
  -d '{"company_name": "Stripe", "optional_context": "payments platform"}' | jq
```

- `GET /health` — liveness + which keys are configured
- `POST /score` — `ScoringRequest` → `ScoringResponse`

### Streamlit UI

```bash
make ui           # streamlit run app/streamlit_app.py
```

### Docker (no local Python needed)

Run the API **and** the UI with just Docker:

```bash
cp .env.example .env          # add ANTHROPIC_API_KEY + TAVILY_API_KEY
docker compose up --build
# API -> http://localhost:8000/docs   ·   UI -> http://localhost:8501
```

Keys are read at runtime from your local `.env` (never baked into the image),
and the disk cache is persisted in a named volume so repeat scores stay free.

### Python

```python
from cloud_alliance_score import score_company  # re-exported convenience

resp = score_company("Stripe", optional_context="payments platform")
print(resp.composite.total_score, resp.composite.tier.value)
for ds in resp.composite.dimension_scores:
    print(ds.dimension_name, ds.score, ds.reasoning)
```

### Discovery Mode

Find candidate accounts for a vendor pair instead of naming a company.

```python
from cloud_alliance_score.pipeline import discover_candidates

result = discover_candidates("LangChain × GCP", n_candidates=5)
for c in result.results:
    print(c.rank, c.scorecard.company_name, c.composite_score, c.tier.value)
```

```bash
# API
curl -s http://localhost:8000/discover \
  -H "Content-Type: application/json" \
  -d '{"vendor_pair": "LangChain × GCP", "n_candidates": 5}' | jq
```

**How it works:** generate ~30 candidate names (1 LLM call) → validate each is a
real company via Tavily + a cheap Haiku confirmation (drop hallucinations) →
score the validated ones with the **existing scoring engine** (reused, not
duplicated) on **Claude Haiku** → rank by composite, return top N. The number
*scored* is capped (`CAS_DISCOVERY_MAX_SCORE`, default 10) to bound cost, and
whole runs are cached 24h per vendor pair. See [EXAMPLES.md](EXAMPLES.md) for a
real Discovery run. The Streamlit UI exposes it as a **Discovery Mode** tab.

> `score_company` lives in `cloud_alliance_score.pipeline`; it is the single
> entry point shared by the CLI, API, and UI.

See **[EXAMPLES.md](EXAMPLES.md)** for full sample scorecards (Stripe, Capital
One, Sephora).

---

## Deploy a public demo on Vercel

A static frontend (`public/index.html`) + the FastAPI app as a Vercel Python
function (`api/index.py`) give you one public URL with a **free curated gallery**
and **rate-limited live scoring** that protects your API credits.

**What's already wired:** `vercel.json` (routing), `requirements.txt` (the lean
function deps), the gallery JSON in `demo/scorecards/`, and an Upstash-backed
daily cap that the demo activates automatically.

**Steps (≈5 min, all in the browser):**

1. **Push this repo to GitHub.**
2. **Import it on Vercel** → [vercel.com/new](https://vercel.com/new), pick the repo, **Deploy**.
3. **Add Upstash Redis** (for the shared daily cap): in the project, **Storage →
   Marketplace → Upstash → Redis → connect**. This auto-injects
   `UPSTASH_REDIS_REST_URL` and `UPSTASH_REDIS_REST_TOKEN`.
4. **Add environment variables** (Project → Settings → Environment Variables):
   | Name | Value |
   |---|---|
   | `ANTHROPIC_API_KEY` | your key |
   | `TAVILY_API_KEY` | your key |
   | `CAS_DEMO_MODE` | `true` |
   | `CAS_DEMO_DAILY_CAP` | `25` (tune to taste) |
   | `LANGSMITH_API_KEY` / `LANGSMITH_TRACING` | optional |
5. **Redeploy** (Deployments → ⋯ → Redeploy) so the new vars take effect.

Visit your URL: the gallery loads instantly and for free; "Score live" runs the
agents, capped at `CAS_DEMO_DAILY_CAP` per day. Health check: `/api/health`.

> **Cost guardrail:** the gallery costs nothing (static JSON). Live scoring is
> ~5¢/company, bounded by the daily cap — e.g. a cap of 25 ⇒ ≤ ~$1.25/day worst
> case. The disk/Redis cache makes repeats free.

> Streamlit can't run on Vercel (it's a long-lived server). The `app/` Streamlit
> UI is for local use or [Streamlit Community Cloud](https://streamlit.io/cloud).

## Observability (LangSmith)

Set `LANGSMITH_API_KEY` and `LANGSMITH_TRACING=true`. Each run is traced under
`LANGSMITH_PROJECT` (default `cloud-alliance-score`) with the run name
`score:<company>`, so you can inspect the supervisor fan-out, every sub-agent's
search + LLM call, and the aggregator in the LangSmith UI. Tracing is wired in
one place (`config.configure_langsmith`) and is a no-op if no key is present.

## Reliability & cost controls

- **Retry + exponential backoff** on Tavily (`CAS_SEARCH_RETRIES`, default 3).
  A flaky search degrades to an empty evidence list rather than failing the run.
- **Disk cache** keyed on `(company, dimension, model)` with a 24h TTL. Re-running
  the same company during development is a cache hit that spends **zero** Tavily
  and **zero** Anthropic credits. Toggle with `CAS_CACHE_ENABLED`.

---

## Project structure

```
src/cloud_alliance_score/
├── schemas.py          # Pydantic contract: DimensionScore, CompositeScore, ScoringRequest/Response
├── config.py           # Settings (.env) + LangSmith wiring
├── llm.py              # Claude factory + structured-output binding
├── dimensions.py       # the 5 dimension specs (search queries + rubrics)
├── tools/
│   ├── search.py       # Tavily wrapper (retry/backoff, dedup) -> Evidence
│   └── cache.py        # disk cache keyed on (company, dimension, model)
├── graph/
│   ├── state.py        # graph state (additive reducer for parallel scores)
│   ├── nodes.py        # fan-out, generic sub-agent, aggregator
│   └── build.py        # ScoringDependencies + graph wiring
├── discovery/          # Discovery Mode
│   ├── generator.py    # LLM proposes candidate companies
│   ├── validator.py    # Tavily + Haiku confirm each is real (drop hallucinations)
│   ├── ranker.py       # sort scored candidates, take top N
│   ├── runtime.py      # DiscoveryDependencies + orchestration (reuses the engine)
│   ├── cache.py        # 24h whole-run cache per vendor pair
│   └── schemas.py      # Discovery request/response models
├── pipeline.py         # score_company() + discover_candidates() — public entry points
├── api.py              # FastAPI app
└── scripts_entry.py    # CLI (score-company)
app/streamlit_app.py    # Streamlit UI
scripts/                # score_cli.py, run_api.sh
tests/                  # schemas, aggregator, search, cache, graph, api, cli
```

---

## Development

```bash
make test         # pytest — fully offline (LLM + Tavily are faked)
make lint         # ruff
make typecheck    # mypy
make clean        # remove caches/artifacts
```

The test suite runs the entire graph with injected fakes, so **no API keys and
no network** are needed to validate scoring, aggregation, tiers, retry, caching,
the API, and the CLI.

### Continuous integration

`.github/workflows/ci.yml` runs **ruff + mypy + pytest** on Python 3.11 and 3.12
for every push and pull request to `main`. Because the tests are fully faked, CI
needs **no secrets**. The status badge is at the top of this README.

## License

MIT
