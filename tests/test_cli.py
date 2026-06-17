"""CLI entry point: formatting, JSON mode, and exit codes."""

from __future__ import annotations

import json

from cloud_alliance_score import scripts_entry
from cloud_alliance_score.schemas import Dimension, DimensionScore, ScoringResponse


def _fake_response(company, optional_context=None) -> ScoringResponse:
    scores = [
        DimensionScore(dimension=d, score=s, reasoning="a. b.")
        for d, s in zip(Dimension, [5, 5, 4, 4, 3])
    ]
    return ScoringResponse.build(
        company, scores, summary="fit summary", model_used="test", optional_context=optional_context
    )


def test_cli_human_output(monkeypatch, capsys):
    monkeypatch.setattr(scripts_entry, "score_company", _fake_response)
    code = scripts_entry.main(["Stripe", "--context", "payments"])
    out = capsys.readouterr().out
    assert code == 0
    assert "Stripe" in out
    assert "COMPOSITE: 21/25" in out
    assert "Tier 1" in out
    assert "GCP Commit Size" in out


def test_cli_json_output(monkeypatch, capsys):
    monkeypatch.setattr(scripts_entry, "score_company", _fake_response)
    code = scripts_entry.main(["Stripe", "--json"])
    out = capsys.readouterr().out
    assert code == 0
    data = json.loads(out)
    assert data["composite"]["total_score"] == 21
    assert data["company_name"] == "Stripe"


def test_cli_config_error_exit_code(monkeypatch, capsys):
    def _boom(company, optional_context=None):
        raise RuntimeError("TAVILY_API_KEY is not set.")

    monkeypatch.setattr(scripts_entry, "score_company", _boom)
    code = scripts_entry.main(["Stripe"])
    assert code == 2
    assert "TAVILY_API_KEY" in capsys.readouterr().err


def test_cli_runtime_failure_exit_code(monkeypatch, capsys):
    def _boom(company, optional_context=None):
        raise ValueError("kaboom")

    monkeypatch.setattr(scripts_entry, "score_company", _boom)
    code = scripts_entry.main(["Stripe"])
    assert code == 1
