"""Search-based website provider: candidates, filtering, deterministic verification, budgets."""

from datetime import date
from unittest.mock import patch

import pytest

from scripts.firecrawl_client import FirecrawlClient
from scripts.hospitality.budget import BudgetExceeded, CallBudget
from scripts.hospitality.config import WebsitesConfig, load_config
from scripts.hospitality.discover.exa import ExaClient
from scripts.hospitality.stack.website_search import (
    FetchedPage,
    WebsiteFinder,
    iter_search_lookups,
    page_shows_address,
    page_shows_phone,
)
from tests.hospitality.factories import make_venue

TODAY = date(2026, 11, 16)
PHONE = "2125550100"
PHONE_PAGE = '<html><body><a href="tel:+1-212-555-0100">Call us</a></body></html>'
ADDRESS_PAGE = (
    "<html><body><p>Find us at 123 West 27th Street, New York, NY 10001</p></body></html>"
)
NAME_ONLY = "<html><body><h1>Oriana</h1><p>Welcome to Oriana. Great food.</p></body></html>"


def venue(**kw: object):
    base = {"name": "Oriana", "address": "123 W 27TH ST", "zip_code": "10001", "camis": "111"}
    return make_venue("v:1", **{**base, **kw})


def cfg(**kw: object) -> WebsitesConfig:
    return load_config().websites.model_copy(update=kw)


class FakeFetch:
    """Maps url -> body (200), 'robots', 'fail'; records every url requested."""

    def __init__(self, pages: dict[str, str]) -> None:
        self.pages = pages
        self.requested: list[str] = []

    def __call__(self, urls):  # type: ignore[no-untyped-def]
        out = {}
        for u in urls:
            self.requested.append(u)
            v = self.pages.get(u, "fail")
            if v == "robots":
                out[u] = FetchedPage(url=u, status="robots", body=None)
            elif v == "fail":
                out[u] = FetchedPage(url=u, status="failed", body=None)
            else:
                out[u] = FetchedPage(url=u, status="ok", body=v)
        return out


def exa_with(urls: list[str], limit: int = 5) -> ExaClient:
    client = ExaClient("k", CallBudget("exa", limit))
    raw = {"results": [{"url": u, "title": "t"} for u in urls]}
    client._exa_post = patch.object(client, "post", return_value=raw).start()  # type: ignore[attr-defined]
    return client


def fc_with(urls: list[str], limit: int = 5) -> tuple[FirecrawlClient, CallBudget]:
    client = FirecrawlClient("k")
    raw = {"data": [{"url": u, "title": "t"} for u in urls]}
    client._fc_post = patch.object(client, "post", return_value=raw).start()  # type: ignore[attr-defined]
    return client, CallBudget("firecrawl", limit)


@pytest.fixture(autouse=True)
def _stop_patches():  # type: ignore[no-untyped-def]
    yield
    patch.stopall()


def finder(fetch, exa=None, fc=None, fc_budget=None, phones=None, **cfg_kw):  # type: ignore[no-untyped-def]
    return WebsiteFinder(
        cfg(**cfg_kw),
        exa=exa,
        firecrawl=fc,
        firecrawl_budget=fc_budget,
        fetch=fetch,
        phones={"111": PHONE} if phones is None else phones,
    )


# --- verification primitives -------------------------------------------------------------


def test_phone_matches_digits_in_any_format_and_tel_links() -> None:
    assert page_shows_phone("<p>(212) 555-0100</p>", PHONE)
    assert page_shows_phone(PHONE_PAGE, PHONE)
    assert page_shows_phone("<p>+1 212.555.0100</p>", PHONE)
    assert not page_shows_phone("<p>(212) 555-0199</p>", PHONE)
    assert not page_shows_phone("<p>id 12125550100123</p>", PHONE)  # inside a longer number
    assert not page_shows_phone("<p>(212) 555-0100</p>", "")  # no phone on record: never matches
    assert not page_shows_phone("<p>(212) 555-0100</p>", "555")  # too short to mean anything


