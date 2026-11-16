import json
import math
from datetime import date

import pytest
from pydantic import ValidationError

from scripts.hospitality.measure.backtest import auc, case_replay, find_venue, fit_auc
from scripts.hospitality.models import BacktestResult, CaseReplay, CustomerLabel
from tests.hospitality.factories import make_license, make_scored, make_signal, make_venue


def _label(name: str = "The Noortwyck", when: date | None = date(2026, 5, 1)) -> CustomerLabel:
    return CustomerLabel(
        name=name,
        website_domain=None,
        first_public_date=when,
        source="public_list",
        evidence_ref="x",
    )


def test_auc_hand_computed():
    assert auc([0.9, 0.4], [0.5, 0.1]) == pytest.approx(0.75)
    assert auc([0.5], [0.5]) == pytest.approx(0.5)


def test_auc_empty_side_is_nan():
    assert math.isnan(auc([], [0.1]))
    assert math.isnan(auc([0.1], []))


def _sigs(*signals):
    """signals_for stub: every listed signal, whatever the venue and anchor."""
    return lambda venue, anchor: list(signals)


def test_case_replay_lead_days():
    labels = {"g:1": _label()}
    venues = [make_venue("v:o", name="Oriana", group_id="g:1", license_ids=("l1",))]
    lics = [make_license("l1", source="sla_active", original_issue_date=date(2026, 2, 1))]
    sigs = _sigs(make_signal("license_issued", "v:o", observed=date(2026, 2, 1)))
    [r] = case_replay(labels, venues, sigs, {"The Noortwyck": "Oriana"}, seeds=[], licenses=lics)
    assert r.status == "replayed" and r.anchor_basis == "customer"
    assert r.lead_days == 89 and r.signal_types == ("license_issued",)
    assert r.new_venue_id == "v:o" and r.first_signal_date == date(2026, 2, 1)


def test_case_replay_no_signal_is_a_real_miss_and_missing_venue_is_not_evaluable():
    labels = {"g:1": _label(), "g:2": _label("Momofuku")}
    venues = [
        make_venue(
            "v:o",
            name="Oriana",
            group_id="g:1",
            license_ids=("l1",),
            first_inspection_date=date(2026, 1, 1),
        )
    ]
    # A license on file before the opening that produced no signal: a real miss.
    lics = [make_license("l1", source="sla_active", original_issue_date=date(2024, 1, 1))]
    hints = {"The Noortwyck": "Oriana", "Momofuku": "Zzz"}
    out = {
        r.customer: r for r in case_replay(labels, venues, _sigs(), hints, seeds=[], licenses=lics)
    }
    assert out["The Noortwyck"].status == "replayed" and out["The Noortwyck"].lead_days is None
    assert out["Momofuku"].status == "not_evaluable" and out["Momofuku"].new_venue_id is None
    assert "not found" in out["Momofuku"].reason


def test_case_replay_ignores_non_opening_and_post_anchor_signals():
    labels = {"g:1": _label()}
    venues = [
        make_venue("v:o", name="Oriana", group_id="g:1", first_inspection_date=date(2026, 1, 1))
    ]
    sigs = _sigs(
        make_signal("stack_fragmented", "v:o", observed=date(2026, 1, 1)),
        make_signal("license_issued", "v:o", observed=date(2026, 6, 1)),  # after the anchor
    )
    [r] = case_replay(labels, venues, sigs, {"The Noortwyck": "Oriana"}, seeds=[], licenses=[])
    assert r.lead_days is None and r.signal_types == ()


def test_undated_customer_is_marked_not_evaluable_not_dropped():
    labels = {"g:1": _label(when=None)}
    venues = [make_venue("v:o", name="Oriana", group_id="g:1")]
    [r] = case_replay(labels, venues, _sigs(), {"The Noortwyck": "Oriana"}, seeds=[], licenses=[])
    assert r.status == "not_evaluable" and r.anchor_date is None and r.lead_days is None
    assert r.reason.startswith("undated")


