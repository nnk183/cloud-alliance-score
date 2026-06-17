"""Streamlit UI for the cloud alliance scorer.

Tabs:
  * Single Company Score — score one company live.
  * Discovery Mode — surface + rank candidate accounts for a vendor pair.

Demo mode (CAS_DEMO_MODE=true) adds a free pre-computed gallery and rate-limits
the live actions so a public deployment can't burn API credits.

Run locally:  streamlit run app/streamlit_app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import streamlit as st  # noqa: E402

from cloud_alliance_score.config import get_settings  # noqa: E402
from cloud_alliance_score.demo import (  # noqa: E402
    DailyRateLimiter,
    list_demo_companies,
    load_demo_scorecard,
)
from cloud_alliance_score.pipeline import discover_candidates, score_company  # noqa: E402
from cloud_alliance_score.schemas import ScoringResponse, Tier  # noqa: E402

TIER_COLORS = {Tier.TIER_1: "#1a7f37", Tier.TIER_2: "#9a6700", Tier.TIER_3: "#cf222e"}

st.set_page_config(page_title="Cloud Alliance Score", page_icon="☁️", layout="centered")
settings = get_settings()


# ---------------------------------------------------------------------------
# Shared rendering
# ---------------------------------------------------------------------------


def _tier_badge(tier: Tier) -> str:
    return f"<span style='color:{TIER_COLORS[tier]};font-weight:700'>{tier.value}</span>"


def render_scorecard(resp: ScoringResponse, *, precomputed: bool = False) -> None:
    comp = resp.composite
    st.markdown(
        f"<h3 style='margin-bottom:0'>{resp.company_name} — {_tier_badge(comp.tier)}</h3>",
        unsafe_allow_html=True,
    )
    st.progress(comp.total_score / 25, text=f"Composite {comp.total_score} / 25")
    if resp.summary:
        st.info(resp.summary)

    cols = st.columns(5)
    for col, ds in zip(cols, comp.dimension_scores):
        col.metric(ds.dimension_name, f"{ds.score}/5")

    for ds in comp.dimension_scores:
        with st.expander(f"{ds.dimension_name} — {ds.score}/5"):
            st.write(ds.reasoning)
            for ev in ds.evidence:
                st.markdown(f"- [{ev.title}]({ev.url}) — {ev.snippet[:160]}…")

    tag = "pre-computed sample" if precomputed else f"model: {resp.model_used}"
    st.caption(f"{tag} · generated {resp.generated_at:%Y-%m-%d %H:%M UTC}")


def render_discovery(resp) -> None:
    st.markdown(f"### Top accounts for **{resp.vendor_pair}**")
    st.caption(
        f"Generated {resp.generated} · validated {resp.validated} · scored {resp.scored}"
        f" · model {resp.model_used}" + (" · (cached)" if resp.cached else "")
    )
    for sc in resp.results:
        comp = sc.scorecard.composite
        st.markdown(
            f"**#{sc.rank}. {sc.scorecard.company_name}** — "
            f"{comp.total_score}/25 · {_tier_badge(comp.tier)}",
            unsafe_allow_html=True,
        )
        st.progress(comp.total_score / 25)
        with st.expander("Full scorecard"):
            render_scorecard(sc.scorecard)


# ---------------------------------------------------------------------------
# Action panels (shared by normal + demo modes)
# ---------------------------------------------------------------------------


def single_company_panel(*, gated: bool) -> None:
    with st.form("score_form"):
        company = st.text_input("Company name", placeholder="e.g. Stripe")
        context = st.text_input("Optional context", placeholder="e.g. payments platform")
        submitted = st.form_submit_button("Score account", type="primary")
    if not submitted:
        return
    if not company.strip():
        st.error("Please enter a company name.")
        return
    if not _keys_ready():
        return
    if gated and not _consume_quota():
        return
    with st.spinner(f"Scoring {company} across 5 dimensions…"):
        try:
            render_scorecard(score_company(company, optional_context=context or None))
        except Exception as exc:  # noqa: BLE001
            st.error(f"Scoring failed: {exc}")


def discovery_panel(*, gated: bool) -> None:
    st.caption(
        "Generate candidate companies for a partnership, validate they're real, "
        "then score and rank them. Takes ~1–2 min."
    )
    with st.form("discover_form"):
        vendor_pair = st.text_input("Vendor pair", value="LangChain × GCP")
        n = st.slider("How many to return", 1, settings.discovery_max_candidates, 5)
        submitted = st.form_submit_button("Discover candidates", type="primary")
    if not submitted:
        return
    if not vendor_pair.strip():
        st.error("Please enter a vendor pair.")
        return
    if not _keys_ready():
        return
    if gated and not _consume_quota():
        return
    with st.spinner(f"Discovering accounts for {vendor_pair}… this can take 1–2 min."):
        try:
            render_discovery(discover_candidates(vendor_pair, n_candidates=n))
        except Exception as exc:  # noqa: BLE001
            st.error(f"Discovery failed: {exc}")


def _keys_ready() -> bool:
    if settings.anthropic_api_key and settings.tavily_api_key:
        return True
    st.error("ANTHROPIC_API_KEY and TAVILY_API_KEY must be set on the server.")
    return False


def _consume_quota() -> bool:
    """Demo-mode guard: session cap + daily cap. Returns True if allowed."""
    st.session_state.setdefault("runs", 0)
    if st.session_state["runs"] >= settings.demo_session_cap:
        st.warning("You've hit this session's limit. Try the gallery instead!")
        return False
    limiter = DailyRateLimiter.from_settings(settings)
    if not limiter.consume():
        st.warning("The daily demo limit is reached. Come back tomorrow!")
        return False
    st.session_state["runs"] += 1
    return True


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

st.title("☁️ Cloud Alliance Score")
st.caption("Score & discover cloud alliance accounts for a **LangChain × GCP** partnership.")

if settings.demo_mode:
    st.info(
        "🎬 **Live demo.** Browse pre-scored companies free, or run live "
        "scoring/discovery — capped to protect API credits."
    )
    tab_gallery, tab_score, tab_discover = st.tabs(
        ["📚 Gallery (instant)", "🔎 Single Company", "🧭 Discovery Mode"]
    )
    with tab_gallery:
        gallery = list_demo_companies()
        if gallery:
            labels = {name: slug for name, slug in gallery}
            choice = st.selectbox("Pick a company", list(labels.keys()))
            resp = load_demo_scorecard(labels[choice])
            if resp:
                render_scorecard(resp, precomputed=True)
        else:
            st.warning("No pre-computed scorecards bundled.")
    with tab_score:
        single_company_panel(gated=True)
    with tab_discover:
        discovery_panel(gated=True)
else:
    with st.sidebar:
        st.subheader("Configuration")
        st.write("Model:", f"`{settings.model}`")
        st.write("Discovery model:", f"`{settings.discovery_model}`")
        st.write("Anthropic key:", "✅" if settings.anthropic_api_key else "❌ missing")
        st.write("Tavily key:", "✅" if settings.tavily_api_key else "❌ missing")
        st.write(
            "LangSmith:",
            "✅ tracing" if (settings.langsmith_tracing and settings.langsmith_api_key) else "—",
        )
        st.caption("Set keys in a `.env` file (see `.env.example`).")

    tab_score, tab_discover = st.tabs(["🔎 Single Company Score", "🧭 Discovery Mode"])
    with tab_score:
        single_company_panel(gated=False)
    with tab_discover:
        discovery_panel(gated=False)