def test_address_needs_house_number_street_and_a_locality() -> None:
    v = venue()
    assert page_shows_address(ADDRESS_PAGE, v.address, v.zip_code, cfg())
    assert page_shows_address("<p>123 W. 27th St., Suite 4, Brooklyn</p>", v.address, "", cfg())
    # Right street, wrong number; right number, other street; no locality near it.
    assert not page_shows_address(
        "<p>125 West 27th Street, New York</p>", v.address, "10001", cfg()
    )
    assert not page_shows_address(
        "<p>123 West 28th Street, New York</p>", v.address, "10001", cfg()
    )
    assert not page_shows_address(
        "<p>123 West 27th Street</p>" + "word " * 30, v.address, "", cfg()
    )
    assert not page_shows_address("<p>nothing</p>", "", "10001", cfg())


def test_address_read_from_json_ld() -> None:
    body = (
        '<script type="application/ld+json">{"address": {"streetAddress": "123 W 27th St", '
        '"addressLocality": "New York", "postalCode": "10001"}}</script>'
    )
    assert page_shows_address(body, "123 W 27TH ST", "10001", cfg())


# --- the rules ---------------------------------------------------------------------------


def test_phone_verified_site_is_accepted_with_evidence() -> None:
    fetch = FakeFetch({"https://www.oriana.com/": PHONE_PAGE})
    out = finder(fetch, exa=exa_with(["https://www.oriana.com/menu"])).find(venue(), TODAY)
    assert out.website == "https://www.oriana.com/"
    assert out.verified_by == "phone" and out.evidence_url == "https://www.oriana.com/"
    assert out.source == "search" and out.miss_reason is None


def test_address_verified_site_is_accepted_for_a_venue_with_no_dohmh_record() -> None:
    fetch = FakeFetch({"https://oriana.com/": ADDRESS_PAGE})
    v = venue(camis=None)  # not yet open: no inspection, so no phone
    out = finder(fetch, exa=exa_with(["https://oriana.com"])).find(v, TODAY)
    assert (out.website, out.verified_by) == ("https://oriana.com/", "address")


def test_address_verification_is_used_when_the_phone_is_not_on_the_page() -> None:
    fetch = FakeFetch({"https://oriana.com/": ADDRESS_PAGE})
    out = finder(fetch, exa=exa_with(["https://oriana.com"])).find(venue(), TODAY)
    assert out.verified_by == "address"


def test_a_name_match_alone_is_rejected() -> None:
    fetch = FakeFetch({"https://oriana.com/": NAME_ONLY})
    out = finder(fetch, exa=exa_with(["https://oriana.com"])).find(venue(), TODAY)
    assert out.website is None and out.miss_reason == "none_verified"


def test_verification_reads_likely_extra_pages_up_to_the_cap() -> None:
    fetch = FakeFetch({"https://oriana.com/": NAME_ONLY, "https://oriana.com/contact": PHONE_PAGE})
    out = finder(fetch, exa=exa_with(["https://oriana.com"])).find(venue(), TODAY)
    assert out.verified_by == "phone" and out.evidence_url == "https://oriana.com/contact"
    fetch2 = FakeFetch({"https://oriana.com/": NAME_ONLY})
    finder(fetch2, exa=exa_with(["https://oriana.com"]), max_verify_pages=2).find(venue(), TODAY)
    assert fetch2.requested == [
        "https://oriana.com/",
        "https://oriana.com/contact",
        "https://oriana.com/contact-us",
    ]


def test_aggregator_domains_are_filtered_and_never_fetched() -> None:
    fetch = FakeFetch({"https://oriana.com/": PHONE_PAGE})
    urls = ["https://www.yelp.com/biz/oriana", "https://resy.com/cities/ny/oriana",
            "https://www.nyc.gov/x", "https://oriana.com"]  # fmt: skip
    out = finder(fetch, exa=exa_with(urls)).find(venue(), TODAY)
    assert out.website == "https://oriana.com/"
    assert all("yelp" not in u and "resy" not in u and "nyc.gov" not in u for u in fetch.requested)


