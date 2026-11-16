import re
import subprocess
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from scripts.hospitality import cli
from scripts.hospitality.benchmark.compare import FAIRNESS_NOTE
from scripts.hospitality.models import (
    BenchmarkResult,
    Contact,
    Contribution,
    CurveRecord,
    Draft,
    DraftSentence,
    EntityLink,
    EventAppearance,
    Group,
    Judgement,
    StackObservation,
)
from scripts.hospitality.report import build_report
from scripts.hospitality.store import DocStore
from tests.hospitality.factories import (
    make_embed_label,
    make_estimate,
    make_license,
    make_scored,
    make_signal,
    make_venue,
)

HEADERS = [
    "Universe and location counts",
    "Opening-timing curve",
    "Recall audit",
    "Head-to-head",
    "Backtests",
    "Stack distribution and Loyalist penetration",
    "Top 25 prospects with traces",
    "Contacts coverage and cost per verified contact",
    "Drafts with judge scores",
    "Event ranking and the top meeting list",
    "Limitations and assumptions",
    "Questions for Magic",
]
TODAY = date(2026, 11, 16)


def sections(text: str) -> dict[int, str]:
    parts = re.split(r"^## (\d+)\. ", text, flags=re.MULTILINE)
    return {int(parts[i]): parts[i + 1] for i in range(1, len(parts), 2)}


def group(gid: str, name: str, venue_ids: tuple[str, ...]) -> Group:
    return Group(group_id=gid, name=name, venue_ids=venue_ids, resolution="singleton")


def full_store(tmp_path: Path) -> DocStore:
    store = DocStore(f"sqlite:///{tmp_path}/m.db")
    venues = [
        make_venue(
            "v:a",
            name="Zephyr Hall",
            group_id="g:a",
            camis="1",
            license_ids=("L1",),
            license_description="Restaurant",
            first_inspection_date=date(2026, 10, 1),
            website="https://zephyr.test",
        ),
        make_venue("v:b", name="Quill Room", group_id="g:b"),
        make_venue("v:c", name="Moth Bistro", group_id="g:c"),
        make_venue("v:d", name="Orbit Catering", group_id="g:d"),
    ]
    store.save("venues", venues, key=lambda v: v.venue_id)
    store.save(
        "groups",
        [
            group("g:a", "Zephyr Hall", ("v:a",)),
            group("g:b", "Quill Room", ("v:b",)),
            group("g:c", "Moth Bistro", ("v:c",)),
            group("g:d", "Orbit Catering", ("v:d",)),
        ],
        key=lambda g: g.group_id,
    )
    store.save(
        "licenses",
        [make_license("L1", source="sla_active", original_issue_date=date(2026, 8, 1))],
        key=lambda r: r.record_id,
    )
    store.save(
        "links",
        [EntityLink(left_id="L9", right_id="9", kind="possibly_same", probability=0.5, method="t")],
        key=lambda x: x.left_id,
    )
    store.save(
        "curves",
        [
            CurveRecord(
                stratum="all", n=40, steps=((0.0, 1.0), (30.0, 0.75), (60.0, 0.5), (90.0, 0.2))
            )
        ],
        key=lambda r: r.stratum,
    )
    store.save("estimates", [make_estimate("v:a", basis="curve:all")], key=lambda e: e.venue_id)
    sig = make_signal("license_pending", "v:a", evidence_ref="sla:ref-123", detail="pending")
    store.save("license_signals", [sig], key=lambda s: s.signal_id)
    trace = (
        Contribution(
            signal_id=sig.signal_id,
            signal_type="license_pending",
            precision=0.3,
            weight=1.0,
            contribution=0.3,
        ),
        Contribution(
            signal_id="license_issued:v:a",
            signal_type="license_issued",
            precision=0.3,
            weight=1.0,
            contribution=0.0,
            note="folded into strongest opening signal",
        ),
    )
    store.save(
        "scores",
        [
            make_scored("g:a", 0.3, contributions=trace),
            make_scored("g:b", 0.1),
            make_scored("g:c", 0.9, is_customer=True),
            make_scored("g:d", 0.0, disqualified_reason="contract_foodservice"),
        ],
        key=lambda a: a.group_id,
    )
    # Customer evidence: a stored embed label on Moth Bistro's venue (stored seed copies are
    # ignored; the seed YAML is authoritative). The crawl below saw the embed there too.
    store.save("customer_labels", [make_embed_label("v:c", name="Moth Bistro")], key=lambda c: "c")
    store.save(
        "benchmark",
        [
            BenchmarkResult(
                k=50,
                sf_hits=7,
                sf_precision_at_k=0.14,
                claude_hits=(2, 3),
                claude_precision_at_k=(0.04, 0.06),
                claude_duplicates=(1, 0),
                claude_unmatched=(5, 4),
                claude_run_jaccard=0.3,
                truth_total=40,
                notes=(FAIRNESS_NOTE, "scope note"),
            )
        ],
        key=lambda r: "b",
    )
    store.save(
        "stack_observations",
        [
            StackObservation(
                venue_id="v:c",
                url="https://moth.test",
                observed_at=datetime(2026, 11, 1, tzinfo=UTC),
                platforms=("resy", "loyalist"),
                evidence=("e", "e"),
                fetched_via="fetcher",
            )
        ],
        key=lambda o: o.venue_id,
    )
    store.save(
        "contacts",
        [
            Contact(
                contact_id="c1",
                group_id="g:a",
                name="Ada Fake",
                role="General Manager",
                email="ada@zephyr.test",
                email_confidence=0.9,
                instagram=None,
                phone=None,
                source="hunter",
                evidence_ref="r",
            )
        ],
        key=lambda c: c.contact_id,
    )
    d = Draft(
        draft_id="d1",
        group_id="g:a",
        contact_id="c1",
        angle="opening",
        subject="Hello",
        sentences=(
            DraftSentence(text="You are opening.", evidence_ids=(sig.signal_id,), is_claim=True),
        ),
    )
    store.save("drafts", [d], key=lambda x: x.draft_id)
    store.save(
        "judgements",
        [
            Judgement(
                score=0.8,
                hyper_specific=True,
                factually_grounded=True,
                non_obvious=True,
                deletion_reason="",
                what_would_make_me_reply="",
                grounding_violations=(),
                passed=True,
            )
        ],
        key=lambda j: "d1",
    )
    store.save(
        "event_appearances",
        [
            EventAppearance(
                event_id="e:1",
                person="Quinn Test",
                restaurant="Quill Room",
                role="speaker",
                source_url="https://x.test",
            ),
            EventAppearance(
                event_id="e:1",
                person="Moth Owner",
                restaurant="Moth Bistro",
                role="speaker",
                source_url="https://x.test",
            ),
        ],
        key=lambda a: a.person,
    )
    return store


