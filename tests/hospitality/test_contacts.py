from unittest.mock import AsyncMock, Mock, patch

import pytest

from scripts.api_client import APIError
from scripts.hospitality import cli
from scripts.hospitality.budget import BudgetExceeded, CallBudget
from scripts.hospitality.contacts import waterfall
from scripts.hospitality.contacts.waterfall import (
    HunterClient,
    find_contacts,
    role_priority,
    team_members,
)
from scripts.hospitality.models import Contact, TeamFacts, TeamPerson
from scripts.hospitality.store import DocStore
from scripts.watch.fetcher import ProbeResult
from tests.hospitality.factories import make_embed_label, make_scored, make_venue

SITE = "https://www.acme.com"
TEAM_URL = "https://www.acme.com/team"
HTML = (
    "<html><body><script>var x='Zed Ghost';</script>"
    "<h1>Our team</h1>"
    "<p>Ana Reyes, Owner. Bo Lin, General Manager. Cy Park, Chef. Di Fox, Director of "
    "Operations. Ed Kim, Founder.</p>"
    '<a href="https://instagram.com/acme_nyc/">ig</a><a href="tel:+12125550100">call</a>'
    '<a href="mailto:ana@acme.com">mail</a><a href="mailto:random@acme.com">x</a>'
    "</body></html>"
)


def people(*pairs: tuple[str, str]) -> TeamFacts:
    return TeamFacts(people=tuple(TeamPerson(name=n, role=r) for n, r in pairs))


ALL = people(
    ("Ana Reyes", "Owner"),
    ("Bo Lin", "General Manager"),
    ("Cy Park", "Chef"),
    ("Di Fox", "Director of Operations"),
    ("Ed Kim", "Founder"),
)


def fc(links: list | None = None) -> Mock:
    m = Mock()
    m.map_site.return_value = {
        "links": links if links is not None else [f"{SITE}/menu", TEAM_URL, f"{SITE}/about"]
    }
    return m


def run_find(
    facts: TeamFacts = ALL,
    *,
    hunter_scores: dict[str, tuple[str | None, float | None]] | None = None,
    html: str | None = HTML,
    venues=None,
    account=None,
    fcm: Mock | None = None,
    budgets: dict[str, CallBudget] | None = None,
    hunter: Mock | None = None,
    max_lookups: int = 2,
):
    hunter = hunter or Mock()
    if hunter_scores is not None:
        hunter.find_email.side_effect = lambda d, f, last: hunter_scores.get(f, (None, None))
    venues = venues if venues is not None else [make_venue("v:1", website=SITE, group_id="g:1")]
    with (
        patch.object(waterfall, "_fetch_page", return_value=html) as fetch,
        patch.object(waterfall, "structured", return_value=facts) as st,
    ):
        out = find_contacts(
            account or make_scored("g:1"),
            venues,
            firecrawl=fcm or fc(),
            hunter=hunter,
            budgets=budgets or {"firecrawl": CallBudget("fc", 5), "hunter": CallBudget("h", 5)},
            min_email_confidence=70.0,
            max_email_lookups=max_lookups,
        )
    return out, hunter, fetch, st


def test_role_priority_ordering() -> None:
    order = ["Co-Founder", "Managing Partner", "Director of Operations", "General Manager", "Chef"]
    ranks = [role_priority(r) for r in order]
    assert ranks == sorted(ranks) and ranks[0] == ranks[1] < ranks[2] < ranks[3] < ranks[4]
    assert role_priority("Owner") < role_priority("Executive Chef")
    assert role_priority("Sommelier") > role_priority("Chef")


def test_team_members_reads_page_through_structured_and_drops_fabrications() -> None:
    parsed = people(
        ("Ana Reyes", "Owner"),
        ("Zed Ghost", "Owner"),  # only inside a <script>: not visible text
        ("Phantom Person", "Chef"),  # not on the page
        ("Bo Lin", "Pastry Wizard"),  # role not on the page
    )
    with (
        patch.object(waterfall, "_fetch_page", return_value=HTML),
        patch.object(waterfall, "structured", return_value=parsed) as st,
    ):
        out = team_members(SITE, fc(), CallBudget("fc", 3))
    assert out == [("Ana Reyes", "Owner")]
    assert st.call_args.args[0] is TeamFacts
    assert st.call_args.kwargs["role"] == "extract"