def test_venue_newer_than_the_customer_date_is_not_a_miss():
    """I6 (live): Oriana licensed 2026-04-07 was anchored to The Noortwyck's 2024-11-02, so
    "no prior signal" was guaranteed. A venue that first appears after the anchor cannot have
    preceded the purchase: not evaluable, never a miss."""
    labels = {"g:1": _label(when=date(2024, 11, 2))}
    venues = [
        make_venue(
            "v:o",
            name="ORIANA",
            group_id="g:1",
            license_ids=("l1",),
            first_inspection_date=date(2026, 10, 14),
        )
    ]
    lics = [
        make_license(
            "l1", source="sla_active", received_date=None, original_issue_date=date(2026, 4, 7)
        )
    ]
    sigs = _sigs(make_signal("license_issued", "v:o", observed=date(2026, 4, 7)))
    [r] = case_replay(labels, venues, sigs, {"The Noortwyck": "Oriana"}, seeds=[], licenses=lics)
    assert r.status == "not_evaluable" and r.lead_days is None
    assert "2026-04-07" in r.reason and "2024-11-02" in r.reason


def test_venue_with_its_own_seed_entry_is_anchored_on_its_own_date():
    labels = {"g:1": _label(when=date(2024, 11, 2))}
    venues = [make_venue("v:o", name="ORIANA", group_id="g:1", license_ids=("l1",))]
    lics = [
        make_license(
            "l1", source="sla_active", received_date=None, original_issue_date=date(2026, 4, 7)
        )
    ]
    sigs = _sigs(make_signal("license_issued", "v:o", observed=date(2026, 4, 7)))
    hints = {"The Noortwyck": "Oriana"}
    undated = [_label("Oriana", when=None)]
    [r] = case_replay(labels, venues, sigs, hints, seeds=undated, licenses=lics)
    assert r.status == "not_evaluable" and r.reason.startswith("undated")
    dated = [_label("Oriana", when=date(2026, 6, 1))]
    [r] = case_replay(labels, venues, sigs, hints, seeds=dated, licenses=lics)
    assert (r.status, r.anchor_basis, r.anchor_date) == ("replayed", "venue", date(2026, 6, 1))
    assert r.lead_days == 55


def test_find_venue_is_strict_never_a_token_subset():
    venues = [
        make_venue("v:x", name="LA BAR", group_id="g:9"),
        make_venue("v:t", name="T/CO", group_id="g:9"),
        make_venue("v:k", name="KABAWA / BAR KABAWA", group_id="g:9"),
    ]
    assert find_venue("La Tête d'Or Bar", ["g:1"], venues) is None
    assert find_venue("Bar Kabawa", ["g:1"], venues).venue_id == "v:k"  # a "/" segment


def test_one_case_per_customer_preferring_the_customers_own_group():
    labels = {"g:1": _label("Dinex Group"), "g:2": _label("Dinex Group")}
    venues = [
        make_venue(
            "v:a", name="LA TETE D'OR", group_id="g:9", first_inspection_date=date(2026, 1, 1)
        ),
        make_venue(
            "v:b", name="LA TETE D'OR", group_id="g:2", first_inspection_date=date(2026, 1, 1)
        ),
    ]
    [r] = case_replay(
        labels, venues, _sigs(), {"Dinex Group": "La Tête d'Or"}, seeds=[], licenses=[]
    )
    assert (r.group_id, r.new_venue_id) == ("g:2", "v:b")


def test_case_replay_model_frozen():
    r = CaseReplay(
        group_id="g:1",
        customer="c",
        anchor_date=date(2026, 1, 1),
        new_venue_id=None,
        first_signal_date=None,
        lead_days=None,
        signal_types=(),
        status="replayed",
    )
    with pytest.raises(ValidationError):
        r.lead_days = 3  # type: ignore[misc]


