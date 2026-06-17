"""Discovery Mode: generator, validator, ranker, orchestration, cache, API."""

from __future__ import annotations

import pytest

from cloud_alliance_score.discovery.cache import DiscoveryCache
from cloud_alliance_score.discovery.generator import generate_candidates
from cloud_alliance_score.discovery.ranker import rank_candidates
from cloud_alliance_score.discovery.runtime import DiscoveryDependencies, run_discovery
from cloud_alliance_score.discovery.schemas import (
    Candidate,
    CandidateIdea,
    CandidateList,
    ExistenceCheck,
)
from cloud_alliance_score.discovery.validator import validate_candidates
from cloud_alliance_score.schemas import Dimension, DimensionScore, ScoringResponse


def _scorecard(name, vals):
    ds = [DimensionScore(dimension=d, score=s, reasoning="a. b.") for d, s in zip(Dimension, vals)]
    return ScoringResponse.build(name, ds, model_used="claude-haiku-4-5")


# --- generator --------------------------------------------------------------


class _GenLLM:
    def invoke(self, messages):
        return CandidateList(
            candidates=[CandidateIdea(name="Stripe", industry="Fintech", rationale="r")]
        )


def test_generator_returns_candidate_list():
    out = generate_candidates("LangChain × GCP", 1, _GenLLM())
    assert [c.name for c in out.candidates] == ["Stripe"]


# --- validator --------------------------------------------------------------


class _Search:
    def search_one(self, query, max_results=3):
        from cloud_alliance_score.schemas import Evidence

        if "Acme" in query:  # the hallucination has no evidence
            return []
        return [Evidence(title="T", url="https://x.com", snippet="real company")]


class _Confirm:
    def invoke(self, messages):
        name = messages[1].content
        return ExistenceCheck(exists=True, canonical_name="Stripe, Inc." if "Stripe" in name else "Sephora", industry="X")


def test_validator_drops_hallucinations():
    ideas = [
        CandidateIdea(name="Stripe"),
        CandidateIdea(name="Acme Fakeco"),
        CandidateIdea(name="Sephora"),
    ]
    cands = validate_candidates(ideas, _Search(), _Confirm(), concurrency=2)
    valid = {c.name for c in cands if c.validated}
    invalid = {c.name for c in cands if not c.validated}
    assert "Acme Fakeco" in invalid
    assert valid == {"Stripe, Inc.", "Sephora"}  # canonical names applied


# --- ranker -----------------------------------------------------------------


def test_ranker_orders_by_composite_and_takes_top_n():
    cards = [_scorecard("Stripe", [1, 5, 5, 2, 4]),
             _scorecard("Capital One", [3, 5, 5, 2, 5]),
             _scorecard("Sephora", [2, 5, 3, 1, 4])]
    ranked = rank_candidates(cards, 2)
    assert [r.scorecard.company_name for r in ranked] == ["Capital One", "Stripe"]
    assert [r.rank for r in ranked] == [1, 2]
    assert ranked[0].composite_score == 20
    assert ranked[0].tier.value == "Tier 1"


# --- orchestration + cache --------------------------------------------------


@pytest.fixture
def fake_deps(tmp_path):
    calls = {"gen": 0, "val": 0, "score": 0}

    def gen(vp, count):
        calls["gen"] += 1
        return [CandidateIdea(name=n, industry="X") for n in
                ["Stripe", "Acme Fake", "Capital One", "Sephora", "Notion"]]

    def val(ideas):
        calls["val"] += 1
        return [Candidate(name=i.name, validated=(i.name != "Acme Fake")) for i in ideas]

    scores = {"Stripe": [1, 5, 5, 2, 4], "Capital One": [3, 5, 5, 2, 5],
              "Sephora": [2, 5, 3, 1, 4], "Notion": [2, 4, 3, 2, 3]}

    def score(c):
        calls["score"] += 1
        return _scorecard(c.name, scores[c.name])

    cache = DiscoveryCache(str(tmp_path), ttl_seconds=999, enabled=True, model="haiku")
    deps = DiscoveryDependencies(
        generate=gen, validate=val, score_one=score, model_name="claude-haiku-4-5",
        generate_count=30, max_score=3, concurrency=2, cache=cache,
    )
    return deps, calls


def test_run_discovery_caps_scoring_and_ranks(fake_deps):
    deps, calls = fake_deps
    resp = run_discovery("LangChain × GCP", 2, deps)
    assert resp.generated == 5
    assert resp.validated == 4          # Acme Fake dropped
    assert resp.scored == 3             # capped by max_score=3
    assert len(resp.results) == 2       # top N
    assert resp.results[0].scorecard.company_name == "Capital One"
    assert resp.cached is False


def test_run_discovery_second_call_is_cached(fake_deps):
    deps, calls = fake_deps
    run_discovery("LangChain × GCP", 2, deps)
    before = dict(calls)
    resp2 = run_discovery("LangChain × GCP", 2, deps)
    assert resp2.cached is True
    assert calls == before              # no regeneration / rescoring


def test_score_failure_is_skipped_not_fatal(tmp_path):
    def gen(vp, count):
        return [CandidateIdea(name="Good"), CandidateIdea(name="Bad")]

    def val(ideas):
        return [Candidate(name=i.name, validated=True) for i in ideas]

    def score(c):
        if c.name == "Bad":
            raise RuntimeError("boom")
        return _scorecard(c.name, [3, 3, 3, 3, 3])

    deps = DiscoveryDependencies(
        generate=gen, validate=val, score_one=score, model_name="m",
        generate_count=30, max_score=10, concurrency=2, cache=None,
    )
    resp = run_discovery("X × Y", 5, deps)
    assert resp.validated == 2 and resp.scored == 1  # Bad skipped, run survives
    assert resp.results[0].scorecard.company_name == "Good"
