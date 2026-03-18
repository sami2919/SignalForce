"""Recency decay functions for signal freshness weighting.

Signal value decays exponentially over time using the formula:
    decay_factor = 2^(-age_days / half_life)

Different signal types decay at different rates:
- GitHub commits: 5-day half-life (code activity is time-sensitive)
- LinkedIn activity: 2-day half-life (the 48-hour window)
- Job postings: 10-day half-life (hiring cycles are slower)
- ArXiv papers: 10-day half-life (research remains relevant longer)
- Funding events: 21-day half-life (post-funding windows last months)
- HF model uploads: 7-day half-life
"""

from __future__ import annotations

import math
from datetime import datetime


class SignalHalfLife:
    """Half-life in days for each signal type."""

    GITHUB_RL_REPO = 5
    ARXIV_PAPER = 10
    JOB_POSTING = 10
    HUGGINGFACE_MODEL = 7
    FUNDING_EVENT = 21
    LINKEDIN_ACTIVITY = 2


def calculate_decay_factor(
    signal_time: datetime,
    now: datetime,
    half_life_days: float,
) -> float:
    """Calculate exponential decay factor based on signal age.

    Returns float between 0.0 and 1.0.
    """
    age_seconds = (now - signal_time).total_seconds()
    if age_seconds <= 0:
        return 1.0
    age_days = age_seconds / 86400
    return math.pow(2, -age_days / half_life_days)


def apply_recency_weight(
    signal_strength: int | float,
    signal_time: datetime,
    now: datetime,
    half_life_days: float,
) -> float:
    """Multiply signal strength by its recency decay factor."""
    decay = calculate_decay_factor(signal_time, now, half_life_days)
    return signal_strength * decay
