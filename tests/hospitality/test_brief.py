"""The presentable account brief: summary, signals with hypotheses, case studies, evidence."""

from datetime import date
from pathlib import Path

from scripts.hospitality.brief import build_brief, evidence_link, hypothesis
from scripts.hospitality.config import load_config
from scripts.hospitality.models import Contribution, Group, Signal
from scripts.hospitality.store import DocStore
from tests.hospitality.factories import make_scored, make_signal, make_venue

TODAY = date(2026, 11, 20)


def _contrib(sig: Signal, value: float) -> Contribution:
    return Contribution(signal_id=sig.signal_id, signal_type=sig.signal_type, precision=0.3,
                        weight=1.0, contribution=value)  # fmt: skip


def _store(tmp_path: Path) -> DocStore:
    store = DocStore(f"sqlite:///{tmp_path}/m.db")
    venues = [
        make_venue("v:a", name="Zephyr Hall", group_id="g:a", address="1 Main St", zip_code="10012"),
        make_venue("v:b", name="Quill Room", group_id="g:b", address="2 Elm St", zip_code="11211"),
        make_venue("v:c", name="Moth Bistro", group_id="g:c"),
    ]  # fmt: skip
    store.save("venues", venues, key=lambda v: v.venue_id)
    store.save("groups", [Group(group_id=g, name=n, venue_ids=(v,), resolution="singleton")
                          for g, n, v in (("g:a", "Zephyr Group", "v:a"),
                                          ("g:b", "Quill Group", "v:b"),
                                          ("g:c", "Moth Group", "v:c"))],
               key=lambda g: g.group_id)  # fmt: skip
    lic = make_signal("license_issued", "v:a", evidence_ref="sla_active:0340-26-140129")
    ev = make_signal("private_events", "v:b", evidence_ref="https://quill.test/events")
    store.save("license_signals", [lic], key=lambda s: s.signal_id)
    store.save("signals", [ev], key=lambda s: s.signal_id)
    store.save(
        "scores",
        [make_scored("g:a", 0.5, contributions=(_contrib(lic, 0.3),)),
         make_scored("g:b", 0.3, contributions=(_contrib(ev, 0.15),)),
         make_scored("g:c", 0.9, is_customer=True)],
        key=lambda a: a.group_id,
    )  # fmt: skip
    return store


def _build(tmp_path: Path, store: DocStore, top: int = 25) -> str:
    seed = tmp_path / "seed.yaml"
    seed.write_text("customers:\n  - name: Moth Group\n    website_domain: null\n"
                    "    first_public_date: null\n    evidence_ref: https://x.test\n"
                    "dismissed_embeds: []\n")  # fmt: skip
    path = build_brief(store, load_config(), tmp_path / "out", seed_path=seed, top=top,
                       today=TODAY)  # fmt: skip
    assert path.parent == tmp_path / "out" and path.name == "demo_brief.md"
    return path.read_text(encoding="utf-8")


def test_accounts_in_rank_order_and_customers_excluded(tmp_path) -> None:
    text = _build(tmp_path, _store(tmp_path))
    assert text.index("Zephyr Group") < text.index("Quill Group")
    assert "Moth Group" not in text


def test_each_account_has_the_four_parts(tmp_path) -> None:
    text = _build(tmp_path, _store(tmp_path))
    block = text.split("## 1. Zephyr Hall", 1)[1].split("## 2.", 1)[0]
    for part in ("**Summary**", "**Signals and why they matter**", "**Case studies to cite**",
                 "**Evidence**"):  # fmt: skip
        assert part in block


def test_every_signal_type_has_a_hypothesis_and_unknown_types_get_a_fallback() -> None:
    for t in ("license_pending", "license_issued", "opening_soon", "new_gm", "new_chef",
              "guest_role_hire", "events_role_hire", "staffing_change", "hiring_burst",
              "stack_fragmented", "private_events", "tripleseat_resy", "platform_switch",
              "press_opening", "lookalike"):  # fmt: skip
        assert len(hypothesis(t)) > 20
    assert hypothesis("something_new")


