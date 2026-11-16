import logging
from unittest.mock import Mock

import pytest
import requests

from scripts.hospitality import cli
from scripts.hospitality.budget import BudgetExceeded, CallBudget
from scripts.hospitality.contacts import clay
from scripts.hospitality.contacts.clay import (
    ClayPushError,
    clay_rows,
    import_clay_csv,
    merge_contact,
    push_to_clay,
)
from scripts.hospitality.models import Contact, Contribution, Group
from scripts.hospitality.store import DocStore
from tests.hospitality.factories import make_scored, make_venue

URL = "https://api.clay.com/v3/sources/webhook/secret-token-123"


def contrib(sig: str, value: float) -> Contribution:
    return Contribution(
        signal_id=f"s:{sig}", signal_type=sig, precision=0.5, weight=1.0, contribution=value
    )


def mk_contact(group_id: str = "g:1", name: str = "Ana Reyes", **kw: object) -> Contact:
    base: dict[str, object] = {
        "contact_id": clay._contact_id(group_id, name),
        "group_id": group_id,
        "name": name,
        "role": "Owner",
        "email": None,
        "email_confidence": None,
        "instagram": None,
        "phone": None,
        "source": "team_page",
        "evidence_ref": "https://acme.com/team",
    }
    base.update(kw)
    return Contact(**base)  # type: ignore[arg-type]


def test_row_shape_includes_top_evidence_and_best_contact() -> None:
    acct = make_scored(
        "g:1", 0.7, contributions=(contrib("a", 0.1), contrib("license_pending", 0.4))
    )
    venues = [make_venue("v:1", name="Acme", website="https://www.acme.com/x", group_id="g:1")]
    contacts = [
        mk_contact(name="Zed Chef", role="Chef"),
        mk_contact(name="Ana Reyes", role="Owner", email="ana@acme.com"),
    ]
    (row,) = clay_rows([acct], venues, contacts)
    assert row["group_id"] == "g:1" and row["name"] == "Acme" and row["domain"] == "acme.com"
    assert row["priority"] == "0.700"
    assert row["top_evidence"].startswith("license_pending=0.40")
    assert row["contact_name"] == "Ana Reyes" and row["contact_email"] == "ana@acme.com"
    assert all(isinstance(v, str) for v in row.values())


def test_customers_and_disqualified_are_never_pushed() -> None:
    accts = [
        make_scored("g:ok", 0.5),
        make_scored("g:cust", 0.9, is_customer=True),
        make_scored("g:dq", 0.8, disqualified_reason="contract_foodservice"),
    ]
    venues = [make_venue(f"v:{g}", group_id=g) for g in ("g:ok", "g:cust", "g:dq")]
    rows = clay_rows(accts, venues, [mk_contact("g:cust")])
    assert [r["group_id"] for r in rows] == ["g:ok"]


def test_no_website_means_blank_domain() -> None:
    (row,) = clay_rows([make_scored("g:1")], [make_venue("v:1", group_id="g:1")], [])
    assert row["domain"] == "" and row["contact_email"] == ""


def test_push_spends_before_each_post_and_hard_stops(monkeypatch) -> None:
    post = Mock(return_value=Mock(status_code=200))
    monkeypatch.setattr(clay.requests, "post", post)
    budget = CallBudget("clay", 2)
    with pytest.raises(BudgetExceeded):
        push_to_clay(URL, [{"group_id": "a"}, {"group_id": "b"}, {"group_id": "c"}], budget)
    assert post.call_count == 2 and budget.used == 2
    assert post.call_args.kwargs["json"] == {"group_id": "b"}


def test_push_returns_count(monkeypatch) -> None:
    monkeypatch.setattr(clay.requests, "post", Mock(return_value=Mock(status_code=200)))
    assert push_to_clay(URL, [{"group_id": "a"}], CallBudget("clay", 5)) == 1


def test_push_requires_url() -> None:
    with pytest.raises(ValueError, match="CLAY_WEBHOOK_URL"):
        push_to_clay("", [{"group_id": "a"}], CallBudget("clay", 5))


def test_secret_url_never_in_errors_or_logs(monkeypatch, caplog) -> None:
    caplog.set_level(logging.DEBUG)
    monkeypatch.setattr(
        clay.requests, "post", Mock(return_value=Mock(status_code=500, text=f"boom {URL}"))
    )
    with pytest.raises(ClayPushError) as exc:
        push_to_clay(URL, [{"group_id": "a"}], CallBudget("clay", 5))
    assert "secret-token" not in str(exc.value) and "500" in str(exc.value)
    monkeypatch.setattr(clay.requests, "post", Mock(side_effect=requests.ConnectionError(URL)))
    with pytest.raises(ClayPushError) as exc2:
        push_to_clay(URL, [{"group_id": "a"}], CallBudget("clay", 5))
    assert "secret-token" not in str(exc2.value)
    assert "secret-token" not in repr(exc2.value.__cause__) and exc2.value.__suppress_context__
    assert "secret-token" not in caplog.text


def write_csv(tmp_path, text: str):
    p = tmp_path / "clay.csv"
    p.write_text(text, encoding="utf-8")
    return p


