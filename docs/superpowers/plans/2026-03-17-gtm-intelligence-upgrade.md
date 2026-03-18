# GTM Intelligence Upgrade — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade rl-gtm-engine from a basic signal-detection engine into a state-of-the-art GTM system that implements the playbooks used by Sendoso, Gojiberry AI, and GTMify — the companies actually doubling pipeline with AI.

**Architecture:** Three upgrade layers: (1) Intent-weighted scoring with recency decay replaces the current "all signals equal" model, (2) Blueprint/resource-first outreach replaces demo-ask templates, (3) Multi-channel sequencing adds LinkedIn alongside email. Each layer is independently valuable and builds on the existing scanner → stacker → skill pipeline.

**Tech Stack:** Python 3.11+, Pydantic v2 (extending existing models), pytest, Claude Code skills, n8n workflows

---

## Why This Upgrade

The current engine treats all signals equally and only does email. The GTM engineering community has converged on three principles that our engine violates:

1. **Timing beats targeting.** Gojiberry AI's 48-hour LinkedIn activity filter alone doubles response rates. Our scoring gives a 7-day-old GitHub commit the same weight as one from today.

2. **Resources beat demos.** Roman Czerny's "blueprint before demo" funnel gets 50% reply rates vs. our 8-15% target. Our templates all ask for 20-minute calls. Technical buyers respond to free frameworks, not meeting requests.

3. **Specialized agents beat generic templates.** GTMify's architecture uses different agents per signal+channel combination. Our single `email-writer` skill generates identical-structure emails regardless of whether someone published a paper or posted a job.

This plan addresses all three with minimal code changes to the existing foundation.

---

## File Structure Overview

### New Files
```
scripts/intent_scorer.py           — Intent-weighted scoring engine (replaces equal weighting)
scripts/recency.py                 — Time-decay functions for signal freshness
scripts/linkedin_activity.py       — LinkedIn activity signal scanner (new signal source)
scripts/multi_channel_sequencer.py — Channel routing logic (email vs. LinkedIn vs. both)
tests/unit/test_intent_scorer.py
tests/unit/test_recency.py
tests/unit/test_linkedin_activity.py
tests/unit/test_multi_channel_sequencer.py
templates/email-sequences/resource-offer-signal.md   — Blueprint/resource-first template
templates/linkedin-sequences/                         — New directory for LinkedIn templates
templates/linkedin-sequences/github-rl-signal.md
templates/linkedin-sequences/arxiv-paper-signal.md
templates/linkedin-sequences/hiring-signal.md
templates/linkedin-sequences/general-signal.md
skills/intent-scorer/SKILL.md      — Skill for running intent-weighted scoring
skills/multi-channel-writer/SKILL.md — Skill for generating multi-channel sequences
skills/resource-offer/SKILL.md     — Skill for blueprint/resource-first outreach
skills/meeting-followup/SKILL.md   — Post-meeting automation skill
```

### Modified Files
```
scripts/models.py                  — Add new enums + fields for intent scoring, channels, resources
scripts/signal_stacker.py          — Integrate intent scorer + recency decay
scripts/config.py                  — (No changes needed — LinkedIn scanner uses data input mode)
skills/email-writer/SKILL.md       — Reference new templates, integrate with multi-channel
skills/signal-scanner/SKILL.md     — Add LinkedIn activity scanner, update scoring display
templates/scoring-rubrics/icp-scoring-model.md — Update to intent-weighted formula
```

---

## Phase 1: Intent-Weighted Scoring with Recency Decay

**Why this is first:** This is the highest-leverage change. Gojiberry's data shows intent weighting at 60% vs. ICP fit at 40% dramatically improves targeting precision. Adding recency decay means a GitHub commit from today scores higher than one from 7 days ago. Together, these changes affect every downstream decision — which accounts to pursue, in what order, with what urgency.

---

### Task 1.1: Add Recency Decay Functions

**Files:**
- Create: `scripts/recency.py`
- Create: `tests/unit/test_recency.py`

**Logic:** Signal value decays exponentially over time. A signal from today is worth 1.0x, from 2 days ago 0.85x, from 5 days ago 0.5x, from 14 days ago 0.1x. The decay curve is configurable but defaults to a half-life of 5 days for fast-moving signals (GitHub, LinkedIn activity) and 14 days for slower signals (funding, papers).

The formula: `decay_factor = 2^(-age_days / half_life)`

This is the building block that the intent scorer (Task 1.2) uses.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_recency.py
"""Tests for recency decay functions."""
from __future__ import annotations

from datetime import datetime, timedelta, UTC

import pytest

from scripts.recency import (
    calculate_decay_factor,
    apply_recency_weight,
    SignalHalfLife,
)


class TestCalculateDecayFactor:
    def test_zero_age_returns_1(self):
        """Signal from right now has full value."""
        now = datetime.now(UTC)
        assert calculate_decay_factor(now, now, half_life_days=5) == pytest.approx(1.0)

    def test_one_half_life_returns_0_5(self):
        """Signal from exactly one half-life ago has 50% value."""
        now = datetime.now(UTC)
        signal_time = now - timedelta(days=5)
        assert calculate_decay_factor(signal_time, now, half_life_days=5) == pytest.approx(0.5)

    def test_two_half_lives_returns_0_25(self):
        """Signal from two half-lives ago has 25% value."""
        now = datetime.now(UTC)
        signal_time = now - timedelta(days=10)
        assert calculate_decay_factor(signal_time, now, half_life_days=5) == pytest.approx(0.25)

    def test_48_hours_fast_decay(self):
        """Signal from 48 hours ago with 5-day half-life retains ~75% value."""
        now = datetime.now(UTC)
        signal_time = now - timedelta(hours=48)
        factor = calculate_decay_factor(signal_time, now, half_life_days=5)
        assert 0.7 < factor < 0.8

    def test_14_day_slow_decay(self):
        """Funding signal from 14 days ago with 14-day half-life retains 50%."""
        now = datetime.now(UTC)
        signal_time = now - timedelta(days=14)
        assert calculate_decay_factor(signal_time, now, half_life_days=14) == pytest.approx(0.5)

    def test_negative_age_clamps_to_1(self):
        """Future signals (clock skew) should not exceed 1.0."""
        now = datetime.now(UTC)
        future = now + timedelta(hours=1)
        assert calculate_decay_factor(future, now, half_life_days=5) == pytest.approx(1.0)

    def test_very_old_signal_near_zero(self):
        """30-day-old signal with 5-day half-life is near zero."""
        now = datetime.now(UTC)
        signal_time = now - timedelta(days=30)
        factor = calculate_decay_factor(signal_time, now, half_life_days=5)
        assert factor < 0.02


class TestApplyRecencyWeight:
    def test_applies_decay_to_strength(self):
        """Signal strength is multiplied by decay factor."""
        now = datetime.now(UTC)
        signal_time = now - timedelta(days=5)
        # Half-life 5 days → decay = 0.5, strength 3 → weighted = 1.5
        result = apply_recency_weight(
            signal_strength=3, signal_time=signal_time, now=now, half_life_days=5
        )
        assert result == pytest.approx(1.5)

    def test_fresh_signal_full_strength(self):
        """Recent signal retains full strength."""
        now = datetime.now(UTC)
        result = apply_recency_weight(
            signal_strength=2, signal_time=now, now=now, half_life_days=5
        )
        assert result == pytest.approx(2.0)