def test_team_members_picks_same_host_team_page_and_never_linkedin_or_loyalist() -> None:
    links = [
        "https://linkedin.com/company/acme/about",
        "https://www.loyalist.com/for/acme/team",
        "https://other.com/team",
        {"url": f"{SITE}/about"},
        TEAM_URL,
    ]
    with (
        patch.object(waterfall, "_fetch_page", return_value=HTML) as fetch,
        patch.object(waterfall, "structured", return_value=ALL),
    ):
        team_members(SITE, fc(links), CallBudget("fc", 3))
    assert [c.args[0] for c in fetch.call_args_list] == [TEAM_URL]  # /team beats /about


def test_no_team_page_means_no_fetch_and_no_members() -> None:
    with patch.object(waterfall, "_fetch_page") as fetch:
        assert team_members(SITE, fc([f"{SITE}/menu"]), CallBudget("fc", 3)) == []
    fetch.assert_not_called()


def test_linkedin_site_is_never_mapped_or_fetched() -> None:
    f = fc()
    with patch.object(waterfall, "_fetch_page") as fetch:
        assert team_members("https://www.linkedin.com/company/acme", f, CallBudget("fc", 3)) == []
    f.map_site.assert_not_called()
    fetch.assert_not_called()


@pytest.mark.asyncio
async def test_fetch_page_respects_robots_and_skips_forbidden_hosts() -> None:
    blocked = ProbeResult(source_id=0, robots_blocked=True)
    with patch.object(waterfall, "fetch_all", AsyncMock(return_value=[blocked])):
        assert await waterfall._fetch_page_async(TEAM_URL) is None
    ok = ProbeResult(source_id=0, status_code=200, body="<p>hi</p>")
    fetch = AsyncMock(return_value=[ok])
    with patch.object(waterfall, "fetch_all", fetch):
        assert await waterfall._fetch_page_async(TEAM_URL) == "<p>hi</p>"
        for bad in ("https://www.linkedin.com/in/x", "https://loyalist.com/for/acme"):
            assert await waterfall._fetch_page_async(bad) is None
    assert fetch.call_count == 1


def test_team_members_budget_hard_stops_before_the_call() -> None:
    f = fc()
    with pytest.raises(BudgetExceeded):
        team_members(SITE, f, CallBudget("fc", 0))
    f.map_site.assert_not_called()


def test_find_contacts_survives_firecrawl_budget_exhaustion() -> None:
    f = fc()
    out, hunter, _, _ = run_find(fcm=f, budgets={"firecrawl": CallBudget("fc", 0)})
    assert out == [] and f.map_site.call_count == 0
    hunter.find_email.assert_not_called()


def test_email_lookups_follow_role_priority_and_cap_at_two() -> None:
    scores = {"Ana": ("ana.reyes@acme.com", 91.0), "Ed": ("ed@acme.com", 80.0)}
    out, hunter, _, _ = run_find(hunter_scores=scores)
    called = [c.args[1] for c in hunter.find_email.call_args_list]
    # Ana has an on-page email, so the two lookups go to the next-best: Ed (founder), Di (dir ops)
    assert called == ["Ed", "Di"]
    assert hunter.find_email.call_args_list[0].args == ("acme.com", "Ed", "Kim")
    by_name = {c.name: c for c in out}
    assert by_name["Ed Kim"].email == "ed@acme.com" and by_name["Ed Kim"].email_confidence == 80.0
    assert by_name["Bo Lin"].email is None and by_name["Cy Park"].email is None


def test_page_email_attributed_only_when_it_names_the_person() -> None:
    out, _, _, _ = run_find(hunter_scores={})
    by_name = {c.name: c for c in out}
    assert by_name["Ana Reyes"].email == "ana@acme.com"
    assert by_name["Ana Reyes"].email_confidence is None
    assert by_name["Ana Reyes"].source == "team_page"
    assert all(c.email != "random@acme.com" for c in out)  # unattributable: never assigned


def test_hunter_confidence_threshold_is_70() -> None:
    facts = people(("Ed Kim", "Founder"), ("Di Fox", "Director of Operations"))
    scores = {"Ed": ("ed@acme.com", 69.0), "Di": ("di@acme.com", 70.0)}
    out, _, _, _ = run_find(facts, hunter_scores=scores)
    by_name = {c.name: c for c in out}
    assert by_name["Ed Kim"].email is None and by_name["Ed Kim"].email_confidence is None
    assert by_name["Di Fox"].email == "di@acme.com" and by_name["Di Fox"].email_confidence == 70.0
    assert by_name["Di Fox"].source == "team_page+hunter"