def test_all_filtered_is_a_distinct_miss() -> None:
    fetch = FakeFetch({})
    out = finder(fetch, exa=exa_with(["https://yelp.com/biz/o", "https://tripadvisor.com/o"])).find(
        venue(), TODAY
    )
    assert out.website is None and out.miss_reason == "all_filtered" and fetch.requested == []


def test_linkedin_is_never_fetched_even_if_the_config_list_omits_it() -> None:
    fetch = FakeFetch({"https://oriana.com/": PHONE_PAGE})
    urls = ["https://www.linkedin.com/company/oriana", "https://oriana.com"]
    out = finder(fetch, exa=exa_with(urls), excluded_domains=("yelp.com",)).find(venue(), TODAY)
    assert out.website == "https://oriana.com/"
    assert not any("linkedin" in u for u in fetch.requested)


def test_loyalist_for_pages_are_never_fetched() -> None:
    fetch = FakeFetch({"https://oriana.com/": PHONE_PAGE})
    urls = ["https://www.loyalist.com/for/oriana", "https://oriana.com"]
    out = finder(fetch, exa=exa_with(urls), excluded_domains=("yelp.com",)).find(venue(), TODAY)
    assert out.website == "https://oriana.com/"
    # the /for/ result is dropped outright, not reduced to the vendor's home page
    assert not any("loyalist.com" in u for u in fetch.requested)


def test_no_candidates_is_a_distinct_miss() -> None:
    out = finder(FakeFetch({}), exa=exa_with([])).find(venue(), TODAY)
    assert out.website is None and out.miss_reason == "no_candidates"


def test_robots_blocked_is_a_miss_and_is_not_retried_through_firecrawl() -> None:
    fc, budget = fc_with([])
    fetch = FakeFetch({"https://oriana.com/": "robots"})
    f = finder(fetch, exa=exa_with(["https://oriana.com"]), fc=fc, fc_budget=budget)
    with patch.object(fc, "scrape") as scrape:
        out = f.find(venue(), TODAY)
    assert out.miss_reason == "robots_blocked" and not scrape.called
    assert fetch.requested == ["https://oriana.com/"]  # extra pages of a blocked host skipped


def test_fetch_failure_is_a_distinct_miss() -> None:
    out = finder(FakeFetch({}), exa=exa_with(["https://oriana.com"])).find(venue(), TODAY)
    assert out.miss_reason == "fetch_failed"


def test_two_address_verified_domains_are_ambiguous_and_take_none() -> None:
    fetch = FakeFetch({"https://a.com/": ADDRESS_PAGE, "https://b.com/": ADDRESS_PAGE})
    out = finder(fetch, exa=exa_with(["https://a.com", "https://b.com"])).find(venue(), TODAY)
    assert out.website is None and out.miss_reason == "ambiguous"


def test_phone_verified_beats_address_verified() -> None:
    fetch = FakeFetch({"https://a.com/": ADDRESS_PAGE, "https://b.com/": PHONE_PAGE})
    out = finder(fetch, exa=exa_with(["https://a.com", "https://b.com"])).find(venue(), TODAY)
    assert (out.website, out.verified_by) == ("https://b.com/", "phone")


def test_two_phone_verified_domains_are_ambiguous() -> None:
    fetch = FakeFetch({"https://a.com/": PHONE_PAGE, "https://b.com/": PHONE_PAGE})
    out = finder(fetch, exa=exa_with(["https://a.com", "https://b.com"])).find(venue(), TODAY)
    assert out.website is None and out.miss_reason == "ambiguous"


def test_same_domain_twice_is_one_candidate() -> None:
    fetch = FakeFetch({"https://a.com/": ADDRESS_PAGE})
    urls = ["https://a.com/menu", "https://www.a.com/contact"]
    out = finder(fetch, exa=exa_with(urls)).find(venue(), TODAY)
    assert out.verified_by == "address"


