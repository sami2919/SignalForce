import logging
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from scripts.hospitality import cli
from scripts.hospitality.budget import BudgetExceeded
from scripts.hospitality.discover.lookalikes import lookalike_signals
from scripts.hospitality.models import CustomerLabel, ExaResult, Group, Signal
from tests.hospitality.factories import make_venue

NOW = datetime(2026, 11, 16, tzinfo=UTC)


def _seed(name: str, domain: str | None) -> CustomerLabel:
    return CustomerLabel(
        name=name,
        website_domain=domain,
        first_public_date=None,
        source="public_list",
        evidence_ref="seed",
    )


def _res(url: str) -> ExaResult:
    return ExaResult(url=url, title="t", published_date=None, text=None)


def _exa(by_seed: dict[str, list[ExaResult]]) -> MagicMock:
    exa = MagicMock()
    exa.find_similar.side_effect = lambda url, **kw: by_seed.get(url, [])
    return exa


def test_matched_domain_becomes_signal_and_customer_domain_is_dropped() -> None:
    seeds = [_seed("Carbone Group", "carbone.com")]
    prospect = make_venue("v:p", name="Nova", website="https://www.novabar.com/menu")
    customer = make_venue("v:c", name="Other Cust", website="https://othercust.com")
    other_seed = _seed("Other Cust", "othercust.com")
    exa = _exa(
        {
            "https://carbone.com": [
                _res("https://www.novabar.com/about"),
                _res("https://othercust.com/home"),
            ]
        }
    )
    sigs = lookalike_signals(
        exa, [seeds[0], other_seed], [prospect, customer], NOW, per_seed=5, groups=[]
    )
    assert [s.entity_id for s in sigs] == ["v:p"]
    s = sigs[0]
    assert isinstance(s, Signal) and s.signal_type == "lookalike" and s.observed_at == NOW
    assert "Carbone Group" in s.evidence_ref
    assert "https://carbone.com" in s.evidence_ref
    assert "https://www.novabar.com/about" in s.evidence_ref
    assert exa.find_similar.call_args_list[0].kwargs["num_results"] == 5


def test_result_matching_customer_venue_by_name_is_dropped() -> None:
    # The seed list knows the customer by name only; the venue's site is the same business.
    seeds = [_seed("Carbone Group", "carbone.com"), _seed("Nova Bar", None)]
    nova = make_venue("v:n", name="Nova Bar", website="https://novabar.com")
    exa = _exa({"https://carbone.com": [_res("https://novabar.com/x")]})
    assert lookalike_signals(exa, seeds, [nova], NOW, groups=[]) == []


def test_result_whose_group_name_is_a_customer_is_dropped() -> None:
    # Residual: the CLI used to pass no groups, so a group-name customer match was skipped here.
    seeds = [_seed("Carbone Group", "carbone.com"), _seed("Major Food Group", None)]
    v = make_venue("v:t", name="Pasta Spot", website="https://pastaspot.com", group_id="g:m")
    groups = [
        Group(group_id="g:m", name="Major Food Group", venue_ids=("v:t",), resolution="manual")
    ]
    exa = _exa({"https://carbone.com": [_res("https://pastaspot.com/x")]})
    assert lookalike_signals(exa, seeds, [v], NOW, groups=groups) == []


def test_groups_argument_is_required() -> None:
    with pytest.raises(TypeError):
        lookalike_signals(_exa({}), [], [], NOW)  # type: ignore[call-arg]


def test_unresolved_domain_is_logged_not_invented(caplog: pytest.LogCaptureFixture) -> None:
    v = make_venue("v:1", name="Nova", website="https://novabar.com")
    exa = _exa({"https://carbone.com": [_res("https://unknown-place.com/a")]})
    with caplog.at_level(logging.INFO):
        sigs = lookalike_signals(exa, [_seed("Carbone", "carbone.com")], [v], NOW, groups=[])
    assert sigs == []
    assert "unknown-place.com" in caplog.text


def test_venue_without_website_never_matched() -> None:
    v = make_venue("v:1", website=None)
    exa = _exa({"https://carbone.com": [_res("https://acme.com")]})
    assert lookalike_signals(exa, [_seed("Carbone", "carbone.com")], [v], NOW, groups=[]) == []


def test_seeds_without_domain_skipped_and_no_call_made() -> None:
    exa = _exa({})
    assert lookalike_signals(exa, [_seed("No Site", None)], [make_venue()], NOW, groups=[]) == []
    exa.find_similar.assert_not_called()


def test_same_result_from_two_seeds_gets_distinct_ids_and_ids_are_unique() -> None:
    v = make_venue("v:p", website="https://novabar.com")
    exa = _exa(
        {
            "https://a.com": [_res("https://novabar.com/x"), _res("https://novabar.com/x")],
            "https://b.com": [_res("https://novabar.com/x")],
        }
    )
    sigs = lookalike_signals(exa, [_seed("A", "a.com"), _seed("B", "b.com")], [v], NOW, groups=[])
    assert len(sigs) == 2 and len({s.signal_id for s in sigs}) == 2


def test_budget_exhaustion_keeps_earlier_signals() -> None:
    v = make_venue("v:p", website="https://novabar.com")

    def fake(url, **kw):
        if url == "https://b.com":
            raise BudgetExceeded("exa budget exhausted")
        return [_res("https://novabar.com/x")]

    exa = MagicMock()
    exa.find_similar.side_effect = fake
    sigs = lookalike_signals(exa, [_seed("A", "a.com"), _seed("B", "b.com")], [v], NOW, groups=[])
    assert len(sigs) == 1


def test_cli_lookalikes_fails_fast_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EXA_API_KEY", raising=False)
    with pytest.raises(SystemExit, match="EXA_API_KEY"):
        cli.lookalikes()


def test_cli_lookalikes_end_to_end_mocked(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    from scripts.hospitality.store import DocStore

    monkeypatch.setenv("EXA_API_KEY", "x")
    store = DocStore(f"sqlite:///{tmp_path}/m.db")
    v = make_venue("v:p", name="Nova", website="https://novabar.com")
    store.save("venues", [v], key=lambda x: x.venue_id)
    store.save(
        "groups",
        [Group(group_id="g:v:p", name="Nova", venue_ids=("v:p",), resolution="singleton")],
        key=lambda g: g.group_id,
    )
    seed = tmp_path / "seed.yaml"
    seed.write_text(
        "customers:\n  - {name: Carbone, website_domain: carbone.com, first_public_date: null,"
        " evidence_ref: seed}\n"
    )
    monkeypatch.setattr(cli, "SEED_PATH", seed)
    monkeypatch.setattr(cli, "DocStore", lambda: store)

    class FakeExa:
        def find_similar(self, url, **kw):
            return [_res("https://novabar.com/a")]

    monkeypatch.setattr(cli.ExaClient, "from_env", classmethod(lambda c, b: FakeExa()))
    monkeypatch.setattr(cli, "score", lambda: {"scored_groups": 1})
    out = cli.lookalikes()
    assert out["signals"] == 1 and out["seeds"] == 1
    saved = store.load("signals", Signal)
    assert [s.signal_type for s in saved] == ["lookalike"]