class TestSignalHalfLife:
    def test_github_fast_decay(self):
        """GitHub signals use fast decay (5 days)."""
        assert SignalHalfLife.GITHUB_RL_REPO == 5

    def test_arxiv_medium_decay(self):
        """ArXiv papers use medium decay (10 days)."""
        assert SignalHalfLife.ARXIV_PAPER == 10

    def test_funding_slow_decay(self):
        """Funding events use slow decay (21 days)."""
        assert SignalHalfLife.FUNDING_EVENT == 21

    def test_job_posting_medium_decay(self):
        """Job postings use medium decay (10 days)."""
        assert SignalHalfLife.JOB_POSTING == 10

    def test_huggingface_fast_decay(self):
        """HF model uploads use fast decay (7 days)."""
        assert SignalHalfLife.HUGGINGFACE_MODEL == 7
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/unit/test_recency.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.recency'`

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/recency.py
"""Recency decay functions for signal freshness weighting.

Signal value decays exponentially over time using the formula:
    decay_factor = 2^(-age_days / half_life)

Different signal types decay at different rates:
- GitHub commits: 5-day half-life (code activity is time-sensitive)
- LinkedIn activity: 2-day half-life (the 48-hour window from Gojiberry)
- Job postings: 10-day half-life (hiring cycles are slower)
- ArXiv papers: 10-day half-life (research remains relevant longer)
- Funding events: 21-day half-life (post-funding windows last months)
- HF model uploads: 7-day half-life (model publishing is moderately time-sensitive)
"""
from __future__ import annotations

import math
from datetime import datetime


class SignalHalfLife:
    """Half-life in days for each signal type.

    Shorter half-life = signal decays faster = more time-sensitive.
    """

    GITHUB_RL_REPO = 5
    ARXIV_PAPER = 10
    JOB_POSTING = 10
    HUGGINGFACE_MODEL = 7
    FUNDING_EVENT = 21
    LINKEDIN_ACTIVITY = 2  # The 48-hour window


def calculate_decay_factor(
    signal_time: datetime,
    now: datetime,
    half_life_days: float,
) -> float:
    """Calculate exponential decay factor based on signal age.

    Args:
        signal_time: When the signal was detected/published.
        now: Current time (injected for testability).
        half_life_days: Number of days until signal loses 50% of its value.

    Returns:
        Float between 0.0 and 1.0 representing remaining signal value.
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
    """Multiply signal strength by its recency decay factor.

    Args:
        signal_strength: Raw signal strength value (1, 2, or 3).
        signal_time: When the signal was detected.
        now: Current time.
        half_life_days: Decay half-life for this signal type.

    Returns:
        Weighted signal strength (original × decay factor).
    """
    decay = calculate_decay_factor(signal_time, now, half_life_days)
    return signal_strength * decay
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/unit/test_recency.py -v`
Expected: All 12 tests PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/recency.py tests/unit/test_recency.py
git commit -m "feat: add recency decay functions for signal freshness weighting"
```

---

### Task 1.2: Build Intent-Weighted Scoring Engine

**Files:**
- Create: `scripts/intent_scorer.py`
- Create: `tests/unit/test_intent_scorer.py`

**Logic:** The current signal stacker uses `sum(strengths) × breadth_multiplier`. The new intent scorer implements Gojiberry's formula: `COMBINED_SCORE = (ICP_Fit × 0.4) + (Intent_Signal × 0.6)`. Intent gets 60% weight because timing beats targeting.

Intent signals are categorized by type with different weights:
- Publishing a paper (+3): Company has dedicated research resources to RL
- Active GitHub repo (+2-3 based on recency): Engineering investment RIGHT NOW
- Hiring RL engineers (+2): Budget allocated, team building
- HF model upload (+2): Actively using RL for training
- Funding round (+1-2): Budget available but less specific to RL
- LinkedIn activity (+3): Real-time engagement signal (highest urgency)

The intent scorer also applies recency decay from Task 1.1, so a GitHub commit from today scores higher than one from a week ago.

- [ ] **Step 1: Write the failing tests**

**NOTE:** Before implementing this task, extract the `make_signal` helper from `tests/unit/test_signal_stacker.py` into `tests/conftest.py` so all test files share a single factory function. Add an `age_days: float = 0` parameter to the shared helper.

```python
# tests/conftest.py (shared test helpers)
"""Shared test fixtures and factory functions."""
from __future__ import annotations

from datetime import datetime, timedelta, UTC

from scripts.models import Signal, SignalType, SignalStrength


def make_signal(
    signal_type: SignalType = SignalType.GITHUB_RL_REPO,
    strength: SignalStrength = SignalStrength.MODERATE,
    age_days: float = 0,
    company_name: str = "TestCo",
    company_domain: str | None = "testco.com",
) -> Signal:
    """Shared helper to create Signal objects for testing."""
    metadata = {}
    if signal_type == SignalType.GITHUB_RL_REPO:
        metadata["repo_name"] = "test-repo"
    return Signal(
        signal_type=signal_type,
        company_name=company_name,
        company_domain=company_domain,
        signal_strength=strength,
        source_url="https://example.com",
        raw_data={},
        detected_at=datetime.now(UTC) - timedelta(days=age_days),
        metadata=metadata,
    )
```

Then update `tests/unit/test_signal_stacker.py` to import from `tests.conftest` instead of defining its own `make_signal`.

```python
# tests/unit/test_intent_scorer.py
"""Tests for intent-weighted scoring engine."""
from __future__ import annotations

from datetime import datetime, timedelta, UTC

import pytest

from scripts.models import SignalType, SignalStrength, ICPScore
from scripts.intent_scorer import (
    IntentScorer,
    INTENT_WEIGHTS,
    calculate_intent_score,
    calculate_combined_score,
)
from tests.conftest import make_signal


class TestIntentWeights:
    def test_arxiv_highest_base_weight(self):
        """ArXiv papers indicate deep RL investment — highest weight."""
        assert INTENT_WEIGHTS[SignalType.ARXIV_PAPER] >= INTENT_WEIGHTS[SignalType.FUNDING_EVENT]

    def test_github_high_weight(self):
        """Active code = active investment."""
        assert INTENT_WEIGHTS[SignalType.GITHUB_RL_REPO] >= 2.0

    def test_funding_lowest_weight(self):
        """Funding is least specific to RL."""
        assert INTENT_WEIGHTS[SignalType.FUNDING_EVENT] <= INTENT_WEIGHTS[SignalType.JOB_POSTING]


class TestCalculateIntentScore:
    def test_single_fresh_strong_signal(self):
        """Fresh STRONG ArXiv signal should score high."""
        signals = [make_signal(SignalType.ARXIV_PAPER, SignalStrength.STRONG, age_days=0)]
        score = calculate_intent_score(signals)
        assert score > 7.0  # High intent

    def test_stale_signal_scores_lower(self):
        """7-day-old signal scores lower than fresh one."""
        fresh = [make_signal(SignalType.GITHUB_RL_REPO, SignalStrength.STRONG, age_days=0)]
        stale = [make_signal(SignalType.GITHUB_RL_REPO, SignalStrength.STRONG, age_days=7)]
        assert calculate_intent_score(fresh) > calculate_intent_score(stale)

    def test_multi_source_breadth_bonus(self):
        """Signals from multiple sources get breadth multiplier."""
        single = [make_signal(SignalType.GITHUB_RL_REPO, SignalStrength.MODERATE)]
        multi = [
            make_signal(SignalType.GITHUB_RL_REPO, SignalStrength.MODERATE),
            make_signal(SignalType.ARXIV_PAPER, SignalStrength.MODERATE),
        ]
        assert calculate_intent_score(multi) > calculate_intent_score(single) * 1.4

    def test_empty_signals_returns_zero(self):
        """No signals = zero intent."""
        assert calculate_intent_score([]) == 0.0


class TestCalculateCombinedScore:
    def test_intent_weighted_60_percent(self):
        """Intent should be 60% of combined score."""
        # ICP fit = 5.0, intent = 10.0
        combined = calculate_combined_score(icp_fit=5.0, intent_score=10.0)
        expected = (5.0 * 0.4) + (10.0 * 0.6)  # 2.0 + 6.0 = 8.0
        assert combined == pytest.approx(expected)

    def test_icp_weighted_40_percent(self):
        """ICP fit is 40% of combined score."""
        combined = calculate_combined_score(icp_fit=10.0, intent_score=0.0)
        assert combined == pytest.approx(4.0)

    def test_zero_both_returns_zero(self):
        assert calculate_combined_score(0.0, 0.0) == pytest.approx(0.0)


class TestIntentScorer:
    def test_score_company_with_fresh_multi_source(self):
        """Company with fresh signals from 3 sources should score A-tier."""
        scorer = IntentScorer()
        signals = [
            make_signal(SignalType.GITHUB_RL_REPO, SignalStrength.STRONG, age_days=0),
            make_signal(SignalType.ARXIV_PAPER, SignalStrength.STRONG, age_days=1),
            make_signal(SignalType.JOB_POSTING, SignalStrength.MODERATE, age_days=2),
        ]
        result = scorer.score_signals(signals, icp_fit=4.0)
        assert result.icp_score == ICPScore.A

    def test_score_company_with_stale_single_source(self):
        """Company with one stale signal should score low."""
        scorer = IntentScorer()
        signals = [
            make_signal(SignalType.FUNDING_EVENT, SignalStrength.WEAK, age_days=20),
        ]
        result = scorer.score_signals(signals, icp_fit=2.0)
        assert result.icp_score in (ICPScore.C, ICPScore.D)

    def test_returns_intent_score_and_combined(self):
        """Result should include both intent and combined scores."""
        scorer = IntentScorer()
        signals = [make_signal(SignalType.GITHUB_RL_REPO, SignalStrength.MODERATE)]
        result = scorer.score_signals(signals, icp_fit=3.0)
        assert result.intent_score > 0
        assert result.combined_score > 0
        assert result.icp_score is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/unit/test_intent_scorer.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write implementation**

```python
# scripts/intent_scorer.py
"""Intent-weighted scoring engine.

