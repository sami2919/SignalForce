"""Exa search and findSimilar client.

Request field names (`query`, `numResults`, `startPublishedDate`, `contents.text`, `url`,
`excludeSourceDomain`, header `x-api-key`) follow Exa's public API reference as recalled from
memory. This offline environment could not re-check them (no network, no EXA_API_KEY):
verify against https://docs.exa.ai before the first live run (doc date: NOT verified,
2026-11-16). A wrong field name silently returns unfiltered results rather than an error.
One search = one billable call; `CallBudget` counts 1:1 and is spent before the HTTP call.
"""

import logging
import os
from datetime import date

from scripts.api_client import BaseAPIClient
from scripts.hospitality.budget import CallBudget
from scripts.hospitality.models import ExaResult

logger = logging.getLogger(__name__)

BASE_URL = "https://api.exa.ai"


class ExaClient(BaseAPIClient):
    def __init__(self, api_key: str, budget: CallBudget) -> None:
        if not api_key:
            raise ValueError("EXA_API_KEY is not set; export it before running discovery")
        super().__init__(BASE_URL, auth_headers={"x-api-key": api_key})
        self.budget = budget

    @classmethod
    def from_env(cls, budget: CallBudget) -> "ExaClient":
        """Build a client from EXA_API_KEY, failing fast with a clear message if absent."""
        return cls(os.environ.get("EXA_API_KEY", ""), budget)

    def _call(self, endpoint: str, body: dict) -> list[ExaResult]:
        self.budget.spend()
        raw = self.post(endpoint, json_data=body)
        return _parse_results(raw)

    def search(
        self,
        query: str,
        *,
        num_results: int = 10,
        start_published_date: date | None = None,
        include_text: bool = True,
    ) -> list[ExaResult]:
        body: dict = {"query": query, "numResults": num_results}
        if start_published_date is not None:
            body["startPublishedDate"] = start_published_date.isoformat()
        if include_text:
            body["contents"] = {"text": True}
        return self._call("search", body)

    def find_similar(
        self, url: str, *, num_results: int = 10, exclude_source_domain: bool = True
    ) -> list[ExaResult]:
        body = {"url": url, "numResults": num_results, "excludeSourceDomain": exclude_source_domain}
        return self._call("findSimilar", body)


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        logger.warning("Unparseable Exa publishedDate: %r", value)
        return None


def _parse_results(raw: dict) -> list[ExaResult]:
    out: list[ExaResult] = []
    for r in raw.get("results", []):
        if not r.get("url"):
            logger.warning("Skipping Exa result without url: %s", r.get("title"))
            continue
        out.append(
            ExaResult(
                url=r["url"],
                title=r.get("title") or "",
                published_date=_parse_date(r.get("publishedDate")),
                text=r.get("text"),
            )
        )
    return out
