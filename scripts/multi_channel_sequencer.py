"""Multi-channel sequencing engine.

Determines which channels to use and in what order for each prospect.

Timing (dual channel):
- Day 0: Email 1
- Day 1: LinkedIn connection request
- Day 3: Email 2
- Day 4: LinkedIn follow-up (if connected)
- Day 7: Email 3 (break-up)
- Day 8: LinkedIn second follow-up
"""

from __future__ import annotations

from scripts.models import OutreachChannel, SequenceStep


def select_primary_channel(has_email: bool, has_linkedin: bool) -> list[OutreachChannel]:
    """Determine available channels based on contact data."""
    channels = []
    if has_email:
        channels.append(OutreachChannel.EMAIL)
    if has_linkedin:
        channels.append(OutreachChannel.LINKEDIN)
    return channels


# Template mapping: signal_type → {channel → template_name}
_TEMPLATE_MAP: dict[str, dict[OutreachChannel, str]] = {
    "github": {
        OutreachChannel.EMAIL: "github-signal",
        OutreachChannel.LINKEDIN: "github-signal",
    },
    "arxiv": {
        OutreachChannel.EMAIL: "arxiv-paper-signal",
        OutreachChannel.LINKEDIN: "arxiv-paper-signal",
    },
    "jobs": {
        OutreachChannel.EMAIL: "hiring-signal",
        OutreachChannel.LINKEDIN: "hiring-signal",
    },
    "huggingface": {
        OutreachChannel.EMAIL: "huggingface-model-signal",
        OutreachChannel.LINKEDIN: "general-signal",
    },
    "funding": {
        OutreachChannel.EMAIL: "funding-signal",
        OutreachChannel.LINKEDIN: "general-signal",
    },
    "linkedin": {
        OutreachChannel.EMAIL: "general-signal",
        OutreachChannel.LINKEDIN: "general-signal",
    },
}


def build_sequence(
    channels: list[OutreachChannel],
    signal_type: str,
) -> list[SequenceStep]:
    """Build a staggered multi-channel outreach sequence."""
    if not channels:
        return []

    email_template = _TEMPLATE_MAP.get(signal_type, {}).get(OutreachChannel.EMAIL, "general-signal")
    linkedin_template = _TEMPLATE_MAP.get(signal_type, {}).get(
        OutreachChannel.LINKEDIN, "general-signal"
    )

    has_email = OutreachChannel.EMAIL in channels
    has_linkedin = OutreachChannel.LINKEDIN in channels

    steps: list[SequenceStep]

    if has_email and has_linkedin:
        # Dual channel: staggered
        steps = [
            SequenceStep(
                day=0,
                channel=OutreachChannel.EMAIL,
                action="send_email",
                template_name=email_template,
                variant="problem_focused",
            ),
            SequenceStep(
                day=1,
                channel=OutreachChannel.LINKEDIN,
                action="connection_request",
                template_name=linkedin_template,
                variant="signal_reference",
            ),
            SequenceStep(
                day=3,
                channel=OutreachChannel.EMAIL,
                action="send_email",
                template_name=email_template,
                variant="outcome_focused",
            ),
            SequenceStep(
                day=4,
                channel=OutreachChannel.LINKEDIN,
                action="follow_up_message",
                template_name=linkedin_template,
            ),
            SequenceStep(
                day=7,
                channel=OutreachChannel.EMAIL,
                action="send_email",
                template_name=email_template,
                variant="break_up",
            ),
            SequenceStep(
                day=8,
                channel=OutreachChannel.LINKEDIN,
                action="follow_up_message",
                template_name=linkedin_template,
            ),
        ]
    elif has_email:
        steps = [
            SequenceStep(
                day=0,
                channel=OutreachChannel.EMAIL,
                action="send_email",
                template_name=email_template,
                variant="problem_focused",
            ),
            SequenceStep(
                day=3,
                channel=OutreachChannel.EMAIL,
                action="send_email",
                template_name=email_template,
                variant="outcome_focused",
            ),
            SequenceStep(
                day=7,
                channel=OutreachChannel.EMAIL,
                action="send_email",
                template_name=email_template,
                variant="break_up",
            ),
        ]
    else:
        # LinkedIn only
        steps = [
            SequenceStep(
                day=0,
                channel=OutreachChannel.LINKEDIN,
                action="connection_request",
                template_name=linkedin_template,
                variant="signal_reference",
            ),
            SequenceStep(
                day=3,
                channel=OutreachChannel.LINKEDIN,
                action="follow_up_message",
                template_name=linkedin_template,
            ),
            SequenceStep(
                day=7,
                channel=OutreachChannel.LINKEDIN,
                action="follow_up_message",
                template_name=linkedin_template,
            ),
        ]

    return steps
