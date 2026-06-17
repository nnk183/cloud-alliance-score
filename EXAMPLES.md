# Sample Scorecards

Three real scorecards produced by the scorer. Reproduce them with:

```bash
python scripts/score_cli.py "Stripe" --context "payments platform"
python scripts/score_cli.py "Capital One" --context "US consumer bank"
python scripts/score_cli.py "Sephora" --context "beauty retailer"
```

> These are **actual outputs** from a live run (model `claude-sonnet-4-6`,
> Tavily search, 2026-06-16). Because scores are produced from live web search,
> exact numbers, reasoning, and evidence will shift over time as the web changes
> — treat these as representative, not golden.

### At a glance

| Company | GCP Commit | AI Maturity | Industry Fit | LangChain | Strategic | **Total** | **Tier** |
|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| Capital One | 3 | 5 | 5 | 2 | 5 | **20/25** | **Tier 1** |
| Stripe | 1 | 5 | 5 | 2 | 4 | **17/25** | **Tier 2** |
| Sephora | 4 | 5 | 3 | 1 | 4 | **17/25** | **Tier 2** |

A nice illustration of evidence-grounded scoring beating intuition: **Sephora**
(a confirmed GCP data-platform customer) outscored **Stripe** (an AWS shop) on
GCP commit, 4 vs 1.

---

## 1. Capital One — **Tier 1** (20/25)

A technology-first, deeply AI-native bank in a top-tier regulated vertical with
executive-level AI commitment. The standout alliance target.

| Dimension | Score | Reasoning |
|---|:---:|---|
| GCP Commit Size | 3/5 | Named Google Cloud customer (presented at Google Cloud Next on its digital transformation), confirming real GCP usage. But most evidence points to a deep, primary AWS partnership, so GCP reads as secondary/supplemental. |
| AI Maturity | 5/5 | Multiple production AI/ML systems across fraud, customer experience, incident management, and financial well-being, on a dedicated cloud-based ML platform with an active applied-research program. Extensive public case studies and a detailed engineering blog mark a deeply AI-native enterprise. |
| Industry Fit | 5/5 | Regulated financial services — a top-tier GenAI vertical — with $669B in assets, 15,000 technologists, and a data-driven, technology-first strategy. Massive data intensity maps directly to fraud detection, risk modeling, personalization, and compliance automation. |
| LangChain Footprint | 2/5 | The only Capital One-specific signal is a third-party interview-prep site mentioning LangChain in a sample question — weak and indirect. No engineering blogs, GitHub repos, job posts, or talks confirm direct usage. |
| Strategic Signals | 5/5 | A dedicated Chief Scientist & Head of Enterprise AI (Prem Natarajan), a proprietary AI platform ("Intelligent Foundations and Experiences"), presence at NVIDIA GTC 2026, and active senior AI/ML hiring. Clear executive-level commitment to AI as a core business driver. |

**Recommendation:** High-conviction, land-and-expand via AI/ML engineering
relationships and regulated-industry use cases — rather than leading with GCP
co-sell, given the AWS-heavy footprint.

---

## 2. Stripe — **Tier 2** (17/25)

Elite AI maturity in a high-value fintech vertical, gated by an AWS-centric
cloud posture and a thin LangChain footprint.

| Dimension | Score | Reasoning |
|---|:---:|---|
| GCP Commit Size | 1/5 | A named AWS customer with a formal AWS case study and re:Invent keynote; no GCP customer references or case studies found. The only GCP-adjacent results are third-party integration tools — no sign Stripe itself commits to GCP. |
| AI Maturity | 5/5 | Production AI spanning years — the Railyard ML platform (fraud models since ~2017), fraud-ring similarity clustering, and autonomous agents merging ~1,000 PRs/week — plus a public Claude case study. A mature, multi-faceted ML organization. |
| Industry Fit | 5/5 | Squarely in fintech/financial infrastructure — regulated, data-intensive, with obvious GenAI value in fraud, agentic commerce, and workflow automation. $1.9T processed in 2025 and AI agents already in the stack (e.g. Decagon cutting support costs 65%). |
| LangChain Footprint | 2/5 | No direct LangChain usage by Stripe — third-party tutorials use Stripe's APIs with LangChain, and a LangChain blog merely cites Stripe's internal coding agent without confirming the framework. Clear LLM engagement (Stripe Agent Toolkit), but no first-party LangChain signal. |
| Strategic Signals | 4/5 | A dedicated Head of Data and AI plus a Chief AI Revenue Officer indicate senior, executive-level AI leadership actively shaping hiring and automation. No explicit earnings-call AI priority or disclosed major GenAI investment in evidence. |

