"""Streamlit UI for the cloud alliance scorer.

Two modes, controlled by the CAS_DEMO_MODE setting:

* Normal (default): a single input box that scores any company live.
* Demo (CAS_DEMO_MODE=true): a curated gallery of pre-computed scorecards
  (instant, free) plus a rate-limited "score your own" box — safe to expose
  publicly without strangers burning your API credits.

Run locally:  streamlit run app/streamlit_app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make `src/` importable when running from a checkout.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import streamlit as st  # noqa: E402

from cloud_alliance_score.config import get_settings  # noqa: E402
from cloud_alliance_score.demo import (  # noqa: E402
    DailyRateLimiter,
    list_demo_companies,
    load_demo_scorecard,
)
from cloud_alliance_score.pipeline import score_company  # noqa: E402
from cloud_alliance_score.schemas import ScoringResponse, Tier  # noqa: E402

TIER_COLORS = {Tier.TIER_1: "#1a7f37", Tier.TIER_2: "#9a6700", Tier.TIER_3: "#cf222e"}

st.set_page_config(page_title="Cloud Alliance Score", page_icon="☁️", layout="centered")
settings = get_settings()


# ---------------------------------------------------------------------------
# Shared rendering
# ---------------------------------------------------------------------------


def render_scorecard(resp: ScoringResponse, *, precomputed: bool = False) -> None:
    comp = resp.composite
    color = TIER_COLORS[comp.tier]

    st.markdown(
        f"<h2 style='margin-bottom:0'>{resp.company_name} — "
        f"<span style='color:{color}'>{comp.tier.value}</span></h2>",
        unsafe_allow_html=True,
    )
    st.progress(comp.total_score / 25, text=f"Composite {comp.total_score} / 25")
    if resp.summary:
        st.info(resp.summary)

    st.subheader("Dimension breakdown")
    cols = st.columns(5)
    for col, ds in zip(cols, comp.dimension_scores):
        col.metric(ds.dimension_name, f"{ds.score}/5")

    for ds in comp.dimension_scores:
        with st.expander(f"{ds.dimension_name} — {ds.score}/5"):
            st.write(ds.reasoning)
            if ds.evidence:
                st.caption("Evidence")
                for ev in ds.evidence:
                    st.markdown(f"- [{ev.title}]({ev.url}) — {ev.snippet[:160]}…")
            else:
                st.caption("No web evidence found for this dimension.")

    tag = "pre-computed sample" if precomputed else f"model: {resp.model_used}"
    st.caption(f"{tag} · generated {resp.generated_at:%Y-%m-%d %H:%M UTC}")
    with st.expander("Raw JSON"):
        st.json(resp.model_dump(mode="json"))


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

st.title("☁️ Cloud Alliance Score")
st.caption("Score companies as cloud alliance accounts for a **LangChain × GCP** partnership.")


# ---------------------------------------------------------------------------
# Demo mode: gallery + rate-limited live scoring
# ---------------------------------------------------------------------------

if settings.demo_mode:
    limiter = DailyRateLimiter.from_settings(settings)
    st.session_state.setdefault("session_runs", 0)

    st.info(
        "🎬 **Live demo.** Browse pre-scored companies for free, or score your "
        "own — live scoring is rate-limited to protect API credits."
    )

    gallery = list_demo_companies()
    tab_gallery, tab_live = st.tabs(["📚 Gallery (instant)", "🔎 Score your own"])

    with tab_gallery:
        if not gallery:
            st.warning("No pre-computed scorecards are bundled.")
        else:
            labels = {name: slug for name, slug in gallery}
            choice = st.selectbox("Pick a company", list(labels.keys()))
            resp = load_demo_scorecard(labels[choice])
            if resp:
                render_scorecard(resp, precomputed=True)

    with tab_live:
        remaining_day = limiter.remaining()
        session_left = settings.demo_session_cap - st.session_state["session_runs"]
        st.caption(
            f"Remaining today: **{remaining_day}** · this session: **{max(0, session_left)}**"
        )
        with st.form("live_form"):
            company = st.text_input("Company name", placeholder="e.g. Spotify")
            context = st.text_input("Optional context", placeholder="e.g. music streaming")
            go = st.form_submit_button("Score live", type="primary")

        if go:
            if not company.strip():
                st.error("Please enter a company name.")
            elif session_left <= 0:
                st.warning("You've hit this session's limit. Browse the gallery instead!")
            elif not limiter.allow():
                st.warning("The daily demo limit is reached. Try the gallery, or come back tomorrow.")
            elif not (settings.anthropic_api_key and settings.tavily_api_key):
                st.error("Server is missing API keys — contact the site owner.")
            else:
                limiter.consume()
                st.session_state["session_runs"] += 1
                with st.spinner(f"Scoring {company} across 5 dimensions…"):
                    try:
                        resp = score_company(company, optional_context=context or None)
                        render_scorecard(resp)
                    except Exception as exc:  # noqa: BLE001
                        st.error(f"Scoring failed: {exc}")

    st.stop()  # demo mode handled; skip the normal single-box flow below


# ---------------------------------------------------------------------------
# Normal mode: score any company live
# ---------------------------------------------------------------------------

with st.sidebar:
    st.subheader("Configuration")
    st.write("Model:", f"`{settings.model}`")
    st.write("Anthropic key:", "✅" if settings.anthropic_api_key else "❌ missing")
    st.write("Tavily key:", "✅" if settings.tavily_api_key else "❌ missing")
    st.write(
        "LangSmith:",
        "✅ tracing" if (settings.langsmith_tracing and settings.langsmith_api_key) else "—",
    )
    st.write("Cache:", "on" if settings.cache_enabled else "off")
    st.caption("Set keys in a `.env` file (see `.env.example`).")

with st.form("score_form"):
    company = st.text_input("Company name", placeholder="e.g. Stripe")
    context = st.text_input("Optional context", placeholder="e.g. payments platform")
    submitted = st.form_submit_button("Score account", type="primary")

if submitted:
    if not company.strip():
        st.error("Please enter a company name.")
        st.stop()
    if not (settings.anthropic_api_key and settings.tavily_api_key):
        st.error("ANTHROPIC_API_KEY and TAVILY_API_KEY must be set. See the sidebar.")
        st.stop()

    with st.spinner(f"Scoring {company} across 5 dimensions…"):
        try:
            resp = score_company(company, optional_context=context or None)
        except Exception as exc:  # noqa: BLE001
            st.error(f"Scoring failed: {exc}")
            st.stop()
    render_scorecard(resp)
