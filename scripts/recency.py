"""Recency decay functions for signal freshness weighting.

Signal value decays exponentially over time using the formula:
    decay_factor = 2^(-age_days / half_life)

Half-life values are signal-type-specific and come from the SignalForce
configuration (scoring.half_lives_days). Pass the appropriate half_life_days
value when calling calculate_decay_factor or apply_recency_weight.
"""

from __future__ import annotations

import math
from datetime import datetime


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
