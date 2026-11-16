"""Tests for hospitality domain models."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from scripts.hospitality.models import EntityLink, ScoredAccount, Signal


def test_signal_is_frozen() -> None:
    s = Signal(
        signal_id="s1",
        signal_type="license_pending",
        entity_id="v:1",
        observed_at=datetime(2026, 11, 1, tzinfo=UTC),
        occurred_at=None,
        source="sla_pending",
        evidence_ref="sla:123",
        detail="pending",
    )
    with pytest.raises(ValidationError):
        s.detail = "x"


def test_entity_link_probability_bounds() -> None:
    with pytest.raises(ValidationError):
        EntityLink(left_id="a", right_id="b", kind="possibly_same", probability=1.2, method="m")


def test_scored_account_roundtrips_json() -> None:
    acc = ScoredAccount(
        group_id="g:1",
        p_window=0.5,
        fit=0.4,
        relationship=1.0,
        priority=0.35,
        contributions=(),
        disqualified_reason=None,
        is_customer=False,
    )
    assert ScoredAccount.model_validate_json(acc.model_dump_json()) == acc