Implements the Gojiberry formula: COMBINED = (ICP_Fit × 0.4) + (Intent × 0.6)

Intent scoring applies:
1. Signal-type-specific weights (papers > code > hiring > funding)
2. Recency decay (fresh signals score higher)
3. Breadth multiplier (multi-source signals score higher)

This replaces the equal-weight model in signal_stacker.py.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, UTC

from scripts.models import ICPScore, Signal, SignalType
from scripts.recency import SignalHalfLife, apply_recency_weight


# Intent weights by signal type.
# Higher weight = stronger buying intent indicator.
INTENT_WEIGHTS: dict[SignalType, float] = {
    SignalType.ARXIV_PAPER: 3.0,        # Dedicated research resources → high intent
    SignalType.GITHUB_RL_REPO: 2.5,     # Active engineering → high intent
    SignalType.HUGGINGFACE_MODEL: 2.5,  # Using RL for training → high intent
    SignalType.JOB_POSTING: 2.0,        # Budget allocated → medium-high intent
    SignalType.FUNDING_EVENT: 1.5,      # Budget available but less RL-specific
}

# Map signal types to their decay half-lives.
_HALF_LIVES: dict[SignalType, float] = {
    SignalType.GITHUB_RL_REPO: SignalHalfLife.GITHUB_RL_REPO,
    SignalType.ARXIV_PAPER: SignalHalfLife.ARXIV_PAPER,
    SignalType.JOB_POSTING: SignalHalfLife.JOB_POSTING,
    SignalType.HUGGINGFACE_MODEL: SignalHalfLife.HUGGINGFACE_MODEL,
    SignalType.FUNDING_EVENT: SignalHalfLife.FUNDING_EVENT,
}

# Breadth multiplier (same as existing signal_stacker).
_BREADTH_MULTIPLIER: dict[int, float] = {1: 1.0, 2: 1.5, 3: 2.0}
_BREADTH_FALLBACK = 3.0

# Combined score thresholds.
_GRADE_THRESHOLDS: list[tuple[float, ICPScore]] = [
    (8.0, ICPScore.A),
    (5.0, ICPScore.B),
    (2.0, ICPScore.C),
]


@dataclass(frozen=True)
class ScoringResult:
    """Result of scoring a company's signals."""

    intent_score: float
    combined_score: float
    icp_score: ICPScore
    signal_count: int
    source_types: int


def calculate_intent_score(
    signals: list[Signal],
    now: datetime | None = None,
) -> float:
    """Calculate intent score from a list of signals.

    For each signal:
        weighted_value = strength × intent_weight × recency_decay

    Then apply breadth multiplier based on unique source types.
    """
    if not signals:
        return 0.0

    if now is None:
        now = datetime.now(UTC)

    # Calculate weighted value per signal.
    total = 0.0
    for signal in signals:
        intent_weight = INTENT_WEIGHTS.get(signal.signal_type, 1.0)
        half_life = _HALF_LIVES.get(signal.signal_type, 7.0)
        recency_weighted = apply_recency_weight(
            signal_strength=signal.signal_strength.value,
            signal_time=signal.detected_at,
            now=now,
            half_life_days=half_life,
        )
        total += recency_weighted * intent_weight

    # Apply breadth multiplier.
    unique_types = len({s.signal_type for s in signals})
    multiplier = _BREADTH_MULTIPLIER.get(unique_types, _BREADTH_FALLBACK)

    return total * multiplier


def calculate_combined_score(icp_fit: float, intent_score: float) -> float:
    """Calculate combined score using Gojiberry formula.

    COMBINED = (ICP_Fit × 0.4) + (Intent × 0.6)
    """
    return (icp_fit * 0.4) + (intent_score * 0.6)


def _determine_grade(combined_score: float) -> ICPScore:
    """Map combined score to ICP grade."""
    for threshold, grade in _GRADE_THRESHOLDS:
        if combined_score >= threshold:
            return grade
    return ICPScore.D