def test_backtest_replay_keeps_an_inspection_that_predates_the_anchor(tmp_path, monkeypatch):
    """As of the anchor, a venue inspected before it had already opened: a later license is a
    renewal, not an opening signal, so it must not be replayed as a lead."""
    from scripts.hospitality import cli
    from scripts.hospitality.models import Group
    from scripts.hospitality.store import DocStore

    store = DocStore(f"sqlite:///{tmp_path}/m.db")
    venue = make_venue(
        "v:m",
        name="MASSARA",
        group_id="g:v:m",
        license_ids=("l1",),
        first_inspection_date=date(2025, 3, 20),
    )
    lic = make_license("l1", source="sla_active", original_issue_date=date(2025, 6, 10))
    store.save("venues", [venue], key=lambda v: v.venue_id)
    store.save(
        "groups",
        [Group(group_id="g:v:m", name="MASSARA", venue_ids=("v:m",), resolution="singleton")],
        key=lambda g: g.group_id,
    )
    store.save("licenses", [lic], key=lambda r: r.record_id)
    out = cli.backtest(store)
    [case] = [c for c in out.cases if c.customer.startswith("Rezd")]
    assert case.new_venue_id == "v:m" and case.lead_days is None
    # The 2025-06 license after the 2025-03 inspection is no lead; and with no license on file
    # before the opening, no signal could exist: not evaluable, never a miss (I6, live).
    assert case.status == "not_evaluable" and "no license or application" in case.reason


def test_fit_auc_customers_vs_rest():
    accounts = [
        make_scored("g:1", fit=0.9, is_customer=True),
        make_scored("g:2", fit=0.2, is_customer=True),
        make_scored("g:3", fit=0.5),
        make_scored("g:4", fit=0.1),
    ]
    assert fit_auc(accounts) == pytest.approx(0.75)


def test_fit_auc_constant_fit_is_chance():
    accounts = [make_scored("g:1", is_customer=True), make_scored("g:2")]
    assert fit_auc(accounts) == pytest.approx(0.5)


def test_backtest_command_prints_indicative_with_n(tmp_path, monkeypatch, capsys):
    from scripts.hospitality import cli

    monkeypatch.setattr(
        cli,
        "backtest",
        lambda: BacktestResult(
            cases=(
                CaseReplay(
                    group_id="g:1",
                    customer="Dinex Group",
                    anchor_date=date(2025, 10, 20),
                    new_venue_id="v:1",
                    first_signal_date=date(2025, 1, 1),
                    lead_days=292,
                    signal_types=("license_issued",),
                    status="replayed",
                    anchor_basis="customer",
                ),
                CaseReplay(
                    group_id="g:2",
                    customer="The Noortwyck",
                    anchor_date=None,
                    new_venue_id="v:2",
                    first_signal_date=None,
                    lead_days=None,
                    signal_types=(),
                    status="not_evaluable",
                    reason="undated: the venue's own seed entry has no public date",
                ),
            ),
            undated=3,
            fit_auc=0.5,
            fit_distinct=1,
            n_customers=2,
            n_others=100,
        ),
    )
    assert cli.main(["backtest"]) == 0
    text = capsys.readouterr().out
    assert "indicative" in text.lower() and "n=2" in text and "n=100" in text
    assert "degenerate" in text.lower()
    assert "not evaluable" in text.lower() and "1 replayed" in text
    json.dumps(text)


def test_run_p0_chains_steps_in_order(monkeypatch):
    from scripts.hospitality import cli

    calls: list[str] = []
    real_main = cli.main

    def fake(argv=None):
        if argv == ["run-p0"]:
            return real_main(argv)
        calls.append(argv[0])
        return 0

    monkeypatch.setattr(cli, "main", fake)
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "k")
    monkeypatch.setenv("FIRECRAWL_API_KEY", "k")
    assert cli.main(["run-p0"]) == 0
    assert calls == [
        "ingest-sla", "snapshot-pending", "ingest-dohmh", "resolve", "window",
        "websites", "crawl", "labels", "score", "recall", "backtest",
    ]  # fmt: skip