**Recommendation:** Pursue as a **LangChain-direct** account through AI
engineering / developer-tooling channels, not a GCP co-sell — and watch for any
GCP infrastructure shift that would unlock the full alliance.

---

## 3. Sephora — **Tier 2** (17/25)

A confirmed GCP customer with production AI at scale and a fresh Chief AI Officer
mandate; limited by specialty-retail fit and zero LangChain footprint.

| Dimension | Score | Reasoning |
|---|:---:|---|
| GCP Commit Size | 4/5 | An existing Google Cloud data platform, actively being migrated/optimized (named GCP case study), signaling meaningful, ongoing GCP commitment. No multi-year deal or Vertex AI/BigQuery-specific roles cited, but real GCP spend is clear. |
| AI Maturity | 5/5 | Multiple production AI systems at global scale — virtual makeup try-on, ML personalization (6x ROI in SEA), demand forecasting, fraud prevention, and the "Store of the Future." Multiple credible public case studies; an AI-native retailer. |
| Industry Fit | 3/5 | A data-driven omnichannel beauty retailer with strong personalization/loyalty — real AI applicability. But specialty retail is neither regulated nor as data-heavy as fintech/healthcare, capping fit for the alliance's highest-value use cases. |
| LangChain Footprint | 1/5 | No evidence item references Sephora at all — all are LangChain's own blog/funding/ecosystem content. No signal whatsoever of LangChain, LangGraph, or LangSmith usage. |
| Strategic Signals | 4/5 | A newly appointed Chief AI Officer (per CDO Club) signals executive-level commitment, and Sephora is hiring a Principal GenAI Product Leader to own GenAI vision across the client journey. Concrete, senior GenAI investment. |

**Recommendation:** Medium-priority, high-potential. The Chief AI Officer mandate
and existing GCP relationship create a credible entry point — convert the GenAI
Product Leader hire into a LangChain evaluation before a competitor establishes
the foothold.

---

## 4. Discovery Mode — "LangChain × GCP" (real run)

Instead of naming a company, give Discovery a **vendor pair** and it finds the
candidates for you: it generates company names, validates each is real (via
Tavily), scores the validated ones with the engine (on **Claude Haiku**, for
cheap batch scoring), and ranks them.

```bash
# CLI-equivalent via Python
python -c "from cloud_alliance_score import discover_candidates as d; print(d('LangChain × GCP', 5))"
# or the API
curl -s localhost:8000/discover -H 'Content-Type: application/json' \
  -d '{"vendor_pair": "LangChain × GCP", "n_candidates": 5}'
```

A real run (generated 10 → validated 10 → scored 5, ~37s on Haiku):

| Rank | Company | GCP | AI | Industry | LangChain | Strategic | **Total** | **Tier** |
|:--:|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| **1** | Databricks | 5 | 5 | 5 | 4 | 4 | **23/25** | **Tier 1** |
| **2** | Shopify | 5 | 5 | 4 | 3 | 5 | **22/25** | **Tier 1** |
| **3** | Stripe | 1 | 5 | 5 | 4 | 4 | **19/25** | **Tier 2** |
| **4** | Figma | — | — | — | — | — | **18/25** | **Tier 2** |
| **5** | Notion | — | — | — | — | — | **12/25** | **Tier 2** |

**#1 Databricks (23/25):** *"Perfect marks across GCP commitment, AI maturity,
and industry fit — deep native integrations with Google Cloud, production-grade
MLOps, and Fortune 500 penetration."*

**#2 Shopify (22/25):** *"Exceptional GCP commitment (5/5), AI maturity (5/5),
and executive-level AI mandate (5/5) — an AI-native customer processing $292B
annually across commerce infrastructure."*

> Note: scores come from live search and the (cheaper) Haiku model, so they
> differ slightly from the Sonnet single-company runs above — e.g. Stripe here
> is 19 vs 17. Both correctly flag Stripe's weak GCP footprint (1/5, an AWS shop).
> Re-running the same vendor pair within 24h returns the cached result instantly.

---

### Reading a scorecard

- **Composite** is the simple sum of the five 1–5 dimension scores (max 25).
- **Tier** is derived: 20–25 → Tier 1, 12–19 → Tier 2, < 12 → Tier 3.
- **Every dimension carries an evidence trail** (the search snippets the
  sub-agent used) so the reasoning is auditable — inspect it in the CLI
  (`--json`), the API response, or the Streamlit "Evidence" expanders.