class IntentScorer:
    """Intent-weighted scoring engine for company signals."""

    def score_signals(
        self,
        signals: list[Signal],
        icp_fit: float,
        now: datetime | None = None,
    ) -> ScoringResult:
        """Score a company's signals using intent-weighted formula.

        Args:
            signals: All signals for a single company.
            icp_fit: ICP fit score (0-5) from the scoring rubric.
            now: Current time (defaults to now).

        Returns:
            ScoringResult with intent score, combined score, and grade.
        """
        intent = calculate_intent_score(signals, now)
        combined = calculate_combined_score(icp_fit, intent)
        grade = _determine_grade(combined)

        return ScoringResult(
            intent_score=intent,
            combined_score=combined,
            icp_score=grade,
            signal_count=len(signals),
            source_types=len({s.signal_type for s in signals}),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/unit/test_intent_scorer.py -v`
Expected: All tests PASS

- [ ] **Step 5: Run full test suite to verify no regressions**

Run: `python3 -m pytest tests/ -q`
Expected: All existing + new tests pass

- [ ] **Step 6: Commit**

```bash
git add scripts/intent_scorer.py tests/unit/test_intent_scorer.py
git commit -m "feat: add intent-weighted scoring engine with Gojiberry formula"
```

---

### Task 1.3: Update ICP Scoring Rubric

**Files:**
- Modify: `templates/scoring-rubrics/icp-scoring-model.md`

**Why:** The rubric needs to reflect the new intent-weighted formula. The old formula was `weighted_score = (signal × 0.30) + (maturity × 0.25) + (fit × 0.20) + (budget × 0.15) + (access × 0.10)`. The new formula is `COMBINED = (ICP_Fit × 0.4) + (Intent × 0.6)` where ICP_Fit consolidates the non-signal dimensions and Intent incorporates signal strength + recency + type-specific weights.

- [ ] **Step 1: Update the scoring rubric**

Add a new section at the top titled "## Updated Scoring Formula (v2)" that documents:

1. The new formula: `COMBINED_SCORE = (ICP_Fit × 0.4) + (Intent_Signal × 0.6)`

2. ICP Fit score (0-5) is calculated from:
   - RL Maturity (40% of ICP Fit)
   - Company Fit / Tier (30% of ICP Fit)
   - Budget Likelihood (20% of ICP Fit)
   - Accessibility (10% of ICP Fit)

3. Intent score is calculated from:
   - Signal strength × intent weight × recency decay × breadth multiplier
   - Intent weights: ArXiv (3.0) > GitHub (2.5) = HuggingFace (2.5) > Hiring (2.0) > Funding (1.5)
   - Recency decay: half-lives from 2 days (LinkedIn) to 21 days (funding)
   - Breadth multiplier: same as before (1.0/1.5/2.0/3.0)

4. Grade thresholds (updated): A ≥ 8.0, B ≥ 5.0, C ≥ 2.0, D < 2.0

5. Keep the old formula section but mark it as "## Legacy Scoring Formula (v1)" for reference.

6. Add a new worked example with intent scoring.

- [ ] **Step 2: Verify rubric is internally consistent**

Check: Do the weights in the ICP Fit sub-dimensions sum to 1.0? (0.40 + 0.30 + 0.20 + 0.10 = 1.00 ✓)
Check: Does the worked example math check out?

- [ ] **Step 3: Commit**

```bash
git add templates/scoring-rubrics/icp-scoring-model.md
git commit -m "docs: update ICP scoring rubric with intent-weighted formula v2"
```

---

### Task 1.4: Integrate Intent Scorer into Signal Stacker

**Files:**
- Modify: `scripts/signal_stacker.py`
- Modify: `tests/unit/test_signal_stacker.py`

**Logic:** The signal stacker currently calculates `composite_signal_score` using its own simple formula. We want it to optionally use the new IntentScorer. We add a `use_intent_scoring: bool = True` flag to `SignalStacker.__init__`. When enabled, the stacker delegates scoring to `IntentScorer`. When disabled, it uses the legacy formula (backward compatible).

**IMPORTANT:** We default to `use_intent_scoring=False` to preserve backward compatibility. Existing callers get the same behavior. New callers opt in with `use_intent_scoring=True`. This ensures all existing tests pass without modification.

- [ ] **Step 1: Write new tests**

Add to `tests/unit/test_signal_stacker.py`:

```python
class TestIntentScoringIntegration:
    def test_intent_scoring_disabled_by_default(self):
        """Backward compatibility: new stacker instances use legacy scoring by default."""
        stacker = SignalStacker()
        assert stacker.use_intent_scoring is False

    def test_intent_scoring_opt_in(self):
        """Intent scoring can be enabled explicitly."""
        stacker = SignalStacker(use_intent_scoring=True)
        assert stacker.use_intent_scoring is True

    def test_intent_scoring_produces_different_scores(self):
        """Intent-weighted scores differ from legacy equal-weight scores."""
        signals = [
            make_signal(company_name="IntentCo", signal_type=SignalType.ARXIV_PAPER),
            make_signal(company_name="IntentCo", signal_type=SignalType.GITHUB_RL_REPO),
        ]
        scan_result = ScanResult(
            scan_type=SignalType.ARXIV_PAPER,
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            signals_found=signals,
            total_raw_results=2,
            total_after_dedup=2,
        )
        intent_stacker = SignalStacker(use_intent_scoring=True)
        legacy_stacker = SignalStacker(use_intent_scoring=False)

        intent_profiles = intent_stacker.stack_signals([scan_result])
        legacy_profiles = legacy_stacker.stack_signals([scan_result])

        # Scores should differ because weighting is different
        assert intent_profiles[0].composite_signal_score != legacy_profiles[0].composite_signal_score

    def test_legacy_mode_matches_original_behavior(self):
        """Legacy mode produces same scores as before the upgrade."""
        stacker = SignalStacker(use_intent_scoring=False)
        signals = [make_signal(company_name="LegacyCo", signal_type=SignalType.GITHUB_RL_REPO)]
        scan_result = ScanResult(
            scan_type=SignalType.GITHUB_RL_REPO,
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            signals_found=signals,
            total_raw_results=1,
            total_after_dedup=1,
        )
        profiles = stacker.stack_signals([scan_result])
        # Legacy: sum(2) × multiplier(1.0) = 2.0
        assert profiles[0].composite_signal_score == pytest.approx(2.0)
```

- [ ] **Step 2: Run tests to verify they fail**

- [ ] **Step 3: Modify SignalStacker to integrate IntentScorer**

Add `use_intent_scoring` parameter to `__init__` with `default=False` (backward compatible). In `stack_signals`, branch on the flag:
- If `use_intent_scoring=True`: use `IntentScorer.score_signals()` for composite score and ICP grade
- If `use_intent_scoring=False`: use legacy `_calculate_composite_score()` and `_determine_icp_score()`

Also update `stack_from_files()` to accept an optional `use_intent_scoring` parameter.

Note: The signal-scanner skill and n8n workflows will pass `use_intent_scoring=True` explicitly.

- [ ] **Step 4: Run all tests**

Run: `python3 -m pytest tests/ -q`
Expected: All old tests pass unchanged + new tests pass

- [ ] **Step 5: Commit**

```bash
git add scripts/signal_stacker.py tests/unit/test_signal_stacker.py
git commit -m "feat: integrate intent scorer into signal stacker with legacy fallback"
```

---

## Phase 2: Blueprint/Resource-First Outreach

**Why this phase:** The "blueprint before demo" funnel gets 50% reply rates (Gojiberry) vs. 8-15% for demo asks. Our current templates all ask for 20-minute calls. For technical buyers in RL, offering a free architectural guide, decision framework, or performance benchmark is dramatically more effective than asking for their time.

---

### Task 2.1: Create Resource-First Email Templates

**Files:**
- Create: `templates/email-sequences/resource-offer-signal.md`

**Logic:** This template is signal-agnostic — it works with ANY signal type. Instead of leading with a pitch and ending with "worth 20 minutes?", it leads with a free resource and ends with "happy to share." The resource is a blueprint/guide tailored to the prospect's signal:

- GitHub signal → "Guide: Scaling RL Environments from 1 to 5 Engineers"
- ArXiv signal → "Framework: Environment Infrastructure Decisions for RL Research Teams"
- Hiring signal → "Checklist: Onboarding RL Engineers Without Environment Debt"
- Funding signal → "Playbook: RL Infrastructure Buildout for Post-Series A Teams"
- HF model signal → "Benchmark: RLHF Environment Quality vs. Training Performance"

The CTA is always: share the resource (no meeting ask). If they engage with the resource, THEN follow up with a conversation offer.

- [ ] **Step 1: Create the template**

Follow the existing template format in `templates/email-sequences/`. Include:
- Signal Context section explaining the resource-first philosophy
- Placeholders: `{{contact_first_name}}`, `{{company_name}}`, `{{signal_reference}}`, `{{resource_title}}`, `{{resource_url}}`
- 3 variants (Problem → resource, Outcome → resource, Social Proof → resource)
- 3-email sequence:
  - Email 1 (Day 0): Offer the resource. "I put together {{resource_title}} after working with teams like {{company_name}}. Happy to share — figured it might save you some decisions."
  - Email 2 (Day 4): Share a specific insight FROM the resource. "One thing that surprised us: teams that [insight]. The full framework covers [other topics]."
  - Email 3 (Day 8): Low-friction conversation offer. "If the framework was useful, happy to walk through the parts most relevant to {{company_name}}'s setup — 15 minutes, no pitch."

- [ ] **Step 2: Verify template quality**

Check: First sentence of every email references the signal or resource? ✓
Check: No email asks for a meeting in Email 1 or 2? ✓
Check: Under 4 sentences per email? ✓
Check: No banned phrases? ✓

- [ ] **Step 3: Commit**

```bash
git add templates/email-sequences/resource-offer-signal.md
git commit -m "docs: add resource-first email template for blueprint-before-demo outreach"
```

---

### Task 2.2: Build Resource Offer Skill

**Files:**
- Create: `skills/resource-offer/SKILL.md`

**Logic:** This skill generates resource-first outreach instead of demo-ask outreach. It maps each signal type to the most relevant resource, generates the email copy using the new template, and includes the resource selection decision tree.

- [ ] **Step 1: Create the skill**

```yaml
---
name: resource-offer
description: Use when generating blueprint-first outreach that offers a free resource instead of asking for a meeting, when targeting technical buyers who respond better to value-add than demo requests, or when implementing the resource-before-demo funnel strategy
---
```

Skill content should instruct Claude to:
1. Accept signal type + company research
2. Select appropriate resource based on signal type (mapping table)
3. Generate email using `templates/email-sequences/resource-offer-signal.md`
4. Explain WHY resource-first works better (50% reply rate vs. 8-15%)
5. Include follow-up guidance: if they reply to Email 1, respond with resource + conversation offer

- [ ] **Step 2: Verify word count**

Run: `wc -w skills/resource-offer/SKILL.md`
Expected: Under 500 words

- [ ] **Step 3: Commit**

```bash
git add skills/resource-offer/SKILL.md
git commit -m "feat: add resource-offer skill for blueprint-before-demo outreach"
```

---

### Task 2.3: Update Email Writer Skill

**Files:**
- Modify: `skills/email-writer/SKILL.md`

**Logic:** The email writer skill needs to know about the resource-first template and recommend it as the default for technical ICP. Add a decision point: "For technical buyers (ML engineers, researchers), default to resource-first template. For business buyers (VP Eng, CTO at non-technical companies), use the standard signal-specific template."

- [ ] **Step 1: Update the skill**

Add to the template selection section:
- A new row in the template table: "Any signal + technical buyer → resource-offer-signal.md (RECOMMENDED)"
- A note: "Resource-first outreach gets 50% reply rates vs. 8-15% for demo asks. Use this as default for ICP Tier 1 (AI Labs) and Tier 3 (Robotics) where buyers are deeply technical."

- [ ] **Step 2: Verify word count still under 500**

- [ ] **Step 3: Commit**

```bash
git add skills/email-writer/SKILL.md
git commit -m "feat: update email-writer skill with resource-first recommendation"
```

---

## Phase 3: Multi-Channel Sequencing

**Why this phase:** The current engine is email-only. But LinkedIn is where ML engineers actually spend time. GTMify's architecture uses different agents per channel. Sendoso's system orchestrates across email + LinkedIn + calls. Adding LinkedIn as a second channel with staggered timing is the next biggest impact upgrade.

---

### Task 3.1: Create LinkedIn Message Templates

**Files:**
- Create: `templates/linkedin-sequences/github-rl-signal.md`
- Create: `templates/linkedin-sequences/arxiv-paper-signal.md`
- Create: `templates/linkedin-sequences/hiring-signal.md`
- Create: `templates/linkedin-sequences/general-signal.md`

**Logic:** LinkedIn messages are fundamentally different from emails:
- **Shorter** — 300 characters for connection requests, ~1000 for InMails
- **More conversational** — LinkedIn is a social platform, not a business inbox
- **Connection-first** — start with a connection request + note, then message
- **No templates visible** — LinkedIn users can spot templated messages instantly

Each template has TWO message types:
1. Connection request note (≤300 chars): Reference the signal, be human, no pitch
2. Follow-up message (after connection accepted): Share resource or insight, low-friction CTA

- [ ] **Step 1: Create all 4 LinkedIn templates**

Each template follows this structure:

```markdown
# [Signal Type] LinkedIn Sequence

## Signal Context
[Why this signal makes LinkedIn the right channel]

## Placeholders
- {{contact_first_name}}, {{company_name}}, {{signal_reference}}

## Connection Request Note (≤300 chars)
### Variant A: Signal Reference
"Saw {{signal_reference}} — impressive work. Building in a similar space (RL environments). Would love to connect."

### Variant B: Mutual Interest
"Your work on {{signal_reference}} caught my eye. Working on RL infrastructure challenges — thought we might have overlapping interests."

## Follow-Up Message (Day 2-3 after accepted)
[2-3 sentences, share a resource or insight, NO pitch]

## Second Follow-Up (Day 7, only if no response)
[1-2 sentences, share different resource, graceful close]
```

**Key rules:**
- Connection requests: ≤300 characters, NEVER mention your product
- Follow-ups: lead with value (share a blog post, paper, or insight), mention product only if asked
- Tone: casual professional, not sales — think "fellow engineer" not "sales rep"

- [ ] **Step 2: Verify character counts**

Every connection request variant must be ≤300 characters.

- [ ] **Step 3: Commit**

```bash
git add templates/linkedin-sequences/
git commit -m "docs: add LinkedIn message templates for multi-channel outreach"
```

---

### Task 3.2: Build Multi-Channel Sequencing Logic

**Files:**
- Create: `scripts/multi_channel_sequencer.py`
- Create: `tests/unit/test_multi_channel_sequencer.py`

**Logic:** The sequencer determines which channels to use and in what order for each prospect. The algorithm:

1. **Primary channel selection** based on contact data:
   - Has verified email + LinkedIn → both channels, staggered
   - Has verified email only → email only
   - Has LinkedIn only → LinkedIn only
   - Has neither → flag for manual research

2. **Timing:** Email and LinkedIn messages are staggered (not simultaneous):
   - Day 0: Email 1
   - Day 1: LinkedIn connection request
   - Day 3: Email 2
   - Day 4: LinkedIn follow-up (if connection accepted)
   - Day 7: Email 3 (break-up)
   - Day 8: LinkedIn second follow-up (if connected, no response)

3. **Channel escalation:** If no response on primary channel after full sequence, try secondary channel with adjusted messaging ("I reached out via email but thought LinkedIn might be better...").

- [ ] **Step 1: Add OutreachChannel enum and ChannelSequence model to models.py**

Add to `scripts/models.py`:

```python
class OutreachChannel(str, Enum):
    EMAIL = "EMAIL"
    LINKEDIN = "LINKEDIN"
    LINKEDIN_INMAIL = "LINKEDIN_INMAIL"


class SequenceStep(BaseModel):
    """A single step in a multi-channel outreach sequence."""
    model_config = ConfigDict(frozen=True)

    day: int
    channel: OutreachChannel
    action: str  # "send_email", "connection_request", "follow_up_message"
    template_name: str
    variant: str | None = None  # Free-form variant label (works across channels)
```

- [ ] **Step 2: Write tests for multi_channel_sequencer.py**

```python
# tests/unit/test_multi_channel_sequencer.py
"""Tests for multi-channel sequencing logic."""
from __future__ import annotations

from scripts.models import OutreachChannel, SignalType
from scripts.multi_channel_sequencer import (
    build_sequence,
    select_primary_channel,
)


class TestSelectPrimaryChannel:
    def test_both_channels_available(self):
        """Email + LinkedIn → both, email primary."""
        channels = select_primary_channel(has_email=True, has_linkedin=True)
        assert OutreachChannel.EMAIL in channels
        assert OutreachChannel.LINKEDIN in channels

    def test_email_only(self):
        channels = select_primary_channel(has_email=True, has_linkedin=False)
        assert channels == [OutreachChannel.EMAIL]

    def test_linkedin_only(self):
        channels = select_primary_channel(has_email=False, has_linkedin=True)
        assert channels == [OutreachChannel.LINKEDIN]

    def test_neither_returns_empty(self):
        channels = select_primary_channel(has_email=False, has_linkedin=False)
        assert channels == []


class TestBuildSequence:
    def test_dual_channel_has_8_steps(self):
        """Full dual-channel sequence has steps on days 0,1,3,4,7,8."""
        steps = build_sequence(
            channels=[OutreachChannel.EMAIL, OutreachChannel.LINKEDIN],
            signal_type=SignalType.GITHUB_RL_REPO,
        )
        assert len(steps) >= 6

    def test_email_only_has_3_steps(self):
        """Email-only sequence has 3 emails on days 0, 3, 7."""
        steps = build_sequence(
            channels=[OutreachChannel.EMAIL],
            signal_type=SignalType.GITHUB_RL_REPO,
        )
        assert len(steps) == 3
        assert all(s.channel == OutreachChannel.EMAIL for s in steps)

    def test_linkedin_only_has_3_steps(self):
        steps = build_sequence(
            channels=[OutreachChannel.LINKEDIN],
            signal_type=SignalType.GITHUB_RL_REPO,
        )
        assert len(steps) == 3
        assert all(s.channel == OutreachChannel.LINKEDIN for s in steps)

    def test_steps_are_chronologically_ordered(self):
        steps = build_sequence(
            channels=[OutreachChannel.EMAIL, OutreachChannel.LINKEDIN],
            signal_type=SignalType.ARXIV_PAPER,
        )
        days = [s.day for s in steps]
        assert days == sorted(days)

    def test_linkedin_template_matches_signal(self):
        steps = build_sequence(
            channels=[OutreachChannel.LINKEDIN],
            signal_type=SignalType.ARXIV_PAPER,
        )
        assert "arxiv" in steps[0].template_name.lower()
```

- [ ] **Step 3: Implement multi_channel_sequencer.py**

- [ ] **Step 4: Run tests**

- [ ] **Step 5: Commit**

```bash
git add scripts/models.py scripts/multi_channel_sequencer.py tests/unit/test_multi_channel_sequencer.py
git commit -m "feat: add multi-channel sequencing engine with email + LinkedIn orchestration"
```

---

### Task 3.3: Build Multi-Channel Writer Skill

**Files:**
- Create: `skills/multi-channel-writer/SKILL.md`

- [ ] **Step 1: Create the skill**

```yaml
---
name: multi-channel-writer
description: Use when generating coordinated outreach across email and LinkedIn, when building staggered multi-channel sequences, or when a prospect hasn't responded to single-channel outreach
---
```

Instruct Claude to:
1. Determine available channels (email? LinkedIn?)
2. Build staggered sequence using `scripts/multi_channel_sequencer.py`
3. Generate email copy using existing email-writer templates
4. Generate LinkedIn copy using new LinkedIn templates
5. Present the full multi-channel sequence with timing

- [ ] **Step 2: Verify word count < 500**

- [ ] **Step 3: Commit**

```bash
git add skills/multi-channel-writer/SKILL.md
git commit -m "feat: add multi-channel-writer skill for coordinated email + LinkedIn outreach"
```

---

## Phase 4: Meeting Follow-Up Automation

**Why this phase:** The current engine gets prospects TO a meeting but has no post-meeting automation. Sendoso's meeting follow-up system (Circle Back → n8n → Claude → Slack approval) shows the pattern. This is the gap between "meeting booked" and "deal closed."

---

### Task 4.1: Add Post-Meeting Models

**Files:**
- Modify: `scripts/models.py`
- Create: `tests/unit/test_meeting_models.py`

- [ ] **Step 1: Write tests for new models**

```python
# tests/unit/test_meeting_models.py
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

    def test_new_deal_stages_exist(self):
        """Verify MEETING_COMPLETED and PROPOSAL_SENT were added."""
        assert DealStage.MEETING_COMPLETED == "MEETING_COMPLETED"
        assert DealStage.PROPOSAL_SENT == "PROPOSAL_SENT"
```

- [ ] **Step 2: Add models to scripts/models.py**

```python
class MeetingOutcome(BaseModel):
    """Structured output from a discovery/demo meeting."""
    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    deal_id: str
    meeting_date: datetime
    attendees: list[str]
    outcome: str  # "positive", "neutral", "negative", "no_show"
    objections: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    decision_timeline: str | None = None
    stakeholders_needed: list[str] = Field(default_factory=list)
    follow_up_resources: list[str] = Field(default_factory=list)
    notes: str = ""
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
```

Add `MEETING_COMPLETED` and `PROPOSAL_SENT` to `DealStage` enum.

- [ ] **Step 3: Run tests**

- [ ] **Step 4: Commit**

```bash
git add scripts/models.py tests/unit/test_meeting_models.py
git commit -m "feat: add MeetingOutcome model for post-meeting automation"
```

---

### Task 4.2: Build Meeting Follow-Up Skill

**Files:**
- Create: `skills/meeting-followup/SKILL.md`
- Create: `templates/email-sequences/meeting-followup.md`

- [ ] **Step 1: Create the follow-up email template**

Template for post-meeting emails based on outcome:

**Positive outcome:**
- Email 1 (Day 0, same day): Thank you + attach resources discussed + calendar link for next step
- Email 2 (Day 3): Share relevant case study or proof point addressing their specific use case
- Email 3 (Day 7): Check-in on internal alignment, offer to present to additional stakeholders

**Neutral outcome:**
- Email 1 (Day 0): Thank you + key takeaway + relevant resource
- Email 2 (Day 5): Share a new insight or announcement relevant to their situation
- Email 3 (Day 14): Gentle check-in with new angle

**Negative outcome / Not now:**
- Email 1 (Day 0): Thank you, no pressure, share one last resource
- (No follow-up sequence — add to 6-month re-qualification list)

**No-show:**
- Email 1 (Day 0): "No worries about today — here's the resource I was going to share"
- Email 2 (Day 3): Offer to reschedule, provide self-serve option

- [ ] **Step 2: Create the skill**

```yaml
---
name: meeting-followup
description: Use when a meeting has been completed and you need to generate follow-up emails, when processing meeting notes to extract next steps and objections, or when routing post-meeting tasks based on meeting outcome
---
```

Instruct Claude to:
1. Accept meeting notes (free text or structured)
2. Extract: outcome, objections, next steps, stakeholders, timeline
3. Create MeetingOutcome record
4. Select appropriate follow-up template
5. Generate follow-up email with specific references to discussion points
6. Recommend: CRM updates, resource to share, next touch timing

- [ ] **Step 3: Commit**

```bash
git add skills/meeting-followup/SKILL.md templates/email-sequences/meeting-followup.md
git commit -m "feat: add meeting-followup skill and post-meeting email templates"
```

---

## Phase 5: LinkedIn Activity Scanner

**Why this phase:** The 48-hour LinkedIn activity filter is the single highest-ROI signal according to Gojiberry. "This alone doubles response rates across every campaign tested." This adds LinkedIn activity as a 6th signal source — but it's special because it acts as a MULTIPLIER on existing signals, not just another signal.

---

### Task 5.1: Build LinkedIn Activity Scanner

**Files:**
- Create: `scripts/linkedin_activity.py`
- Create: `tests/unit/test_linkedin_activity.py`

**Logic:** LinkedIn doesn't have a public API for activity data. This scanner works through two approaches:
1. **Sales Navigator integration** — if Sales Navigator API access is available, query for recent activity
2. **Manual input mode** — accept a CSV/JSON of LinkedIn activity data (exported from Sales Nav, Phantom Buster, or manual research)

The key insight from Gojiberry: checking if someone has been active on LinkedIn in the last 48 hours alone doubles response rates. So this scanner's primary job is to add a RECENCY BOOST to existing signals — if a contact at a company we're already tracking is active on LinkedIn right now, that company's score should spike.

Signal types to detect:
- Posted about AI/ML/RL topics (highest intent)
- Commented on competitor or category content (high intent)
- Changed job title (medium intent — already covered by champion tracker, but adds recency)
- Followed your company page (highest intent)
- Active on platform (basic — just means they'll see your outreach)

- [ ] **Step 1: Add LINKEDIN_ACTIVITY to SignalType enum**

**IMPORTANT:** After adding the new enum value, check `tests/unit/test_models.py` for any test that enumerates `SignalType` values (e.g., `test_enum_values_correct`). Update that test to include the new value. Also check `tests/unit/test_signal_stacker.py` for any tests that might need updating.

In `scripts/models.py`, add:
```python
class SignalType(str, Enum):
    GITHUB_RL_REPO = "GITHUB_RL_REPO"
    ARXIV_PAPER = "ARXIV_PAPER"
    JOB_POSTING = "JOB_POSTING"
    HUGGINGFACE_MODEL = "HUGGINGFACE_MODEL"
    FUNDING_EVENT = "FUNDING_EVENT"
    LINKEDIN_ACTIVITY = "LINKEDIN_ACTIVITY"  # New
```

Update any tests that enumerate SignalType values.

- [ ] **Step 2: Write tests for linkedin_activity.py**

```python
# tests/unit/test_linkedin_activity.py
from scripts.linkedin_activity import LinkedInActivityScanner
from scripts.models import SignalType, SignalStrength


class TestLinkedInActivityScanner:
    def test_scan_from_data_returns_scan_result(self):
        """Scanner should process activity data into signals."""
        data = [
            {"name": "John Smith", "company": "Acme AI", "activity_type": "posted",
             "topic": "reinforcement learning", "timestamp": "2026-03-17T10:00:00Z"},
        ]
        scanner = LinkedInActivityScanner()
        result = scanner.scan_from_data(data)
        assert result.scan_type == SignalType.LINKEDIN_ACTIVITY
        assert len(result.signals_found) == 1

    def test_filters_non_rl_activity(self):
        """Activity not related to RL/ML should be filtered."""
        data = [
            {"name": "Jane Doe", "company": "FoodCo", "activity_type": "posted",
             "topic": "cooking recipes", "timestamp": "2026-03-17T10:00:00Z"},
        ]
        scanner = LinkedInActivityScanner()
        result = scanner.scan_from_data(data)
        assert len(result.signals_found) == 0

    def test_48_hour_filter(self):
        """Activity older than 48 hours should be excluded by default."""
        data = [
            {"name": "John Smith", "company": "Acme AI", "activity_type": "posted",
             "topic": "reinforcement learning", "timestamp": "2026-03-14T10:00:00Z"},
        ]
        scanner = LinkedInActivityScanner()
        result = scanner.scan_from_data(data)
        assert len(result.signals_found) == 0  # 3 days old, filtered

    def test_posted_about_rl_is_strong(self):
        """Posting about RL topics = STRONG signal."""
        data = [
            {"name": "Jane Doe", "company": "DeepRL Inc", "activity_type": "posted",
             "topic": "reinforcement learning environments", "timestamp": "2026-03-17T10:00:00Z"},
        ]
        scanner = LinkedInActivityScanner()
        result = scanner.scan_from_data(data)
        assert result.signals_found[0].signal_strength == SignalStrength.STRONG

    def test_engaged_with_competitor_is_moderate(self):
        """Commenting on competitor content = MODERATE signal."""
        data = [
            {"name": "Bob Lee", "company": "RoboML", "activity_type": "commented",
             "topic": "RL environment platform comparison", "timestamp": "2026-03-17T10:00:00Z"},
        ]
        scanner = LinkedInActivityScanner()
        result = scanner.scan_from_data(data)
        assert result.signals_found[0].signal_strength == SignalStrength.MODERATE

    def test_basic_activity_is_weak(self):
        """Just being active with ML context = WEAK signal."""
        data = [
            {"name": "Alice Wang", "company": "MLCorp", "activity_type": "liked",
             "topic": "machine learning infrastructure", "timestamp": "2026-03-17T10:00:00Z"},
        ]
        scanner = LinkedInActivityScanner()
        result = scanner.scan_from_data(data)
        assert result.signals_found[0].signal_strength == SignalStrength.WEAK

    def test_groups_by_company(self):
        """Multiple people from same company → one signal."""
        data = [
            {"name": "Person A", "company": "SameCo", "activity_type": "posted",
             "topic": "reinforcement learning", "timestamp": "2026-03-17T10:00:00Z"},
            {"name": "Person B", "company": "SameCo", "activity_type": "liked",
             "topic": "RL training", "timestamp": "2026-03-17T11:00:00Z"},
        ]
        scanner = LinkedInActivityScanner()
        result = scanner.scan_from_data(data)
        assert len(result.signals_found) == 1
        assert result.signals_found[0].company_name == "SameCo"

    def test_metadata_includes_activity_details(self):
        """Signal metadata should include activity types and topics."""
        data = [
            {"name": "John Smith", "company": "Acme AI", "activity_type": "posted",
             "topic": "reinforcement learning", "timestamp": "2026-03-17T10:00:00Z"},
        ]
        scanner = LinkedInActivityScanner()
        result = scanner.scan_from_data(data)
        meta = result.signals_found[0].metadata
        assert "activity_types" in meta
        assert "topics" in meta
        assert "active_contacts" in meta
```

- [ ] **Step 3: Implement linkedin_activity.py**

```python
# scripts/linkedin_activity.py
"""LinkedIn activity signal scanner.

Detects prospects who are active on LinkedIn and posting about RL/ML topics.
The 48-hour activity filter alone doubles response rates (Gojiberry AI data).

Two modes:
1. Data input mode: Accept pre-collected activity data (CSV/JSON)
2. (Future) Sales Navigator API mode: Query LinkedIn Sales Navigator

Activity scoring:
- Posted about RL/ML: STRONG (3) — highest intent, they're thinking about this
- Commented on competitor/category content: MODERATE (2) — evaluating solutions
- Changed title / new job: MODERATE (2) — already handled by champion tracker
- Basic activity (likes, shares): WEAK (1) — at least they'll see your message
"""
```

- [ ] **Step 4: Add LinkedIn half-life to recency.py**

Already added in Task 1.1: `LINKEDIN_ACTIVITY = 2` (48-hour half-life).

Add to `_HALF_LIVES` in `intent_scorer.py`:
```python
SignalType.LINKEDIN_ACTIVITY: SignalHalfLife.LINKEDIN_ACTIVITY,
```

And add intent weight:
```python
SignalType.LINKEDIN_ACTIVITY: 3.0,  # Real-time engagement = highest urgency
```

- [ ] **Step 5: Run tests**

- [ ] **Step 6: Commit**

```bash
git add scripts/models.py scripts/linkedin_activity.py scripts/intent_scorer.py scripts/recency.py tests/unit/test_linkedin_activity.py
git commit -m "feat: add LinkedIn activity scanner with 48-hour recency filter"
```

---

### Task 5.2: Update Signal Scanner Skill

**Files:**
- Modify: `skills/signal-scanner/SKILL.md`

- [ ] **Step 1: Update the skill**

Add LinkedIn activity scanner to the list of scanners. Add a note about the 48-hour filter:

"The LinkedIn activity scanner is the highest-ROI signal source. Gojiberry AI's data shows that filtering for 48-hour LinkedIn activity alone doubles response rates. Run this scanner LAST and use it as a multiplier on existing signals — a company that already has GitHub + ArXiv signals AND whose Head of ML was active on LinkedIn today should be your #1 priority."

Add the new scanner command:
```
python3 -m scripts.linkedin_activity --input linkedin_data.json --output /tmp/linkedin_signals.json
```

Update the signal stacker command to include the new file.

- [ ] **Step 2: Commit**

```bash
git add skills/signal-scanner/SKILL.md
git commit -m "feat: update signal-scanner skill with LinkedIn activity source"
```

---

## Phase 6: Updated Documentation and n8n Workflows

---

### Task 6.1: Update Architecture Documentation

**Files:**
- Modify: `docs/architecture.md`

Add:
1. Intent-weighted scoring explanation with formula
2. Multi-channel sequencing diagram
3. LinkedIn activity as 6th signal source
4. Resource-first outreach funnel diagram
5. Post-meeting automation flow

- [ ] **Step 1: Update docs/architecture.md**
- [ ] **Step 2: Commit**

```bash
git add docs/architecture.md
git commit -m "docs: update architecture with intent scoring, multi-channel, and meeting followup"
```

---

### Task 6.2: Update n8n Daily Signal Scan Workflow

**Files:**
- Modify: `n8n-workflows/daily-signal-scan.json`

Add LinkedIn activity scanner node (runs in parallel with other scanners). Update the signal stacker node to include the LinkedIn output. Update the Slack notification to show intent-weighted scores.

- [ ] **Step 1: Update the workflow JSON**
- [ ] **Step 2: Verify valid JSON**
- [ ] **Step 3: Commit**

```bash
git add n8n-workflows/daily-signal-scan.json
git commit -m "feat: add LinkedIn activity scanner to daily signal scan workflow"
```

---

### Task 6.3: Final Test Suite and Cleanup

**Files:**
- All test files

- [ ] **Step 1: Run full test suite**

Run: `python3 -m pytest tests/ -v --cov=scripts --cov-report=term-missing`
Expected: All tests pass, coverage ≥ 80% on all new modules

- [ ] **Step 2: Run linter**

Run: `python3 -m ruff check scripts/ tests/ --fix && python3 -m ruff format scripts/ tests/`
Expected: No errors

- [ ] **Step 3: Security check**

Verify: No hardcoded secrets, .env in .gitignore, no PII in test fixtures

- [ ] **Step 4: Commit any fixes**

```bash
git add -A
git commit -m "chore: final lint fixes and test cleanup for GTM intelligence upgrade"
```

---

## Appendix: Task Index

| Task | Name | Phase | Dependencies |
|------|------|-------|-------------|
| 1.1 | Recency Decay Functions | 1: Intent Scoring | — |
| 1.2 | Intent-Weighted Scoring Engine | 1: Intent Scoring | 1.1 |
| 1.3 | Update ICP Scoring Rubric | 1: Intent Scoring | 1.2 |
| 1.4 | Integrate Intent Scorer into Stacker | 1: Intent Scoring | 1.2 |
| 2.1 | Resource-First Email Templates | 2: Blueprint Outreach | — |
| 2.2 | Resource Offer Skill | 2: Blueprint Outreach | 2.1 |
| 2.3 | Update Email Writer Skill | 2: Blueprint Outreach | 2.1 |
| 3.1 | LinkedIn Message Templates | 3: Multi-Channel | — |
| 3.2 | Multi-Channel Sequencing Logic | 3: Multi-Channel | 3.1 |
| 3.3 | Multi-Channel Writer Skill | 3: Multi-Channel | 3.2 |
| 4.1 | Post-Meeting Models | 4: Meeting Follow-Up | — |
| 4.2 | Meeting Follow-Up Skill | 4: Meeting Follow-Up | 4.1 |
| 5.1 | LinkedIn Activity Scanner | 5: LinkedIn Signal | 1.1, 1.2 |
| 5.2 | Update Signal Scanner Skill | 5: LinkedIn Signal | 5.1 |
| 6.1 | Update Architecture Docs | 6: Polish | All above |
| 6.2 | Update n8n Daily Scan Workflow | 6: Polish | 5.1 |
| 6.3 | Final Test Suite and Cleanup | 6: Polish | All above |

## Dependency Graph

```
Phase 1 (Intent Scoring)
  Task 1.1 → Task 1.2 → Task 1.3
                ↓
              Task 1.4

Phase 2 (Blueprint Outreach)     Phase 3 (Multi-Channel)
  Task 2.1 → Task 2.2             Task 3.1 → Task 3.2 → Task 3.3
      ↓
  Task 2.3

Phase 4 (Meeting Follow-Up)     Phase 5 (LinkedIn Signal)
  Task 4.1 → Task 4.2            Task 5.1 → Task 5.2
                                  (depends on 1.1, 1.2)

Phase 6 (Polish)
  Task 6.1, 6.2, 6.3 (depends on all above)
```

**Parallelizable:** Phases 2, 3, and 4 can run in parallel (no dependencies between them). Phase 5 depends on Phase 1.
