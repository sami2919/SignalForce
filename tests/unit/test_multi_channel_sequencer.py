"""Unit tests for multi-channel sequencing engine.

Tests written TDD-first before implementation (RED → GREEN → REFACTOR).
"""

import pytest

from scripts.models import OutreachChannel, SignalType
from scripts.multi_channel_sequencer import build_sequence, select_primary_channel


# ---------------------------------------------------------------------------
# select_primary_channel tests
# ---------------------------------------------------------------------------


def test_select_both_channels():
    channels = select_primary_channel(has_email=True, has_linkedin=True)
    assert OutreachChannel.EMAIL in channels
    assert OutreachChannel.LINKEDIN in channels
    assert len(channels) == 2


def test_select_email_only():
    channels = select_primary_channel(has_email=True, has_linkedin=False)
    assert channels == [OutreachChannel.EMAIL]


def test_select_linkedin_only():
    channels = select_primary_channel(has_email=False, has_linkedin=True)
    assert channels == [OutreachChannel.LINKEDIN]


def test_select_neither_empty():
    channels = select_primary_channel(has_email=False, has_linkedin=False)
    assert channels == []


# ---------------------------------------------------------------------------
# build_sequence — step count tests
# ---------------------------------------------------------------------------


def test_dual_channel_has_6_steps():
    channels = [OutreachChannel.EMAIL, OutreachChannel.LINKEDIN]
    steps = build_sequence(channels, SignalType.GITHUB_RL_REPO)
    assert len(steps) == 6


def test_email_only_has_3_steps():
    channels = [OutreachChannel.EMAIL]
    steps = build_sequence(channels, SignalType.GITHUB_RL_REPO)
    assert len(steps) == 3


def test_linkedin_only_has_3_steps():
    channels = [OutreachChannel.LINKEDIN]
    steps = build_sequence(channels, SignalType.GITHUB_RL_REPO)
    assert len(steps) == 3


def test_empty_channels_returns_empty():
    steps = build_sequence([], SignalType.GITHUB_RL_REPO)
    assert steps == []


# ---------------------------------------------------------------------------
# build_sequence — ordering tests
# ---------------------------------------------------------------------------


def test_steps_chronologically_ordered():
    channels = [OutreachChannel.EMAIL, OutreachChannel.LINKEDIN]
    steps = build_sequence(channels, SignalType.GITHUB_RL_REPO)
    days = [s.day for s in steps]
    assert days == sorted(days)


def test_email_only_steps_chronologically_ordered():
    channels = [OutreachChannel.EMAIL]
    steps = build_sequence(channels, SignalType.ARXIV_PAPER)
    days = [s.day for s in steps]
    assert days == sorted(days)


def test_linkedin_only_steps_chronologically_ordered():
    channels = [OutreachChannel.LINKEDIN]
    steps = build_sequence(channels, SignalType.JOB_POSTING)
    days = [s.day for s in steps]
    assert days == sorted(days)


# ---------------------------------------------------------------------------
# build_sequence — template mapping tests
# ---------------------------------------------------------------------------


def test_linkedin_template_matches_signal_github():
    channels = [OutreachChannel.LINKEDIN]
    steps = build_sequence(channels, SignalType.GITHUB_RL_REPO)
    assert all(s.template_name == "github-rl-signal" for s in steps)


def test_linkedin_template_matches_signal_arxiv():
    channels = [OutreachChannel.LINKEDIN]
    steps = build_sequence(channels, SignalType.ARXIV_PAPER)
    assert all(s.template_name == "arxiv-paper-signal" for s in steps)


def test_linkedin_template_matches_signal_hiring():
    channels = [OutreachChannel.LINKEDIN]
    steps = build_sequence(channels, SignalType.JOB_POSTING)
    assert all(s.template_name == "hiring-signal" for s in steps)


def test_linkedin_template_falls_back_to_general_for_huggingface():
    channels = [OutreachChannel.LINKEDIN]
    steps = build_sequence(channels, SignalType.HUGGINGFACE_MODEL)
    assert all(s.template_name == "general-signal" for s in steps)


