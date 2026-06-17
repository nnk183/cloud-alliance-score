"""Tavily wrapper: retry/backoff and result normalization."""

from __future__ import annotations

import pytest

from cloud_alliance_score.config import Settings
from cloud_alliance_score.tools.search import SearchClient, _results_to_evidence


@pytest.fixture
def fast_retry_settings() -> Settings:
    return Settings(
        _env_file=None,
        CAS_SEARCH_RETRIES=3,
        CAS_SEARCH_BACKOFF_BASE=0.0,
        CAS_SEARCH_BACKOFF_MAX=0.0,
        CAS_SEARCH_MAX_RESULTS=5,
    )


class _FlakyClient:
    def __init__(self, fail_times: int):
        self.fail_times = fail_times
        self.calls = 0

    def search(self, query, **kwargs):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise TimeoutError("transient")
        return {"results": [{"url": "https://x.com", "title": "t", "content": "good"}]}


def test_retry_recovers_after_transient_failures(fast_retry_settings):
    client = _FlakyClient(fail_times=2)
    sc = SearchClient(settings=fast_retry_settings, client=client)
    evidence = sc.search_one("query")
    assert client.calls == 3
    assert len(evidence) == 1
    assert evidence[0].url == "https://x.com"


def test_retry_exhausts_to_empty_without_raising(fast_retry_settings):
    class _Dead:
        def __init__(self):
            self.calls = 0

        def search(self, query, **kwargs):
            self.calls += 1
            raise ConnectionError("down")

    dead = _Dead()
    sc = SearchClient(settings=fast_retry_settings, client=dead)
    assert sc.search_one("query") == []
    assert dead.calls == 3  # exactly CAS_SEARCH_RETRIES attempts


def test_gather_dedupes_by_url_and_caps(fast_retry_settings):
    class _Dupe:
        def search(self, query, **kwargs):
            return {
                "results": [
                    {"url": "https://a.com", "title": "a", "content": "c1"},
                    {"url": "https://a.com", "title": "a", "content": "c1"},  # dup
                    {"url": "https://b.com", "title": "b", "content": "c2"},
                ]
            }

    sc = SearchClient(settings=fast_retry_settings, client=_Dupe())
    out = sc.gather(["q1", "q2"], max_total=10)
    urls = [e.url for e in out]
    assert urls == ["https://a.com", "https://b.com"]  # deduped across queries


def test_results_to_evidence_skips_malformed():
    raw = [
        {"url": "https://ok.com", "title": "t", "content": "snippet"},
        {"url": "", "title": "t", "content": "snippet"},        # no url -> skip
        {"url": "https://x.com", "title": "t", "content": ""},   # no snippet -> skip
        {"url": "https://y.com", "content": "uses snippet key"}, # title falls back to url
    ]
    evidence = _results_to_evidence(raw)
    assert [e.url for e in evidence] == ["https://ok.com", "https://y.com"]
    assert evidence[1].title == "https://y.com"
