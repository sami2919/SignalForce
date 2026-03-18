"""Tests for post-meeting data models."""

from __future__ import annotations

from datetime import datetime, UTC

import pytest
from pydantic import ValidationError

from scripts.models import MeetingOutcome, DealStage


class TestMeetingOutcome:
    def test_create_meeting_outcome(self):
        outcome = MeetingOutcome(
            deal_id="deal-123",
            meeting_date=datetime.now(UTC),
            attendees=["John Smith (VP Eng)", "Jane Doe (Head ML)"],
            outcome="positive",
            objections=["Concerned about integration with existing Gymnasium setup"],
            next_steps=["Send Gymnasium compatibility guide", "Schedule technical deep-dive"],
            decision_timeline="Q2 2026",
            stakeholders_needed=["CTO approval required"],
            notes="Strong interest in managed environments for RLHF",
        )
        assert outcome.outcome == "positive"
        assert len(outcome.objections) == 1
        assert len(outcome.next_steps) == 2

    def test_outcome_is_frozen(self):
        outcome = MeetingOutcome(
            deal_id="deal-123",
            meeting_date=datetime.now(UTC),
            attendees=[],
            outcome="neutral",
        )
        with pytest.raises(ValidationError):
            outcome.outcome = "positive"

    def test_default_empty_lists(self):
        outcome = MeetingOutcome(
            deal_id="deal-123",
            meeting_date=datetime.now(UTC),
            attendees=[],
            outcome="no_show",
        )
        assert outcome.objections == []
        assert outcome.next_steps == []
        assert outcome.stakeholders_needed == []
        assert outcome.follow_up_resources == []

    def test_auto_generates_id(self):
        o1 = MeetingOutcome(
            deal_id="d1", meeting_date=datetime.now(UTC), attendees=[], outcome="positive"
        )
        o2 = MeetingOutcome(
            deal_id="d2", meeting_date=datetime.now(UTC), attendees=[], outcome="negative"
        )
        assert o1.id != o2.id
        assert len(o1.id) == 36  # UUID format

    def test_recorded_at_defaults_to_now(self):
        outcome = MeetingOutcome(
            deal_id="d1", meeting_date=datetime.now(UTC), attendees=[], outcome="positive"
        )
        assert outcome.recorded_at is not None

    def test_new_deal_stages_exist(self):
        assert DealStage.MEETING_COMPLETED == "MEETING_COMPLETED"
        assert DealStage.PROPOSAL_SENT == "PROPOSAL_SENT"
