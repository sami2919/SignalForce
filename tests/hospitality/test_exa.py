from datetime import date
from unittest.mock import patch

import pytest

from scripts.hospitality.budget import BudgetExceeded, CallBudget
from scripts.hospitality.discover.exa import ExaClient
from scripts.hospitality.models import ExaResult

RAW = {
    "results": [
        {
            "url": "https://eater.com/a",
            "title": "New spot opens",
            "publishedDate": "2026-10-01T00:00:00.000Z",
            "text": "Body",
        },
        {"url": "https://b.com", "title": None, "publishedDate": None},
        {"title": "no url"},
    ]
}


def _call(client: ExaClient, fn: str, *args: object, **kwargs: object):
    with patch.object(client._session, "request") as req:
        req.return_value.status_code = 200
        req.return_value.json.return_value = RAW
        out = getattr(client, fn)(*args, **kwargs)
    return out, req


def test_search_body_fields_and_header() -> None:
    client = ExaClient("k", CallBudget("exa", 5))
    _, req = _call(
        client,
        "search",
        "nyc restaurant group",
        num_results=5,
        start_published_date=date(2026, 1, 2),
    )
    assert req.call_args.args[0] == "POST"
    assert req.call_args.args[1] == "https://api.exa.ai/search"
    body = req.call_args.kwargs["json"]
    assert body == {
        "query": "nyc restaurant group",
        "numResults": 5,
        "startPublishedDate": "2026-01-02",
        "contents": {"text": True},
    }
    assert client._session.headers["x-api-key"] == "k"


def test_search_omits_optional_fields() -> None:
    client = ExaClient("k", CallBudget("exa", 5))
    _, req = _call(client, "search", "q", include_text=False)
    assert req.call_args.kwargs["json"] == {"query": "q", "numResults": 10}


def test_search_parses_results_and_skips_urlless() -> None:
    client = ExaClient("k", CallBudget("exa", 5))
    out, _ = _call(client, "search", "q")
    assert out == [
        ExaResult(
            url="https://eater.com/a",
            title="New spot opens",
            published_date=date(2026, 10, 1),
            text="Body",
        ),
        ExaResult(url="https://b.com", title="", published_date=None, text=None),
    ]


def test_find_similar_body() -> None:
    client = ExaClient("k", CallBudget("exa", 5))
    _, req = _call(client, "find_similar", "https://x.com/page", num_results=3)
    assert req.call_args.args[1] == "https://api.exa.ai/findSimilar"
    assert req.call_args.kwargs["json"] == {
        "url": "https://x.com/page",
        "numResults": 3,
        "excludeSourceDomain": True,
    }


def test_budget_hard_stop_before_network() -> None:
    client = ExaClient("k", CallBudget("exa", 1))
    with patch.object(client._session, "request") as req:
        req.return_value.status_code = 200
        req.return_value.json.return_value = RAW
        client.search("a")
        with pytest.raises(BudgetExceeded):
            client.find_similar("https://x.com")
        with pytest.raises(BudgetExceeded):
            client.search("b")
    assert req.call_count == 1


def test_missing_key_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EXA_API_KEY", raising=False)
    with pytest.raises(ValueError, match="EXA_API_KEY"):
        ExaClient.from_env(CallBudget("exa", 1))
    with pytest.raises(ValueError, match="EXA_API_KEY"):
        ExaClient("", CallBudget("exa", 1))
