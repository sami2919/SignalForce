"""I2: the customer gate is computed at the point of use from durable evidence.

Seed labels plus the full history of embed observations decide who is a customer; neither the
command order, the latest crawl alone nor a stored `is_customer` flag may let one through.
"""

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock

import pytest

from scripts.hospitality import cli
from scripts.hospitality.contacts import clay
from scripts.hospitality.models import (
    Contact,
    Group,
    Judgement,
    ScoredAccount,
    StackObservation,
)
from scripts.hospitality.stack.signals import loyalist_venues
from scripts.hospitality.store import DocStore
from tests.hospitality.factories import make_scored, make_signal, make_venue
from tests.hospitality.test_drafts import make_draft

T1 = datetime(2026, 11, 1, tzinfo=UTC)
T2 = datetime(2026, 11, 15, tzinfo=UTC)


def obs(venue_id: str, at: datetime, platforms: tuple[str, ...], via: str) -> StackObservation:
    return StackObservation(
        venue_id=venue_id,
        url=f"https://{venue_id}.test",
        observed_at=at,
        platforms=platforms,
        evidence=tuple(f"ev:{p}" for p in platforms),
        fetched_via=via,  # type: ignore[arg-type]
    )


EMBED = obs("v:x", T1, ("resy", "loyalist"), "firecrawl")
BUDGET_OUT = obs("v:x", T2, ("resy",), "fetcher")  # Firecrawl budget spent: JS embed unseen


def test_embed_evidence_is_sticky_across_a_later_crawl_that_misses_it() -> None:
    from scripts.hospitality.stack.signals import lapsed_loyalist_venues

    assert loyalist_venues([EMBED, BUDGET_OUT]) == {"v:x": "ev:loyalist"}
    assert lapsed_loyalist_venues([EMBED, BUDGET_OUT]) == ["v:x"]  # for review, not an unlabel
    assert lapsed_loyalist_venues([EMBED]) == []


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> DocStore:
    seed = tmp_path / "seed.yaml"
    seed.write_text("customers: []\ndismissed_embeds: []\n")
    monkeypatch.setattr(cli, "SEED_PATH", seed)
    s = DocStore(f"sqlite:///{tmp_path}/m.db")
    venues = [
        make_venue("v:x", name="Xenia", website="https://v:x.test", group_id="g:x"),
        make_venue("v:a", name="Alder", website="https://alder.test", group_id="g:a"),
    ]
    s.save("venues", venues, key=lambda v: v.venue_id)  # type: ignore[attr-defined]
    s.save(
        "groups",
        [
            Group(group_id=v.group_id, name=v.name, venue_ids=(v.venue_id,), resolution="singleton")
            for v in venues
        ],
        key=lambda g: g.group_id,  # type: ignore[attr-defined]
    )
    # Scores from BEFORE the crawl: X looks like the best cold prospect.
    s.save(
        "scores",
        [make_scored("g:x", 0.9), make_scored("g:a", 0.5)],
        key=lambda a: a.group_id,  # type: ignore[attr-defined]
    )
    s.save(
        "signals",
        [make_signal("press_opening", "v:x"), make_signal("press_opening", "v:a")],
        key=lambda x: x.signal_id,
    )  # type: ignore[attr-defined]
    # The crawl then detects the embed; `labels` and `score` were NOT re-run.
    s.save(
        "stack_observations",
        [EMBED, BUDGET_OUT],
        key=lambda o: f"{o.venue_id}|{o.observed_at.isoformat()}",  # type: ignore[attr-defined]
    )
    monkeypatch.setattr(cli, "DocStore", lambda: s)
    return s


def test_current_customers_reads_full_embed_history(store: DocStore) -> None:
    from scripts.hospitality.labels import current_customers

    assert set(current_customers(store, cli.SEED_PATH)) == {"g:x"}


def test_labels_keep_an_embed_customer_after_a_crawl_that_misses_it(store: DocStore) -> None:
    out = cli.labels()
    assert out["embed"] == 1 and out["embeds_lapsed"] == 1


def test_dismissed_embed_is_not_a_customer(store: DocStore, tmp_path: Path) -> None:
    from scripts.hospitality.labels import current_customers

    cli.SEED_PATH.write_text("customers: []\ndismissed_embeds: [{venue_id: 'v:x', reason: r}]\n")
    assert current_customers(store, cli.SEED_PATH) == {}


def test_contacts_never_targets_an_embed_customer_with_a_stale_flag(
    store: DocStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    for var in ("HUNTER_API_KEY", "FIRECRAWL_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.setenv(var, "k")
    seen: list[str] = []

    def fake(account: ScoredAccount, venues: object, **kw: object) -> list[Contact]:
        seen.append(account.group_id)
        return []

    monkeypatch.setattr(cli, "find_contacts", fake)
    cli.contacts(top=5)
    assert seen == ["g:a"]


def test_draft_never_drafts_for_an_embed_customer_with_a_stale_flag(
    store: DocStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    seen: list[str] = []

    def fake_draft(account, evidence, contact, angle):  # type: ignore[no-untyped-def]
        seen.append(account.group_id)
        return make_draft((), draft_id=f"d:{account.group_id}", group_id=account.group_id)

    monkeypatch.setattr(cli, "draft", fake_draft)
    verdict = Judgement(
        score=8.0,
        hyper_specific=True,
        factually_grounded=True,
        non_obvious=True,
        deletion_reason="",
        what_would_make_me_reply="",
        grounding_violations=(),
        passed=True,
    )
    monkeypatch.setattr(cli, "judge", lambda d, ev, *, account_text, pass_score: verdict)
    cli.draft_command(top=5)
    assert "g:x" not in seen and "g:a" in seen


def test_clay_push_never_pushes_an_embed_customer_with_a_stale_flag(
    store: DocStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CLAY_WEBHOOK_URL", "https://hooks.test/x")
    post = Mock(return_value=Mock(status_code=200))
    monkeypatch.setattr(clay.requests, "post", post)
    cli.clay_push(top=5)
    assert [c.kwargs["json"]["group_id"] for c in post.call_args_list] == ["g:a"]


def test_clay_import_does_not_accept_rows_for_an_embed_customer(
    store: DocStore, tmp_path: Path
) -> None:
    csv = tmp_path / "clay.csv"
    csv.write_text(
        "group_id,name,role,email,email_confidence\n"
        "g:x,Xu Test,Owner,xu@x.test,0.9\n"
        "g:a,Al Test,Owner,al@a.test,0.9\n"
    )
    out = cli.clay_import(csv)
    assert out["skipped"] == 1 and {c.group_id for c in store.load("contacts", Contact)} == {"g:a"}


def test_score_marks_an_embed_customer_without_a_labels_run(store: DocStore) -> None:
    cli.score(now=T2)
    by_id = {a.group_id: a for a in store.load("scores", ScoredAccount)}
    assert by_id["g:x"].is_customer and not by_id["g:a"].is_customer


def test_report_never_ranks_an_embed_customer_with_a_stale_flag(
    store: DocStore, tmp_path: Path
) -> None:
    from scripts.hospitality.config import load_config
    from scripts.hospitality.report import build_report

    text = build_report(store, load_config(), tmp_path / "out").read_text(encoding="utf-8")
    ranking = text.split("## 7.")[1].split("## 8.")[0].split("### Disqualified")[0]
    assert "Alder" in ranking and "Xenia" not in ranking