def test_run_p0_fails_fast_before_any_step_without_the_keys_it_needs(monkeypatch):
    """M6: a missing key for a later step (websites, crawl) stops run-p0 before ingest runs."""
    import pytest

    from scripts.hospitality import cli

    calls: list[str] = []
    real_main = cli.main

    def fake(argv=None):
        if argv == ["run-p0"]:
            return real_main(argv)
        calls.append(argv[0])
        return 0

    monkeypatch.setattr(cli, "main", fake)
    monkeypatch.delenv("GOOGLE_PLACES_API_KEY", raising=False)
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    with pytest.raises(SystemExit) as exc:
        cli.main(["run-p0"])
    assert "GOOGLE_PLACES_API_KEY" in str(exc.value) and "FIRECRAWL_API_KEY" in str(exc.value)
    assert calls == []


@pytest.mark.parametrize(
    ("licenses", "why"),
    [
        ((), "no license at all"),
        # live: KABAWA inspected 2025-05-08, its only license issued 2026-10-22 (a re-issue)
        (
            (make_license("l1", source="sla_active", original_issue_date=date(2026, 10, 22)),),
            "license only after the opening",
        ),
    ],
)
def test_opening_with_no_license_on_file_before_it_is_not_evaluable(licenses, why):
    """I6 (quality pass): with no license or application dated before the venue opened (or
    before the anchor), no license signal could have fired; "no prior signal" was guaranteed,
    so the case is not evaluable, and the reason says it is a coverage gap."""
    labels = {"g:1": _label("Momofuku", when=date(2025, 10, 20))}
    venues = [
        make_venue(
            "v:k",
            name="KABAWA / BAR KABAWA",
            group_id="g:1",
            license_ids=tuple(lic.record_id for lic in licenses),
            first_inspection_date=date(2025, 5, 8),
        )
    ]
    [r] = case_replay(
        labels, venues, _sigs(), {"Momofuku": "Bar Kabawa"}, seeds=[], licenses=list(licenses)
    )
    assert r.status == "not_evaluable", why
    assert "no license or application" in r.reason and "coverage gap" in r.reason


def test_report_case_replay_names_every_exclusion_and_never_reads_as_a_rate(tmp_path, monkeypatch):
    """I6 (quality pass): with one replayed case the report must not read as a rate, and its
    not-evaluable summary must name the no-license-on-file exclusion as a coverage gap."""
    from scripts.hospitality import cli, report
    from scripts.hospitality.store import DocStore

    store = DocStore(f"sqlite:///{tmp_path}/m.db")
    store.save("venues", [make_venue("v:1")], key=lambda v: v.venue_id)
    store.save("scores", [make_scored("g:1")], key=lambda a: a.group_id)

    def case(customer: str, status: str, lead: int | None, reason: str = "") -> CaseReplay:
        return CaseReplay(
            group_id="g:1",
            customer=customer,
            anchor_date=date(2025, 10, 20),
            new_venue_id="v:1",
            first_signal_date=None,
            lead_days=lead,
            signal_types=(),
            status=status,  # type: ignore[arg-type]
            anchor_basis="customer",
            reason=reason,
        )

    result = BacktestResult(
        cases=(
            case("A", "replayed", 192),
            case("B", "not_evaluable", None, "no license or application on file before x"),
        ),
        undated=0,
        fit_auc=0.7,
        fit_distinct=5,
        n_customers=3,
        n_others=100,
    )
    monkeypatch.setattr(cli, "backtest", lambda s=None: result)
    text = "\n".join(report._backtests(store))
    assert "no license or application on file" in text.split("|")[0]  # in the summary sentence
    assert "coverage gap" in text
    assert "too few to estimate a rate" in text
    assert "n=3" in text and "too few customers" in text