@pytest.fixture
def events_yaml(tmp_path: Path) -> Path:
    p = tmp_path / "events.yaml"
    p.write_text(
        "events:\n  - {event_id: e:1, name: Fake Summit, start: 2027-05-22, end: 2027-05-25,\n"
        "     city: NYC, event_type: curated_conference, cost_usd: 500, lineup_urls: []}\n"
    )
    return p


def build(store: DocStore, tmp_path: Path, events_yaml: Path | None = None) -> str:
    from scripts.hospitality.config import load_config

    path = build_report(
        store, load_config(), tmp_path / "out", today=TODAY, events_path=events_yaml
    )
    return path.read_text(encoding="utf-8")


def test_all_twelve_headers_in_order_and_hindsight_note(tmp_path, events_yaml) -> None:
    text = build(full_store(tmp_path), tmp_path, events_yaml)
    found = re.findall(r"^## (\d+)\. (.+)$", text, flags=re.MULTILINE)
    assert [(int(n), t) for n, t in found] == list(enumerate(HEADERS, 1))
    assert FAIRNESS_NOTE in sections(text)[4]
    assert "n=40" in sections(text)[4]  # truth openings carried with the numbers


def test_top_prospect_shows_trace_and_evidence_ref(tmp_path, events_yaml) -> None:
    s7 = sections(build(full_store(tmp_path), tmp_path, events_yaml))[7]
    assert "Zephyr Hall" in s7
    assert "license_pending" in s7 and "sla:ref-123" in s7
    assert "folded into strongest opening signal" in s7


def test_customers_never_in_cold_table_and_disqualified_listed_apart(tmp_path, events_yaml) -> None:
    text = build(full_store(tmp_path), tmp_path, events_yaml)
    s7 = sections(text)[7]
    ranked, _, rest = s7.partition("### Disqualified")
    assert "Moth Bistro" not in ranked and "Orbit Catering" not in ranked
    assert "Orbit Catering" in rest and "contract_foodservice" in rest
    s6 = sections(text)[6]
    assert "Moth Bistro" in s6 and "warm intro" in s6
    s10 = sections(text)[10]
    prospects, _, warm = s10.partition("warm intro")
    assert "Moth Owner" not in prospects and "Moth Owner" in warm


def test_missing_inputs_say_not_run(tmp_path) -> None:
    store = DocStore(f"sqlite:///{tmp_path}/empty.db")
    text = build(store, tmp_path)
    secs = sections(text)
    assert len(secs) == 12
    for n in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10):
        assert "not run" in secs[n].lower(), n
    assert "precision" not in secs[4].lower() or "not run" in secs[4].lower()
    assert "recall:" not in secs[3].lower()