def test_csv_round_trip_and_stable_id(tmp_path) -> None:
    p = write_csv(
        tmp_path,
        "group_id,name,role,email,email_confidence\ng:1,Ana Reyes,Owner,ana@acme.com,88\n",
    )
    (c,) = import_clay_csv(p, known_group_ids={"g:1"})
    assert (c.group_id, c.name, c.role, c.email, c.email_confidence) == (
        "g:1",
        "Ana Reyes",
        "Owner",
        "ana@acme.com",
        88.0,
    )
    assert c.source == "clay" and c.contact_id == mk_contact().contact_id


def test_csv_is_untrusted_skip_unknown_blank_and_never_invent(tmp_path, caplog) -> None:
    p = write_csv(
        tmp_path,
        "group_id,name,role,email,extra\n"
        ",,,,\n"
        "g:zzz,Who Dis,Owner,who@x.com,1\n"
        "g:1,No Email,GM,not-an-email,1\n"
        "g:1,,Owner,a@b.com,1\n"
        "g:1,Cy Park\n",
    )
    out = import_clay_csv(p, known_group_ids={"g:1"})
    assert [(c.name, c.email) for c in out] == [("No Email", None), ("Cy Park", None)]
    assert out[1].role == "" and all(c.email_confidence is None for c in out)
    assert "g:zzz" in caplog.text


def test_csv_duplicate_rows_keep_best_and_bad_confidence_is_none(tmp_path) -> None:
    p = write_csv(
        tmp_path,
        "group_id,name,role,email,email_confidence\n"
        "g:1,Ana Reyes,Owner,ana@acme.com,60\n"
        "g:1,Ana Reyes,Owner,ana@acme.com,90\n"
        "g:1,Bo Lin,GM,bo@acme.com,lots\n",
    )
    out = {c.name: c for c in import_clay_csv(p)}
    assert out["Ana Reyes"].email_confidence == 90.0
    assert out["Bo Lin"].email == "bo@acme.com" and out["Bo Lin"].email_confidence is None


def test_merge_never_replaces_better_with_worse() -> None:
    page = mk_contact(email="ana@acme.com")
    assert merge_contact(page, mk_contact(email="other@x.com", email_confidence=95.0)) == page
    no_email = mk_contact(email=None, instagram="acme")
    filled = merge_contact(no_email, mk_contact(email="ana@x.com", email_confidence=80.0))
    assert filled.email == "ana@x.com" and filled.instagram == "acme"
    hunter = mk_contact(email="a@x.com", email_confidence=75.0)
    assert merge_contact(hunter, mk_contact(email="b@x.com", email_confidence=70.0)) == hunter
    assert merge_contact(hunter, mk_contact(email=None)) == hunter
    better = merge_contact(hunter, mk_contact(email="b@x.com", email_confidence=90.0))
    assert better.email == "b@x.com"


def setup_store(tmp_path, monkeypatch) -> DocStore:
    store = DocStore(f"sqlite:///{tmp_path}/m.db")
    key = lambda x: x.group_id
    store.save(
        "groups",
        [Group(group_id=g, name=g, venue_ids=(f"v:{g}",), resolution="singleton") for g in "ab"],
        key=key,
    )
    store.save(
        "venues",
        [make_venue(f"v:{g}", name=f"N{g}", group_id=g) for g in "ab"],
        key=lambda v: v.venue_id,
    )
    store.save(
        "scores",
        [make_scored("a", 0.9), make_scored("b", 0.8), make_scored("c", 0.99, is_customer=True)],
        key=key,
    )
    monkeypatch.setattr(cli, "DocStore", lambda: store)
    return store


def test_clay_push_command_fails_fast_without_url(monkeypatch) -> None:
    monkeypatch.delenv("CLAY_WEBHOOK_URL", raising=False)
    with pytest.raises(SystemExit) as exc:
        cli.main(["clay-push", "--top", "5"])
    assert "CLAY_WEBHOOK_URL" in str(exc.value)


def test_clay_push_command_pushes_top_prospects_only(tmp_path, monkeypatch) -> None:
    setup_store(tmp_path, monkeypatch)
    monkeypatch.setenv("CLAY_WEBHOOK_URL", URL)
    post = Mock(return_value=Mock(status_code=200))
    monkeypatch.setattr(clay.requests, "post", post)
    out = cli.clay_push(top=1)
    assert out["pushed"] == 1
    assert [c.kwargs["json"]["group_id"] for c in post.call_args_list] == ["a"]
    assert URL not in str(out)


def test_clay_import_command_saves_known_groups_without_downgrading(tmp_path, monkeypatch) -> None:
    store = setup_store(tmp_path, monkeypatch)
    store.save(
        "contacts",
        [mk_contact("a", email="ana@acme.com")],
        key=lambda c: c.contact_id,
    )
    p = write_csv(
        tmp_path,
        "group_id,name,role,email,email_confidence\n"
        "a,Ana Reyes,Owner,other@x.com,99\n"
        "a,Bo Lin,GM,bo@acme.com,80\n"
        "c,Cust Omer,Owner,c@x.com,90\n"
        "nope,Ghost,Owner,g@x.com,90\n",
    )
    out = cli.clay_import(p)
    assert out["imported"] == 2 and out["skipped"] == 2
    saved = {c.name: c for c in store.load("contacts", Contact)}
    assert saved["Ana Reyes"].email == "ana@acme.com"
    assert saved["Bo Lin"].email == "bo@acme.com" and "Cust Omer" not in saved
    assert cli.main(["clay-import", str(p)]) == 0
