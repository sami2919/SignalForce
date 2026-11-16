from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from scripts.hospitality import cli
from scripts.hospitality.messages import drafter
from scripts.hospitality.messages import judge as judge_mod
from scripts.hospitality.messages.drafter import choose_angles, draft, grounding_check
from scripts.hospitality.messages.judge import judge
from scripts.hospitality.models import (
    Contact,
    Draft,
    DraftSentence,
    Group,
    Judgement,
)
from scripts.hospitality.store import DocStore
from tests.hospitality.factories import make_embed_label, make_scored, make_signal, make_venue


def make_draft(sentences: tuple[DraftSentence, ...], **kw: object) -> Draft:
    base: dict[str, object] = {
        "draft_id": "d:1",
        "group_id": "g:1",
        "contact_id": None,
        "angle": "opening",
        "subject": "Oriana",
        "sentences": sentences,
    }
    base.update(kw)
    return Draft(**base)  # type: ignore[arg-type]


def fake_llm_judgement(score: float = 9.0) -> judge_mod.LLMJudgement:
    return judge_mod.LLMJudgement(
        score=score,
        hyper_specific=True,
        factually_grounded=True,
        non_obvious=True,
        deletion_reason="",
        what_would_make_me_reply="a question about timing",
    )


ACCOUNT = ("ORIANA", "174 MOTT ST", "Ana Reyes", "Owner")  # the account's own names + contact
LICENSE = make_signal(
    "license_issued",
    "v:o",
    signal_id="a",
    observed_at=datetime(2026, 4, 7, tzinfo=UTC),
    detail="issued 2026-04-07",
    evidence_ref="sla_active:0340-26-1",
)
STACK = make_signal("stack_fragmented", "g:1", signal_id="s", detail="resy + tripleseat")


def check(d: Draft, evidence=(LICENSE, STACK), account=ACCOUNT) -> tuple[str, ...]:
    return grounding_check(d, evidence, account_text=account)


def test_claim_without_evidence_fails_grounding() -> None:
    d = make_draft(
        (DraftSentence(text="You opened Oriana in April.", evidence_ids=(), is_claim=True),)
    )
    assert "sentence 0: claim without evidence" in check(d)


def test_unknown_evidence_id_fails_grounding() -> None:
    d = make_draft((DraftSentence(text="x", evidence_ids=("made-up",), is_claim=True),))
    assert check(d) == ("sentence 0: unknown evidence id made-up",)


def test_grounded_draft_and_non_claim_question_pass_grounding() -> None:
    d = make_draft(
        (
            DraftSentence(
                text="Hi Ana, Oriana's license was issued on April 7, 2026.",
                evidence_ids=("a",),
                is_claim=True,
            ),
            DraftSentence(
                text="You run Resy and Tripleseat side by side.",
                evidence_ids=("s",),
                is_claim=True,
            ),
            DraftSentence(text="How are you handling it?", evidence_ids=(), is_claim=False),
        )
    )
    assert check(d) == ()


# I4: the deterministic layer reads the text and the subject, whatever the model says is_claim is.
def test_made_up_venue_in_a_non_claim_sentence_fails() -> None:
    d = make_draft(
        (DraftSentence(text="Congrats on the Tribeca opening.", evidence_ids=(), is_claim=False),)
    )
    assert check(d) == ("sentence 0: 'Tribeca' is not in its cited evidence or the account",)


def test_made_up_number_with_a_real_citation_fails() -> None:
    d = make_draft(
        (
            DraftSentence(
                text="Your license for the third location was issued in April.",
                evidence_ids=("a",),
                is_claim=True,
            ),
        )
    )
    assert check(d) == ("sentence 0: 'third' is not in its cited evidence or the account",)


def test_made_up_figure_and_date_fail() -> None:
    d = make_draft(
        (
            DraftSentence(
                text="Your 40 covers a night since May 2026 add up.",
                evidence_ids=("a",),
                is_claim=True,
            ),
        )
    )
    assert check(d) == (
        "sentence 0: '40' is not in its cited evidence or the account",
        "sentence 0: 'May' is not in its cited evidence or the account",
    )