def test_hunter_budget_stop_keeps_contacts_without_email() -> None:
    facts = people(("Ed Kim", "Founder"), ("Di Fox", "Director of Operations"))
    budget = CallBudget("h", 1)
    client = HunterClient("k", budget)
    with patch.object(
        HunterClient, "get", return_value={"data": {"email": "ed@acme.com", "score": 90}}
    ) as get:
        out, _, _, _ = run_find(
            facts,
            hunter=client,
            budgets={"firecrawl": CallBudget("fc", 5), "hunter": budget},
        )
    assert get.call_count == 1  # the second lookup never went out
    by_name = {c.name: c for c in out}
    assert by_name["Ed Kim"].email == "ed@acme.com" and by_name["Di Fox"].email is None


def test_hunter_client_spends_before_the_call_and_parses_response() -> None:
    client = HunterClient("k", CallBudget("h", 0))
    with patch.object(HunterClient, "get") as get, pytest.raises(BudgetExceeded):
        client.find_email("acme.com", "Ed", "Kim")
    get.assert_not_called()
    budget = CallBudget("h", 3)
    client = HunterClient("k", budget)
    with patch.object(
        HunterClient, "get", return_value={"data": {"email": "ed@acme.com", "score": 88}}
    ) as get:
        assert client.find_email("acme.com", "Ed", "Kim") == ("ed@acme.com", 88.0)
    assert budget.used == 1
    assert get.call_args.kwargs["params"] == {
        "domain": "acme.com",
        "first_name": "Ed",
        "last_name": "Kim",
    }
    with patch.object(HunterClient, "get", return_value={"data": {"email": None, "score": None}}):
        assert client.find_email("acme.com", "Ed", "Kim") == (None, None)


def test_hunter_client_without_domain_or_name_makes_no_call_and_spends_nothing() -> None:
    budget = CallBudget("h", 3)
    client = HunterClient("k", budget)
    with patch.object(HunterClient, "get") as get:
        assert client.find_email("", "Ed", "Kim") == (None, None)
        assert client.find_email("acme.com", "Ed", "") == (None, None)
    get.assert_not_called()
    assert budget.used == 0


def test_no_website_means_no_domain_no_contacts_no_email() -> None:
    out, hunter, fetch, _ = run_find(venues=[make_venue("v:1", website=None, group_id="g:1")])
    assert out == []
    hunter.find_email.assert_not_called()
    fetch.assert_not_called()


def test_contacts_carry_evidence_channels_and_stable_ids() -> None:
    out, _, _, _ = run_find(hunter_scores={})
    assert len(out) == 5 and all(isinstance(c, Contact) for c in out)
    assert all(c.evidence_ref == TEAM_URL and c.group_id == "g:1" for c in out)
    assert all(c.instagram == "acme_nyc" and c.phone == "+12125550100" for c in out)
    again, _, _, _ = run_find(hunter_scores={})
    assert [c.contact_id for c in out] == [c.contact_id for c in again]
    assert len({c.contact_id for c in out}) == 5


def test_unrecognised_roles_are_not_contacts() -> None:
    facts = people(("Ana Reyes", "Owner"), ("Bo Lin", "General Manager"))
    html = HTML.replace("Cy Park, Chef", "Cy Park, Sommelier")
    facts = people(("Ana Reyes", "Owner"), ("Cy Park", "Sommelier"))
    out, _, _, _ = run_find(facts, hunter_scores={}, html=html)
    assert [c.name for c in out] == ["Ana Reyes"]


def test_customers_and_disqualified_groups_are_not_cold_targets() -> None:
    for acct in (make_scored("g:1", is_customer=True), make_scored("g:1", disqualified_reason="x")):
        f = fc()
        out, hunter, fetch, st = run_find(account=acct, fcm=f)
        assert out == []
        f.map_site.assert_not_called()
        fetch.assert_not_called()
        st.assert_not_called()
        hunter.find_email.assert_not_called()


def test_only_the_accounts_own_venues_are_used() -> None:
    venues = [make_venue("v:9", website="https://zzz.com", group_id="g:other")]
    out, _, fetch, _ = run_find(venues=venues)
    assert out == []
    fetch.assert_not_called()


def test_hunter_api_error_is_logged_and_skipped_but_auth_failure_propagates() -> None:
    facts = people(("Ed Kim", "Founder"))
    hunter = Mock()
    hunter.find_email.side_effect = APIError(status_code=500, message="boom", url="u")
    out, _, _, _ = run_find(facts, hunter=hunter)
    assert out[0].email is None
    hunter.find_email.side_effect = APIError(status_code=401, message="bad key", url="u")
    with pytest.raises(APIError):
        run_find(facts, hunter=hunter)