def test_events_signal_picks_the_private_events_case_study(tmp_path) -> None:
    text = _build(tmp_path, _store(tmp_path))
    quill = text.split("Quill Group", 1)[1]
    assert "High Street Hospitality Group" in quill
    assert "https://www.eatloyalist.com/customer-stories/" in quill


def test_evidence_links_point_at_the_public_record() -> None:
    assert evidence_link("sla_active:0340-26-140129") == (
        "https://data.ny.gov/resource/9s3h-dpkz.json?licensepermitid=0340-26-140129"
    )
    assert evidence_link("sla_pending:NA-0340-26-117413") == (
        "https://data.ny.gov/resource/f8i8-k2gm.json?application_id=NA-0340-26-117413"
    )
    assert evidence_link("sla_inactive:0340-17-1") == (
        "https://data.ny.gov/resource/6dg3-2z7i.json?license_permit_id=0340-17-1"
    )
    assert evidence_link("https://x.test/a") == "https://x.test/a"


def test_top_limits_the_number_of_accounts(tmp_path) -> None:
    text = _build(tmp_path, _store(tmp_path), top=1)
    assert "## 1. Zephyr Hall" in text and "## 2." not in text


def test_cli_brief_writes_to_the_out_dir(tmp_path, monkeypatch, capsys) -> None:
    from scripts.hospitality import cli

    store = _store(tmp_path)
    monkeypatch.setattr(cli, "DocStore", lambda: store)
    monkeypatch.setattr(cli, "OUT_DIR", tmp_path / "out")
    seed = tmp_path / "seed.yaml"
    seed.write_text("customers: []\ndismissed_embeds: []\n")
    monkeypatch.setattr(cli, "SEED_PATH", seed)
    assert cli.main(["brief", "--top", "2"]) == 0
    assert (tmp_path / "out" / "demo_brief.md").exists()
    assert "demo_brief.md" in capsys.readouterr().out


def _with_registry(store: DocStore) -> DocStore:
    from scripts.hospitality.models import LicenseRecord, RegistryRecord, StackObservation
    from scripts.hospitality.sources.registry import RECORDS, normalize_company
    from tests.hospitality.factories import make_license

    venues = {v.venue_id: v for v in store.load("venues", __import__(
        "scripts.hospitality.models", fromlist=["Venue"]).Venue)}  # fmt: skip
    venues["v:a"] = venues["v:a"].model_copy(update={"license_ids": ("L1",)})
    store.save("venues", list(venues.values()), key=lambda v: v.venue_id)
    store.save("licenses", [make_license("L1", legal_name="Zephyr Holdings LLC")],
               key=lambda r: r.record_id)  # fmt: skip
    store.save(RECORDS, [RegistryRecord(
        name_key=normalize_company("Zephyr Holdings LLC"), legal_name="Zephyr Holdings LLC",
        found=True, dos_id="99", entity_name="ZEPHYR HOLDINGS LLC", process_name="Pat Owner",
        process_address="1 Main Street", process_address_1="1 Main Street", process_zip="10012",
    )], key=lambda r: r.name_key)  # fmt: skip
    from datetime import UTC, datetime

    store.save("stack_observations", [StackObservation(
        venue_id="v:a", url="https://zephyr.test", observed_at=datetime(2026, 11, 1, tzinfo=UTC),
        platforms=("sevenrooms",), evidence=("sevenrooms",), fetched_via="fetcher",
    )], key=lambda o: o.venue_id)  # fmt: skip
    assert LicenseRecord
    return store


def test_licence_company_is_titled_by_its_restaurant_name(tmp_path) -> None:
    text = _build(tmp_path, _store(tmp_path))
    assert "## 1. Zephyr Hall (Zephyr Group)" in text


def test_registry_person_shown_for_a_single_licence_company(tmp_path) -> None:
    text = _build(tmp_path, _with_registry(_store(tmp_path)))
    block = text.split("## 1.", 1)[1].split("## 2.", 1)[0]
    assert "Pat Owner" in block and "dos_id=99" in block


def test_sevenrooms_venue_is_flagged_as_a_displacement_sale(tmp_path) -> None:
    text = _build(tmp_path, _with_registry(_store(tmp_path)))
    block = text.split("## 1.", 1)[1].split("## 2.", 1)[0]
    assert "displacement" in block