def test_claim_hidden_in_the_subject_fails() -> None:
    d = make_draft(
        (DraftSentence(text="How are guests finding you?", evidence_ids=(), is_claim=False),),
        subject="Your Tribeca opening",
    )
    assert check(d) == ("subject: 'Tribeca' is not in its cited evidence or the account",)


def test_subject_may_use_facts_the_body_cites() -> None:
    d = make_draft(
        (DraftSentence(text="Oriana got its license.", evidence_ids=("a",), is_claim=True),),
        subject="Oriana, licensed April 2026",
    )
    assert check(d) == ()


def test_a_fact_from_evidence_the_sentence_does_not_cite_fails() -> None:
    d = make_draft(
        (
            DraftSentence(text="You moved to Resy.", evidence_ids=("a",), is_claim=True),
        )  # Resy is in STACK, but the sentence cites only the license
    )
    assert check(d) == ("sentence 0: 'Resy' is not in its cited evidence or the account",)


def test_lowercase_platform_name_and_relative_dates_are_facts() -> None:
    d = make_draft(
        (
            DraftSentence(text="saw you are on opentable now.", evidence_ids=(), is_claim=False),
            DraftSentence(
                text="Your opening next month looks busy.", evidence_ids=("a",), is_claim=True
            ),
        )
    )
    assert check(d) == (
        "sentence 0: 'opentable' is not in its cited evidence or the account",
        "sentence 1: 'next month' is a relative date the evidence cannot support",
    )


def test_account_text_is_a_required_argument() -> None:
    d = make_draft((DraftSentence(text="x", evidence_ids=(), is_claim=False),))
    with pytest.raises(TypeError):
        grounding_check(d, [LICENSE])  # type: ignore[call-arg]


def test_judge_never_passes_with_violations() -> None:
    d = make_draft((DraftSentence(text="x", evidence_ids=(), is_claim=True),))
    with patch.object(judge_mod, "structured", return_value=fake_llm_judgement(9.5)):
        j = judge(d, [], account_text=ACCOUNT, pass_score=7.0)
    assert j.passed is False
    assert j.grounding_violations == ("sentence 0: claim without evidence",)
    assert j.factually_grounded is False


def test_judge_catches_unknown_id_before_llm_runs() -> None:
    d = make_draft((DraftSentence(text="x", evidence_ids=("nope",), is_claim=True),))
    with patch.object(judge_mod, "structured") as llm:
        j = judge(d, [make_signal("press_opening")], account_text=ACCOUNT, pass_score=7.0)
    llm.assert_not_called()  # deterministic layer first; no LLM spend on a fabricated draft
    assert j.passed is False and j.score == 0.0


def test_judge_catches_a_made_up_venue_before_llm_runs() -> None:
    d = make_draft((DraftSentence(text="Congrats on Tribeca.", evidence_ids=(), is_claim=False),))
    with patch.object(judge_mod, "structured") as llm:
        j = judge(d, [LICENSE], account_text=ACCOUNT, pass_score=7.0)
    llm.assert_not_called()
    assert j.passed is False and j.grounding_violations


def test_judge_passes_grounded_draft_at_threshold() -> None:
    sig = make_signal("press_opening")
    d = make_draft((DraftSentence(text="x", evidence_ids=(sig.signal_id,), is_claim=True),))
    with patch.object(judge_mod, "structured", return_value=fake_llm_judgement(7.0)):
        assert judge(d, [sig], account_text=ACCOUNT, pass_score=7.0).passed is True
    with patch.object(judge_mod, "structured", return_value=fake_llm_judgement(6.9)):
        assert judge(d, [sig], account_text=ACCOUNT, pass_score=7.0).passed is False