def test_linkedin_template_falls_back_to_general_for_funding():
    channels = [OutreachChannel.LINKEDIN]
    steps = build_sequence(channels, SignalType.FUNDING_EVENT)
    assert all(s.template_name == "general-signal" for s in steps)


def test_email_template_matches_signal_github():
    channels = [OutreachChannel.EMAIL]
    steps = build_sequence(channels, SignalType.GITHUB_RL_REPO)
    assert all(s.template_name == "github-rl-signal" for s in steps)


def test_email_template_matches_signal_arxiv():
    channels = [OutreachChannel.EMAIL]
    steps = build_sequence(channels, SignalType.ARXIV_PAPER)
    assert all(s.template_name == "arxiv-paper-signal" for s in steps)


def test_email_template_matches_signal_hiring():
    channels = [OutreachChannel.EMAIL]
    steps = build_sequence(channels, SignalType.JOB_POSTING)
    assert all(s.template_name == "hiring-signal" for s in steps)


# ---------------------------------------------------------------------------
# build_sequence — dual channel alternates test
# ---------------------------------------------------------------------------


def test_dual_channel_alternates():
    """Dual channel sequence should alternate between EMAIL and LINKEDIN."""
    channels = [OutreachChannel.EMAIL, OutreachChannel.LINKEDIN]
    steps = build_sequence(channels, SignalType.GITHUB_RL_REPO)
    step_channels = [s.channel for s in steps]
    # Sequence must contain both channels
    assert OutreachChannel.EMAIL in step_channels
    assert OutreachChannel.LINKEDIN in step_channels
    # No two consecutive steps should be the same channel
    for i in range(len(step_channels) - 1):
        assert step_channels[i] != step_channels[i + 1], (
            f"Steps {i} and {i+1} both use {step_channels[i]} — expected alternation"
        )


# ---------------------------------------------------------------------------
# build_sequence — action type tests
# ---------------------------------------------------------------------------


def test_dual_channel_first_step_is_email():
    channels = [OutreachChannel.EMAIL, OutreachChannel.LINKEDIN]
    steps = build_sequence(channels, SignalType.GITHUB_RL_REPO)
    assert steps[0].channel == OutreachChannel.EMAIL
    assert steps[0].action == "send_email"


def test_dual_channel_second_step_is_linkedin_connection():
    channels = [OutreachChannel.EMAIL, OutreachChannel.LINKEDIN]
    steps = build_sequence(channels, SignalType.GITHUB_RL_REPO)
    assert steps[1].channel == OutreachChannel.LINKEDIN
    assert steps[1].action == "connection_request"


def test_linkedin_only_first_step_is_connection_request():
    channels = [OutreachChannel.LINKEDIN]
    steps = build_sequence(channels, SignalType.GITHUB_RL_REPO)
    assert steps[0].action == "connection_request"


def test_dual_channel_day_0_is_email():
    channels = [OutreachChannel.EMAIL, OutreachChannel.LINKEDIN]
    steps = build_sequence(channels, SignalType.GITHUB_RL_REPO)
    assert steps[0].day == 0
    assert steps[0].channel == OutreachChannel.EMAIL


def test_dual_channel_linkedin_connection_on_day_1():
    channels = [OutreachChannel.EMAIL, OutreachChannel.LINKEDIN]
    steps = build_sequence(channels, SignalType.GITHUB_RL_REPO)
    linkedin_connection = next(s for s in steps if s.action == "connection_request")
    assert linkedin_connection.day == 1


# ---------------------------------------------------------------------------
# build_sequence — immutability / frozen model test
# ---------------------------------------------------------------------------


def test_sequence_steps_are_frozen():
    channels = [OutreachChannel.EMAIL]
    steps = build_sequence(channels, SignalType.GITHUB_RL_REPO)
    from pydantic import ValidationError

    with pytest.raises((TypeError, ValidationError)):
        steps[0].day = 99  # type: ignore[misc]