def test_report_without_optional_stages_has_no_fabricated_numbers(tmp_path) -> None:
    store = full_store(tmp_path)
    for kind in (
        "benchmark",
        "contacts",
        "drafts",
        "judgements",
        "stack_observations",
        "event_appearances",
    ):
        store.clear(kind)
    secs = sections(build(store, tmp_path))
    for n in (4, 6, 8, 9, 10):
        assert "not run" in secs[n].lower(), n
    assert "sf_hits" not in secs[4] and "0.14" not in secs[4]


def test_report_written_only_under_out_dir(tmp_path, events_yaml) -> None:
    from scripts.hospitality.config import load_config

    out = tmp_path / "out" / "magic"
    path = build_report(
        full_store(tmp_path), load_config(), out, today=TODAY, events_path=events_yaml
    )
    assert path.parent == out and path.suffix == ".md"


def test_cli_report_targets_gitignored_out_magic(monkeypatch, tmp_path) -> None:
    root = Path(cli.__file__).resolve().parents[2]
    assert cli.OUT_DIR == root / "out" / "magic"
    target = cli.OUT_DIR / "demo_report.md"
    res = subprocess.run(["git", "check-ignore", "-q", str(target)], check=False, cwd=root)
    assert res.returncode == 0  # ignored, so a customer-bearing report can never be committed
    store = DocStore(f"sqlite:///{tmp_path}/m.db")
    monkeypatch.setattr(cli, "DocStore", lambda: store)
    monkeypatch.setattr(cli, "OUT_DIR", tmp_path / "out")
    written = cli.report()
    assert written == tmp_path / "out" / "demo_report.md" and written.exists()


def test_tied_ranks_are_shown_as_a_shared_rank_with_the_tie_break(tmp_path, events_yaml) -> None:
    """I8: ranks that share one priority must read as tied, not as an ordered list."""
    store = full_store(tmp_path)
    tied = [
        make_scored(
            "g:b",
            0.1,
            opening_date=date(2026, 11, 1),
            opening_gap_days=15,
            latest_signal_on=date(2026, 6, 1),
        ),
        make_scored("g:d", 0.1, opening_date=date(2026, 3, 1), opening_gap_days=260),
    ]
    store.save("scores", tied, key=lambda a: a.group_id)  # g:d now an eligible prospect
    s7 = sections(build(store, tmp_path, events_yaml))[7]
    assert "Ranks 2–3 share priority 0.100" in s7
    assert "#### 2 (tied 2–3). Quill Room" in s7
    assert "#### 3 (tied 2–3). Orbit Catering" in s7
    assert "#### 1. Zephyr Hall" in s7  # a unique score keeps a plain rank
    # A past opening must not read as a future one (report quality pass).
    assert "opening 2026-11-01 (15 days ago)" in s7
    assert "days from today" not in s7


def test_tie_break_says_in_n_days_for_a_future_opening(tmp_path, events_yaml) -> None:
    store = full_store(tmp_path)
    future = make_scored("g:b", 0.1, opening_date=date(2026, 12, 6), opening_gap_days=20)
    store.save("scores", [future], key=lambda a: a.group_id)
    s7 = sections(build(store, tmp_path, events_yaml))[7]
    assert "opening 2026-12-06 (in 20 days)" in s7


def test_group_caveat_names_only_the_grouping_rules_that_exist(tmp_path, events_yaml) -> None:
    """Report quality pass: no grouping step reads website location pages."""
    s1 = sections(build(full_store(tmp_path), tmp_path, events_yaml))[1]
    assert "location pages" not in s1
    assert "shared legal name, shared website domain" in s1
    assert "press and job-board" in s1


def test_a_tie_that_runs_past_the_top_n_says_so(tmp_path, events_yaml, monkeypatch) -> None:
    from scripts.hospitality import report

    store = full_store(tmp_path)
    tied = [make_scored("g:b", 0.1), make_scored("g:d", 0.1)]
    store.save("scores", tied, key=lambda a: a.group_id)
    monkeypatch.setattr(report, "TOP_N", 2)
    s7 = sections(build(store, tmp_path, events_yaml))[7]
    assert "Ranks 2–3 share priority 0.100 (tied); rank 3 is below the top 2" in s7
    assert "no dated opening" in s7


def test_timing_section_states_the_match_miss_drop_rule(tmp_path, events_yaml) -> None:
    """M10: after 9b, likely match misses are dropped from the curve, not censored."""
    from scripts.hospitality.config import load_config

    cfg = load_config()
    s2 = sections(build(full_store(tmp_path), tmp_path, events_yaml))[2]
    assert "censored, not dropped" not in s2
    assert "dropped" in s2 and f"{cfg.window_unmatched_censor_max_age_days} days" in s2
    assert f"{cfg.max_opening_days:g} days" in s2