# --- budgets and fallback ----------------------------------------------------------------


def test_exa_budget_hard_stops_before_the_call_over_the_limit() -> None:
    exa = exa_with([], limit=1)
    f = finder(FakeFetch({}), exa=exa)
    f.find(venue(), TODAY)
    with pytest.raises(BudgetExceeded):
        f.find(venue(), TODAY)
    assert exa._exa_post.call_count == 1  # type: ignore[attr-defined]


def test_firecrawl_budget_hard_stops_before_the_call_over_the_limit() -> None:
    fc, budget = fc_with([], limit=1)
    f = finder(FakeFetch({}), fc=fc, fc_budget=budget)
    f.find(venue(), TODAY)
    with pytest.raises(BudgetExceeded):
        f.find(venue(), TODAY)
    assert fc._fc_post.call_count == 1  # type: ignore[attr-defined]


def test_exa_exhausted_falls_back_to_firecrawl_search() -> None:
    exa = exa_with(["https://wrong.com"], limit=0)
    fc, budget = fc_with(["https://oriana.com"])
    fetch = FakeFetch({"https://oriana.com/": PHONE_PAGE})
    out = finder(fetch, exa=exa, fc=fc, fc_budget=budget).find(venue(), TODAY)
    assert out.website == "https://oriana.com/"
    assert not exa._exa_post.called and budget.used == 1  # type: ignore[attr-defined]


def test_exa_with_nothing_usable_falls_back_to_firecrawl_search() -> None:
    exa = exa_with(["https://yelp.com/biz/o"])
    fc, budget = fc_with(["https://oriana.com"])
    fetch = FakeFetch({"https://oriana.com/": PHONE_PAGE})
    out = finder(fetch, exa=exa, fc=fc, fc_budget=budget).find(venue(), TODAY)
    assert out.verified_by == "phone" and exa.budget.used == 1 and budget.used == 1


def test_exa_hit_does_not_spend_firecrawl() -> None:
    exa = exa_with(["https://oriana.com"])
    fc, budget = fc_with(["https://other.com"])
    finder(FakeFetch({"https://oriana.com/": PHONE_PAGE}), exa=exa, fc=fc, fc_budget=budget).find(
        venue(), TODAY
    )
    assert budget.used == 0


def test_a_provider_error_is_logged_and_falls_back_then_switches_off(caplog) -> None:  # type: ignore[no-untyped-def]
    exa = ExaClient("k", CallBudget("exa", 10))
    fc, budget = fc_with(["https://oriana.com"])
    fetch = FakeFetch({"https://oriana.com/": PHONE_PAGE})
    f = finder(fetch, exa=exa, fc=fc, fc_budget=budget, max_provider_errors=2)
    with patch.object(exa, "post", side_effect=RuntimeError("boom")) as post:
        for _ in range(3):
            assert f.find(venue(), TODAY).website == "https://oriana.com/"
    assert post.call_count == 2 and "boom" in caplog.text  # off after two errors in a row


def test_iter_search_lookups_stops_when_every_provider_is_spent() -> None:
    vs = [make_venue(f"v:{i}", name="Oriana", address="1 Main St", camis=None) for i in range(3)]
    f = finder(FakeFetch({}), exa=exa_with([], limit=2))
    out = list(iter_search_lookups(vs, f, [v.venue_id for v in vs], TODAY))
    assert len(out) == 2 and all(o.miss_reason == "no_candidates" for o in out)


def test_iter_search_lookups_skips_venues_that_are_not_prioritized() -> None:
    a, b = make_venue("v:a", name="A"), make_venue("v:b", name="B")
    f = finder(FakeFetch({}), exa=exa_with([]))
    out = list(iter_search_lookups([a, b], f, ["v:b"], TODAY))
    assert [o.venue_id for o in out] == ["v:b"]