def test_contacts_command_fails_fast_without_keys(monkeypatch) -> None:
    for var in ("HUNTER_API_KEY", "FIRECRAWL_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.setenv(var, "k")
    for missing in ("HUNTER_API_KEY", "FIRECRAWL_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(missing)
        with pytest.raises(SystemExit) as exc:
            cli.main(["contacts", "--top", "5"])
        assert missing in str(exc.value)
        monkeypatch.setenv(missing, "k")


def test_contacts_command_runs_top_prospects_only_and_saves(tmp_path, monkeypatch, capsys) -> None:
    for var in ("HUNTER_API_KEY", "FIRECRAWL_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.setenv(var, "k")
    store = DocStore(f"sqlite:///{tmp_path}/m.db")
    from scripts.hospitality.models import Group

    key = lambda x: x.group_id
    store.save(
        "groups",
        [
            Group(group_id=g, name=g, venue_ids=(f"v:{g}",), resolution="singleton")
            for g in ("g:a", "g:b", "g:c")
        ],
        key=key,
    )
    store.save(
        "venues",
        [make_venue(f"v:{g}", website=SITE, group_id=g) for g in ("g:a", "g:b", "g:c")],
        key=lambda v: v.venue_id,  # type: ignore[attr-defined]
    )
    store.save(
        "scores",
        [
            make_scored("g:a", 0.9),
            make_scored("g:b", 0.8),
            make_scored("g:c", 0.99, is_customer=True),
        ],
        key=key,
    )
    # The gate reads evidence, not the stored flag: g:c's venue has an embed label.
    store.save("customer_labels", [make_embed_label("v:g:c")], key=lambda c: "c")
    monkeypatch.setattr(cli, "DocStore", lambda: store)
    seen: list[str] = []

    def fake(account, venues, **kw):
        seen.append(account.group_id)
        return [
            Contact(
                contact_id=f"c:{account.group_id}",
                group_id=account.group_id,
                name="Ana Reyes",
                role="Owner",
                email=None,
                email_confidence=None,
                instagram=None,
                phone=None,
                source="team_page",
                evidence_ref=TEAM_URL,
            )
        ]

    monkeypatch.setattr(cli, "find_contacts", fake)
    out = cli.contacts(top=1)
    assert seen == ["g:a"]  # top 1 prospect; the customer g:c is never a target
    assert out["groups"] == 1 and out["contacts"] == 1
    assert [c.contact_id for c in store.load("contacts", Contact)] == ["c:g:a"]
    assert cli.main(["contacts", "--top", "2"]) == 0
    assert seen == ["g:a", "g:a", "g:b"]


def test_contacts_command_keeps_what_it_found_when_a_later_group_errors(
    tmp_path, monkeypatch
) -> None:
    """M12: a non-budget error (Hunter 401, Firecrawl APIError) must not lose paid contacts."""
    for var in ("HUNTER_API_KEY", "FIRECRAWL_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.setenv(var, "k")
    store = DocStore(f"sqlite:///{tmp_path}/m.db")
    from scripts.hospitality.models import Group

    store.save(
        "groups",
        [
            Group(group_id=g, name=g, venue_ids=(f"v:{g}",), resolution="singleton")
            for g in ("g:a", "g:b")
        ],
        key=lambda x: x.group_id,
    )
    store.save(
        "venues",
        [make_venue(f"v:{g}", website=SITE, group_id=g) for g in ("g:a", "g:b")],
        key=lambda v: v.venue_id,  # type: ignore[attr-defined]
    )
    store.save(
        "scores", [make_scored("g:a", 0.9), make_scored("g:b", 0.8)], key=lambda x: x.group_id
    )
    monkeypatch.setattr(cli, "DocStore", lambda: store)

    def fake(account, venues, **kw):
        if account.group_id == "g:b":
            raise RuntimeError("hunter 401")
        return [
            Contact(
                contact_id="c:g:a",
                group_id="g:a",
                name="Ana Reyes",
                role="Owner",
                email=None,
                email_confidence=None,
                instagram=None,
                phone=None,
                source="team_page",
                evidence_ref=TEAM_URL,
            )
        ]

    monkeypatch.setattr(cli, "find_contacts", fake)
    with pytest.raises(RuntimeError, match="hunter 401"):
        cli.contacts(top=2)
    assert [c.contact_id for c in store.load("contacts", Contact)] == ["c:g:a"]


@pytest.mark.parametrize("cap", [1, 3])
def test_hunter_lookups_per_group_follow_the_configured_cap(cap: int) -> None:
    """M2: the per-group Hunter lookup cap is config (it decides paid spend), not a constant."""
    _, hunter, _, _ = run_find(hunter_scores={}, max_lookups=cap)
    assert hunter.find_email.call_count == cap