def test_choose_angles_maps_signal_families() -> None:
    sigs = [
        make_signal("license_pending", "v:1"),
        make_signal("new_gm", "v:2"),
        make_signal("stack_fragmented", "v:3"),
        make_signal("alumni_edge", "v:4"),
        make_signal("tripleseat_resy", "v:5"),
    ]
    assert choose_angles(sigs) == [
        "opening",
        "people_change",
        "platform_switch",
        "relationship",
        "private_events",
    ]
    assert choose_angles([make_signal("role_hire"), make_signal("platform_switch")]) == [
        "people_change",
        "platform_switch",
    ]
    assert choose_angles([make_signal("lookalike")]) == []


def test_draft_uses_structured_with_voice_rules_and_never_drafts_for_customers() -> None:
    sig = make_signal("press_opening")
    out = drafter.DraftOut(
        subject="Oriana",
        sentences=(DraftSentence(text="You opened Oriana.", evidence_ids=("a",), is_claim=True),),
    )
    contact = Contact(
        contact_id="c:1",
        group_id="g:1",
        name="Ana Reyes",
        role="Owner",
        email=None,
        email_confidence=None,
        instagram=None,
        phone=None,
        source="team_page",
        evidence_ref="u",
    )
    with patch.object(drafter, "structured", return_value=out) as llm:
        d = draft(make_scored("g:1"), [sig], contact, "opening")
    kw = llm.call_args.kwargs
    assert kw["role"] == "draft"
    assert "4 sentences" in kw["system"] and "never invent numbers" in kw["system"].lower()
    assert sig.signal_id in kw["user"]
    assert d.contact_id == "c:1" and d.angle == "opening" and d.group_id == "g:1"
    for acct in (
        make_scored("g:1", is_customer=True),
        make_scored("g:1", disqualified_reason="contract_foodservice"),
    ):
        with patch.object(drafter, "structured") as llm2, pytest.raises(ValueError):
            draft(acct, [sig], None, "opening")
        llm2.assert_not_called()


def test_draft_command_fails_fast_without_key(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(SystemExit) as exc:
        cli.main(["draft", "--top", "3"])
    assert "ANTHROPIC_API_KEY" in str(exc.value)


def test_draft_command_drafts_prospects_only_saves_and_reports(
    tmp_path, monkeypatch, capsys
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    store = DocStore(f"sqlite:///{tmp_path}/m.db")
    gk = lambda x: x.group_id
    store.save(
        "groups",
        [
            Group(group_id=g, name=g, venue_ids=(f"v:{g}",), resolution="singleton")
            for g in ("g:a", "g:c")
        ],
        key=gk,
    )
    store.save(
        "venues",
        [make_venue(f"v:{g}", group_id=g) for g in ("g:a", "g:c")],
        key=lambda v: v.venue_id,
    )
    store.save(
        "scores", [make_scored("g:a", 0.9), make_scored("g:c", 0.99, is_customer=True)], key=gk
    )
    # The gate reads evidence, not the stored flag: g:c's venue has an embed label.
    store.save("customer_labels", [make_embed_label("v:g:c")], key=lambda c: "c")
    store.save(
        "signals",
        [
            make_signal("press_opening", "v:g:a"),
            make_signal("new_gm", "v:g:a"),
            make_signal("press_opening", "v:g:c"),
        ],
        key=lambda s: s.signal_id,
    )
    monkeypatch.setattr(cli, "DocStore", lambda: store)
    seen: list[tuple[str, str]] = []

    def fake_draft(account, evidence, contact, angle):
        seen.append((account.group_id, angle))
        ids = (evidence[0].signal_id,)
        return make_draft(
            (DraftSentence(text="x", evidence_ids=ids, is_claim=True),),
            draft_id=f"d:{account.group_id}:{angle}",
            group_id=account.group_id,
            angle=angle,
        )

    monkeypatch.setattr(cli, "draft", fake_draft)
    judged_with: list[tuple[str, ...]] = []

    def fake_judge(d, ev, *, account_text, pass_score):
        judged_with.append(tuple(account_text))
        return Judgement(
            score=8.0,
            hyper_specific=True,
            factually_grounded=True,
            non_obvious=True,
            deletion_reason="",
            what_would_make_me_reply="",
            grounding_violations=(),
            passed=True,
        )

    monkeypatch.setattr(cli, "judge", fake_judge)
    out = cli.draft_command(top=10)
    assert seen == [("g:a", "opening"), ("g:a", "people_change")]  # the customer g:c is skipped
    assert out["drafts"] == 2 and out["passed"] == 2
    # The grounding check is given the account's own names (group and venues) to trace names to.
    assert judged_with and all("g:a" in names and "Acme" in names for names in judged_with)
    assert len(store.load("drafts", Draft)) == 2
    assert len(store.load("judgements", Judgement)) == 2
    assert cli.main(["draft", "--top", "10"]) == 0
    assert "pass rate" in capsys.readouterr().out


# I4 (quality pass): a cited date may support that date, never its parts as free-standing numbers.
@pytest.mark.parametrize(
    "text",
    [
        "Your 4 locations keep growing.",  # 4 = the license's month (2026-04-07)
        "Seven years in, you are still busy.",  # 7 = its day
        "Your 7 venues share one guest list.",
        "Your 26 seats fill fast.",  # 26 sits in the evidence ref sla_active:0340-26-1
        "Oriana's license was issued on April 9.",  # April is right, the day is not
        "Oriana's license was issued on 4/9.",
    ],
)
def test_numbers_hidden_in_a_cited_date_or_record_id_fail(text: str) -> None:
    d = make_draft((DraftSentence(text=text, evidence_ids=("a",), is_claim=True),))
    assert check(d), text


@pytest.mark.parametrize(
    "text",
    [
        "Oriana's license was issued on April 7, 2026.",
        "Oriana's license was issued on April 7th.",
        "Oriana's license was issued on 7 April 2026.",
        "Oriana's license was issued on 4/7/2026.",
        "Oriana's license was issued on 2026-04-07.",
        "Oriana was licensed in April 2026.",
    ],
)
def test_a_cited_date_written_any_usual_way_passes(text: str) -> None:
    d = make_draft((DraftSentence(text=text, evidence_ids=("a",), is_claim=True),))
    assert check(d) == (), text


def test_draft_command_keeps_judged_drafts_when_a_later_call_errors(tmp_path, monkeypatch) -> None:
    """M12: an LLMRefusal or API error mid-run must not lose the drafts already paid for."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    store = DocStore(f"sqlite:///{tmp_path}/m.db")
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
        [make_venue(f"v:{g}", group_id=g) for g in ("g:a", "g:b")],
        key=lambda v: v.venue_id,
    )
    store.save(
        "scores", [make_scored("g:a", 0.9), make_scored("g:b", 0.8)], key=lambda x: x.group_id
    )
    store.save(
        "signals",
        [make_signal("press_opening", "v:g:a"), make_signal("press_opening", "v:g:b")],
        key=lambda s: s.signal_id,
    )
    monkeypatch.setattr(cli, "DocStore", lambda: store)

    def fake_draft(account, evidence, contact, angle):
        if account.group_id == "g:b":
            raise RuntimeError("refused")
        return make_draft(
            (DraftSentence(text="x", evidence_ids=(evidence[0].signal_id,), is_claim=True),),
            draft_id=f"d:{account.group_id}:{angle}",
            group_id=account.group_id,
            angle=angle,
        )

    def fake_judge(d, ev, *, account_text, pass_score):
        return Judgement(
            score=8.0,
            hyper_specific=True,
            factually_grounded=True,
            non_obvious=True,
            deletion_reason="",
            what_would_make_me_reply="",
            grounding_violations=(),
            passed=True,
        )

    monkeypatch.setattr(cli, "draft", fake_draft)
    monkeypatch.setattr(cli, "judge", fake_judge)
    with pytest.raises(RuntimeError, match="refused"):
        cli.draft_command(top=2)
    assert [d.draft_id for d in store.load("drafts", Draft)] == ["d:g:a:opening"]
    assert len(store.load("judgements", Judgement)) == 1
