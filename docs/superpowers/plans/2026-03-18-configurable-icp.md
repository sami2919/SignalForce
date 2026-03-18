# Configurable ICP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make SignalForce configurable so any company can use it with their own ICP — extract all RL-specific content into a config directory, make the engine read from config at runtime, and add a setup wizard.

**Architecture:** Extract & Configure. All domain-specific content (keywords, tiers, templates, scoring weights) moves to a `config/` directory read at runtime. Six scanners move to a `scripts/scanners/` package and implement `scan(ScannerConfig) -> ScanResult`. A hybrid setup skill auto-generates config from a company description. RL content ships as a working example in `examples/rl-infrastructure/`.

**Tech Stack:** Python 3.11+, Pydantic v2 (frozen models), PyYAML, pytest, ruff

**Spec:** `docs/superpowers/specs/2026-03-18-configurable-icp-design.md`

---

## File Structure

### New files
| File | Responsibility |
|------|---------------|
| `scripts/config_loader.py` | Load + validate `config/config.yaml` via Pydantic |
| `scripts/scanner_runner.py` | Dynamic scanner dispatch via importlib |
| `scripts/scanners/__init__.py` | Package init, re-exports |
| `scripts/scanners/base.py` | Re-export ScannerConfig, ScanResult, Signal, SignalStrength |
| `config.example/config.yaml` | Reference config schema with RL defaults |
| `config.example/gtm-context.md` | Reference GTM positioning (moved from `.agents/`) |
| `config.example/templates/email-sequences/*.md` | Reference email templates (moved from `templates/`) |
| `config.example/templates/linkedin-sequences/*.md` | Reference LinkedIn templates (moved from `templates/`) |
| `examples/rl-infrastructure/` | Complete RL config (copy of config.example) |
| `examples/cybersecurity/` | Example: API security tools → DevSecOps |
| `examples/devtools/` | Example: Dev productivity → engineering leads |
| `examples/data-infra/` | Example: Data pipelines → data engineers |
| `skills/setup/SKILL.md` | Hybrid config generation wizard |
| `skills/validate/SKILL.md` | Config validation checker |
| `tests/unit/test_config_loader.py` | Config loading tests |
| `tests/unit/test_scanner_runner.py` | Scanner dispatch tests |
| `tests/unit/test_first_run_guard.py` | First-run guard tests |
| `tests/fixtures/sample_config.yaml` | Valid test fixture |
| `tests/fixtures/bad_config.yaml` | Invalid test fixture |
| `TODOS.md` | Deferred work tracking |

### Modified files
| File | Change |
|------|--------|
| `scripts/models.py` | Remove `SignalType`, `RLMaturityStage`, `ICPTier`, `ContactTitle` enums → free-form strings. Remove `Signal.validate_github_metadata`. Change `ScanResult.scan_type` to `str`. |
| `scripts/intent_scorer.py` | `IntentScorer.__init__` accepts `SignalForceConfig`. Weights + half-lives from config. Remove module-level `INTENT_WEIGHTS`, `_HALF_LIVES`. |
| `scripts/recency.py` | Remove `SignalHalfLife` class. Keep `calculate_decay_factor` and `apply_recency_weight` unchanged. |
| `scripts/signal_stacker.py` | `SignalStacker.__init__` accepts optional `SignalForceConfig`. Thread config to `IntentScorer`. |
| `scripts/multi_channel_sequencer.py` | `_TEMPLATE_MAP` reads from config instead of `SignalType` enum keys. `build_sequence` accepts `signal_type: str`. |
| `scripts/scanners/github_scanner.py` | Moved from `scripts/github_rl_scanner.py`. Remove `RL_TOPICS`, `RL_LIBRARIES`. Add `scan(ScannerConfig) -> ScanResult`. |
| `scripts/scanners/arxiv_scanner.py` | Moved from `scripts/arxiv_monitor.py`. Remove `RL_SEARCH_QUERIES`. Add `scan(ScannerConfig) -> ScanResult`. |
| `scripts/scanners/hf_scanner.py` | Moved from `scripts/hf_model_monitor.py`. Remove `RL_TRAINING_TAGS`, `RL_KEYWORDS_IN_CARD`. Add `scan(ScannerConfig) -> ScanResult`. |
| `scripts/scanners/job_scanner.py` | Moved from `scripts/job_posting_scanner.py`. Remove `_RL_SKILLS`, `JOB_TITLES`. Add `scan(ScannerConfig) -> ScanResult`. |
| `scripts/scanners/funding_scanner.py` | Moved from `scripts/funding_tracker.py`. Remove hardcoded "reinforcement learning" queries. Add `scan(ScannerConfig) -> ScanResult`. |
| `scripts/scanners/linkedin_scanner.py` | Moved from `scripts/linkedin_activity.py`. Remove `RL_KEYWORDS`. Add `scan(ScannerConfig) -> ScanResult`. |
| 11 `skills/*/SKILL.md` | Replace RL references, update paths from `.agents/` → `config/`, `templates/` → `config/templates/` |
| 4 `n8n-workflows/*.json` | Update scanner module paths, remove "RL" from message strings |
| `docs/architecture.md` | Replace "rl-gtm-engine" → "SignalForce", update diagrams |
| `CLAUDE.md` | Replace "rl-gtm-engine" → "SignalForce", update directory structure |
| `README.md` | Rewrite for generic positioning + quickstart |
| `.gitignore` | Add `config/` |
| 6 scanner test files | Update for config injection, remove hardcoded keyword assertions |
| `tests/unit/test_models.py` | Update for removed enums, free-form strings |
| `tests/unit/test_intent_scorer.py` | Update for config-injected `IntentScorer` |
| `tests/unit/test_signal_stacker.py` | Update for config threading |
| `tests/unit/test_multi_channel_sequencer.py` | Update for string signal types |

---

## Phase 1: Config Foundation

### Task 1: Config Pydantic Models + Loader

**Files:**
- Create: `scripts/config_loader.py`
- Create: `tests/unit/test_config_loader.py`
- Create: `tests/fixtures/sample_config.yaml`
- Create: `tests/fixtures/bad_config.yaml`

- [ ] **Step 1: Create test fixtures**

```yaml
# tests/fixtures/sample_config.yaml
company:
  name: "Test Corp"
  product: "Test product"
  category: "Testing"
  website: "https://test.com"

icp:
  tiers:
    - name: "Tier 1"
      description: "Primary buyers"
      signals: ["signal-1"]
  maturity_stages: ["EXPLORING", "BUILDING", "SCALING"]
  target_titles: ["Engineer", "Manager"]
  disqualifiers: ["No activity"]

scanners:
  github:
    enabled: true
    module: scripts.scanners.github_scanner
    topics: ["test-topic"]
    libraries: ["test-lib"]
    keywords: ["test-keyword"]
    lookback_days: 7
  arxiv:
    enabled: false
    module: scripts.scanners.arxiv_scanner
    queries: ["test query"]

scoring:
  intent_weights:
    github: 2.5
    arxiv: 3.0
  half_lives_days:
    github: 5
    arxiv: 10
  icp_weight: 0.4
  intent_weight: 0.6
  grade_thresholds:
    A: 8.0
    B: 5.0
    C: 2.0
```

```yaml
# tests/fixtures/bad_config.yaml
company:
  name: "Missing required fields"
# Missing: product, category, icp, scanners, scoring
```

- [ ] **Step 2: Write failing tests for config_loader**

```python
# tests/unit/test_config_loader.py
"""Tests for config loading and validation."""

from pathlib import Path
import pytest
import yaml

from scripts.config_loader import (
    load_config,
    SignalForceConfig,
    ScannerConfig,
    CompanyConfig,
    ICPConfig,
    ScoringConfig,
)

_FIXTURES = Path(__file__).parent.parent / "fixtures"
_VALID = _FIXTURES / "sample_config.yaml"
_BAD = _FIXTURES / "bad_config.yaml"


class TestLoadConfig:
    def test_loads_valid_config(self) -> None:
        config = load_config(_VALID)
        assert isinstance(config, SignalForceConfig)
        assert config.company.name == "Test Corp"

    def test_raises_on_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="No config found"):
            load_config(tmp_path / "nonexistent.yaml")

    def test_raises_on_bad_yaml(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.yaml"
        bad.write_text(": invalid: yaml: {{{}}")
        with pytest.raises(yaml.YAMLError):
            load_config(bad)

    def test_raises_on_schema_violation(self) -> None:
        with pytest.raises(Exception):  # pydantic.ValidationError
            load_config(_BAD)

    def test_ignores_extra_fields(self, tmp_path: Path) -> None:
        """Forward compatibility: unknown fields are silently ignored."""
        data = yaml.safe_load(_VALID.read_text())
        data["future_field"] = "ignored"
        data["scanners"]["github"]["future_param"] = "also ignored"
        p = tmp_path / "extra.yaml"
        p.write_text(yaml.dump(data))
        config = load_config(p)
        assert config.company.name == "Test Corp"


class TestScannerConfig:
    def test_enabled_scanner(self) -> None:
        config = load_config(_VALID)
        assert config.scanners["github"].enabled is True
        assert config.scanners["github"].topics == ["test-topic"]

    def test_disabled_scanner(self) -> None:
        config = load_config(_VALID)
        assert config.scanners["arxiv"].enabled is False

    def test_defaults(self) -> None:
        config = load_config(_VALID)
        gh = config.scanners["github"]
        assert gh.lookback_days == 7
        assert gh.custom_params == {}


class TestScoringConfig:
    def test_weights_loaded(self) -> None:
        config = load_config(_VALID)
        assert config.scoring.intent_weights["github"] == 2.5
        assert config.scoring.half_lives_days["arxiv"] == 10

    def test_defaults(self) -> None:
        config = load_config(_VALID)
        assert config.scoring.icp_weight == 0.4
        assert config.scoring.intent_weight == 0.6

    def test_grade_thresholds(self) -> None:
        config = load_config(_VALID)
        assert config.scoring.grade_thresholds["A"] == 8.0
```

- [ ] **Step 3: Run tests — verify they FAIL**

Run: `pytest tests/unit/test_config_loader.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.config_loader'`

- [ ] **Step 4: Implement config_loader.py**

```python
# scripts/config_loader.py
"""Load and validate SignalForce ICP configuration from YAML.

Distinct from scripts/config.py which handles secrets/API keys from .env.
This module handles domain configuration: what to scan for, how to score, who to target.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_CONFIG_DIR = _PROJECT_ROOT / "config"
_CONFIG_FILE = _CONFIG_DIR / "config.yaml"


# ---------------------------------------------------------------------------
# Pydantic config models (all frozen / immutable)
# ---------------------------------------------------------------------------


class CompanyConfig(BaseModel):
    """Company identity and product positioning."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    name: str
    product: str
    category: str
    website: str = ""


class ICPTierConfig(BaseModel):
    """A single ICP tier definition."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    name: str
    description: str
    signals: list[str] = []


class ICPConfig(BaseModel):
    """Ideal Customer Profile configuration."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    tiers: list[ICPTierConfig]
    maturity_stages: list[str]
    target_titles: list[str]
    disqualifiers: list[str] = []


class ScannerConfig(BaseModel):
    """Configuration for a single scanner module."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    enabled: bool = True
    module: str
    keywords: list[str] = []
    topics: list[str] = []
    libraries: list[str] = []
    queries: list[str] = []
    training_tags: list[str] = []
    card_keywords: list[str] = []
    titles: list[str] = []
    skills: list[str] = []
    lookback_days: int = 7
    custom_params: dict[str, Any] = {}


class ScoringConfig(BaseModel):
    """Scoring engine configuration: weights, half-lives, grade thresholds."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    intent_weights: dict[str, float]
    half_lives_days: dict[str, float]
    icp_weight: float = 0.4
    intent_weight: float = 0.6
    grade_thresholds: dict[str, float] = {"A": 8.0, "B": 5.0, "C": 2.0}


class SignalForceConfig(BaseModel):
    """Top-level SignalForce configuration."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    company: CompanyConfig
    icp: ICPConfig
    scanners: dict[str, ScannerConfig]
    scoring: ScoringConfig


# ---------------------------------------------------------------------------
# First-run guard
# ---------------------------------------------------------------------------


def check_config_exists(config_dir: Path = _CONFIG_DIR) -> None:
    """Check that config/ exists with a config.yaml. Exit with helpful message if not."""
    if not config_dir.exists() or not (config_dir / "config.yaml").exists():
        print(
            "\n  SignalForce is not configured yet.\n"
            "\n"
            "  Quick start:\n"
            "    1. Run the /setup skill to auto-generate config for your ICP\n"
            "    2. Or copy an example:  cp -r examples/rl-infrastructure/ config/\n"
            "    3. Or copy the template: cp -r config.example/ config/\n"
            "\n"
            "  See README.md for details.\n"
        )
        raise SystemExit(1)


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


def load_config(config_path: Path = _CONFIG_FILE) -> SignalForceConfig:
    """Load and validate SignalForce configuration.

    Raises:
        FileNotFoundError: config file does not exist.
        yaml.YAMLError: YAML syntax error.
        pydantic.ValidationError: schema validation failure.
    """
    if not config_path.exists():
        raise FileNotFoundError(
            f"No config found at {config_path}. "
            "Run the /setup skill to configure SignalForce for your ICP, "
            "or copy an example: cp -r config.example/ config/"
        )
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    return SignalForceConfig.model_validate(raw)
```

- [ ] **Step 5: Run tests — verify they PASS**

Run: `pytest tests/unit/test_config_loader.py -v`
Expected: All PASS

- [ ] **Step 6: Lint and commit**

```bash
ruff format scripts/config_loader.py tests/unit/test_config_loader.py
ruff check scripts/config_loader.py tests/unit/test_config_loader.py --fix
git add scripts/config_loader.py tests/unit/test_config_loader.py tests/fixtures/sample_config.yaml tests/fixtures/bad_config.yaml
git commit -m "feat: add config loader with Pydantic validation and test fixtures"
```

---

### Task 2: First-Run Guard Tests

**Files:**
- Create: `tests/unit/test_first_run_guard.py`

- [ ] **Step 1: Write tests**

```python
# tests/unit/test_first_run_guard.py
"""Tests for first-run onboarding guard."""

from pathlib import Path
import pytest

from scripts.config_loader import check_config_exists


class TestCheckConfigExists:
    def test_exits_when_dir_missing(self, tmp_path: Path) -> None:
        with pytest.raises(SystemExit):
            check_config_exists(tmp_path / "nonexistent")

    def test_exits_when_yaml_missing(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        # Dir exists but no config.yaml inside
        with pytest.raises(SystemExit):
            check_config_exists(config_dir)

    def test_passes_when_config_exists(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "config.yaml").write_text("company: {}")
        # Should not raise
        check_config_exists(config_dir)
```

- [ ] **Step 2: Run — verify PASS**

Run: `pytest tests/unit/test_first_run_guard.py -v`
Expected: All PASS (implementation was included in Task 1)

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_first_run_guard.py
git commit -m "test: add first-run onboarding guard tests"
```

---

## Phase 2: Models & Scoring Generalization

### Task 3: Generalize models.py

**Files:**
- Modify: `scripts/models.py`
- Modify: `tests/unit/test_models.py`

- [ ] **Step 1: Update test_models.py for free-form strings**

Update tests to:
- Remove all assertions against `SignalType` enum values (replace with string assertions)
- Remove tests for `RLMaturityStage`, `ICPTier`, `ContactTitle` enums
- Add tests that `Signal.signal_type` accepts any string
- Add tests that `CompanyProfile.rl_maturity` field is renamed to `maturity_stage: str | None`
- Add tests that `CompanyProfile.icp_tier` accepts any string
- Remove `test_validate_github_metadata` test (validator removed)
- Add test that `ScanResult.scan_type` accepts any string

- [ ] **Step 2: Run tests — verify FAIL**

Run: `pytest tests/unit/test_models.py -v`
Expected: FAIL — enums still exist, validator still present

- [ ] **Step 3: Modify models.py**

Apply these changes:
1. **Remove** `SignalType` enum entirely
2. **Remove** `RLMaturityStage` enum entirely
3. **Remove** `ICPTier` enum entirely
4. **Remove** `ContactTitle` enum entirely
5. Change `Signal.signal_type` from `SignalType` to `str`
6. Change `Signal.validate_github_metadata` — **remove** the entire `@model_validator` method
7. Change `CompanyProfile.icp_tier` from `ICPTier | None` to `str | None`
8. Change `CompanyProfile.rl_maturity` — **rename** field to `maturity_stage: str | None`
9. Change `Contact.title_category` from `ContactTitle` to `str`
10. Change `GeneratedEmail.signal_type` from `SignalType` to `str`
11. Change `ScanResult.scan_type` from `SignalType` to `str`
12. Update module docstring: "RL GTM pipeline" → "SignalForce GTM pipeline"
13. Remove unused imports for deleted enums

Keep all remaining enums: `SignalStrength`, `ICPScore`, `DealStage`, `OutreachChannel`, `EmailVariant`, `EnrichmentSource`

- [ ] **Step 4: Run tests — verify PASS**

Run: `pytest tests/unit/test_models.py -v`
Expected: All PASS

- [ ] **Step 5: Run full test suite to find cascade breakage**

Run: `pytest --tb=short -q`
Expected: Several tests FAIL due to references to removed enums (this is expected — we'll fix in subsequent tasks)

- [ ] **Step 6: Lint and commit**

```bash
ruff format scripts/models.py tests/unit/test_models.py
ruff check scripts/models.py tests/unit/test_models.py --fix
git add scripts/models.py tests/unit/test_models.py
git commit -m "refactor: generalize models.py — remove RL-specific enums, use free-form strings"
```

---

### Task 4: Refactor recency.py

**Files:**
- Modify: `scripts/recency.py`
- Modify: `tests/unit/test_recency.py`

- [ ] **Step 1: Update test_recency.py**

Remove any tests that reference `SignalHalfLife` class attributes. Tests for `calculate_decay_factor` and `apply_recency_weight` should remain unchanged (they already accept `half_life_days` as a parameter).

- [ ] **Step 2: Modify recency.py**

Remove the `SignalHalfLife` class entirely. Keep `calculate_decay_factor` and `apply_recency_weight` functions unchanged. Update module docstring to remove RL-specific references.

- [ ] **Step 3: Run tests — verify PASS**

Run: `pytest tests/unit/test_recency.py -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
ruff format scripts/recency.py tests/unit/test_recency.py
git add scripts/recency.py tests/unit/test_recency.py
git commit -m "refactor: remove SignalHalfLife class — half-lives now come from config"
```

---

### Task 5: Refactor intent_scorer.py

**Files:**
- Modify: `scripts/intent_scorer.py`
- Modify: `tests/unit/test_intent_scorer.py`

- [ ] **Step 1: Update test_intent_scorer.py**

Rewrite tests to:
- Load a `SignalForceConfig` from `tests/fixtures/sample_config.yaml`
- Instantiate `IntentScorer(config)` instead of `IntentScorer()`
- Create `Signal` objects with `signal_type="github"` (string) instead of `SignalType.GITHUB_RL_REPO`
- Test fallback weight (signal type not in config → default weight 1.0)
- Keep existing math validation tests (just with updated input types)

- [ ] **Step 2: Run tests — verify FAIL**

Run: `pytest tests/unit/test_intent_scorer.py -v`
Expected: FAIL — `IntentScorer` doesn't accept config yet

- [ ] **Step 3: Modify intent_scorer.py**

1. Remove module-level `INTENT_WEIGHTS` dict
2. Remove module-level `_HALF_LIVES` dict
3. Remove import of `SignalType` and `SignalHalfLife`
4. Add import of `SignalForceConfig` from `scripts.config_loader`
5. Change `IntentScorer.__init__` to accept `config: SignalForceConfig`:
   ```python
   def __init__(self, config: SignalForceConfig) -> None:
       self._weights = config.scoring.intent_weights
       self._half_lives = config.scoring.half_lives_days
       self._icp_weight = config.scoring.icp_weight
       self._intent_weight = config.scoring.intent_weight
       thresholds = config.scoring.grade_thresholds
       self._grade_thresholds = sorted(
           ((v, ICPScore(k)) for k, v in thresholds.items()),
           key=lambda t: t[0],
           reverse=True,
       )
   ```
6. Update `calculate_intent_score` to use `self._weights.get(signal.signal_type, 1.0)` and `self._half_lives.get(signal.signal_type, 7.0)`
7. Update `calculate_combined_score` to use `self._icp_weight` and `self._intent_weight`
8. Make `calculate_intent_score` and `calculate_combined_score` instance methods (not standalone functions)
9. Update `_determine_grade` to use `self._grade_thresholds`

- [ ] **Step 4: Run tests — verify PASS**

Run: `pytest tests/unit/test_intent_scorer.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
ruff format scripts/intent_scorer.py tests/unit/test_intent_scorer.py
git add scripts/intent_scorer.py tests/unit/test_intent_scorer.py
git commit -m "refactor: IntentScorer reads weights and half-lives from config"
```

---

### Task 6: Update signal_stacker.py

**Files:**
- Modify: `scripts/signal_stacker.py`
- Modify: `tests/unit/test_signal_stacker.py`

- [ ] **Step 1: Update test_signal_stacker.py**

Update tests to:
- Build `SignalForceConfig` from fixture or inline dict
- Pass config to `SignalStacker(config=config, use_intent_scoring=True)`
- Create `Signal` objects with `signal_type="github"` (string) instead of `SignalType` enum
- Update `ScanResult` construction: `scan_type="github"` (string)
- Remove any imports of deleted enums

- [ ] **Step 2: Run tests — verify FAIL**

Run: `pytest tests/unit/test_signal_stacker.py -v`
Expected: FAIL — `SignalStacker` doesn't accept config yet

- [ ] **Step 3: Modify signal_stacker.py**

1. Add import: `from scripts.config_loader import SignalForceConfig`
2. Remove import of `SignalType` (no longer needed)
3. Change `SignalStacker.__init__` to accept `config: SignalForceConfig | None = None`:
   ```python
   def __init__(
       self,
       known_domains: dict[str, str] | None = None,
       use_intent_scoring: bool = False,
       config: SignalForceConfig | None = None,
   ) -> None:
       self._known_domains = known_domains or {}
       self.use_intent_scoring = use_intent_scoring
       self._config = config
   ```
4. Update line 99: `IntentScorer().score_signals(...)` → `IntentScorer(self._config).score_signals(...)` (only when `use_intent_scoring=True` and `self._config` is not None)
5. Update `stack_from_files` to accept optional `config` parameter and pass through
6. Update CLI `main` to load config and pass to stacker
7. Update module docstring

- [ ] **Step 4: Run tests — verify PASS**

Run: `pytest tests/unit/test_signal_stacker.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
ruff format scripts/signal_stacker.py tests/unit/test_signal_stacker.py
git add scripts/signal_stacker.py tests/unit/test_signal_stacker.py
git commit -m "refactor: SignalStacker accepts config, threads to IntentScorer"
```

---

### Task 7: Update multi_channel_sequencer.py

**Files:**
- Modify: `scripts/multi_channel_sequencer.py`
- Modify: `tests/unit/test_multi_channel_sequencer.py`

- [ ] **Step 1: Update test_multi_channel_sequencer.py**

Change all `SignalType.GITHUB_RL_REPO` references to `"github"` (string). Remove `SignalType` import.

- [ ] **Step 2: Run tests — verify FAIL**

Run: `pytest tests/unit/test_multi_channel_sequencer.py -v`
Expected: FAIL — `build_sequence` still expects `SignalType` enum

- [ ] **Step 3: Modify multi_channel_sequencer.py**

1. Remove import of `SignalType`
2. Change `_TEMPLATE_MAP` keys from `SignalType` enum → plain strings:
   ```python
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
   ```
3. Change `build_sequence` signature: `signal_type: SignalType` → `signal_type: str`
4. Remove "RL" from template names: `"github-rl-signal"` → `"github-signal"`

**Note:** The template map references template names that will only match on disk after Task 11 renames the template files (e.g., `github-rl-signal.md` → `github-signal.md`). This is expected — the sequencer code is updated first, template files renamed later. Tests mock template resolution, so they pass independently.

- [ ] **Step 4: Run tests — verify PASS**

Run: `pytest tests/unit/test_multi_channel_sequencer.py -v`
Expected: All PASS

- [ ] **Step 5: Run full test suite**

Run: `pytest --tb=short -q`
Expected: All tests in Phase 2 modified files pass. Scanner tests may still fail (fixed in Phase 3).

- [ ] **Step 6: Commit**

```bash
ruff format scripts/multi_channel_sequencer.py tests/unit/test_multi_channel_sequencer.py
git add scripts/multi_channel_sequencer.py tests/unit/test_multi_channel_sequencer.py
git commit -m "refactor: multi_channel_sequencer uses string signal types"
```

---

## Phase 3: Scanner Package

### Task 8: Scanner Package Scaffolding

**Files:**
- Create: `scripts/scanners/__init__.py`
- Create: `scripts/scanners/base.py`

- [ ] **Step 1: Create the scanners package**

```python
# scripts/scanners/__init__.py
"""Scanner package. Each scanner implements scan(ScannerConfig) -> ScanResult."""

from scripts.scanners.base import ScannerConfig, ScanResult, Signal, SignalStrength

__all__ = ["ScannerConfig", "ScanResult", "Signal", "SignalStrength"]
```

```python
# scripts/scanners/base.py
"""Base exports for scanner modules.

Scanners import from here to get the types they need:
    from scripts.scanners.base import ScannerConfig, ScanResult, Signal, SignalStrength
"""

from scripts.config_loader import ScannerConfig
from scripts.models import ScanResult, Signal, SignalStrength

__all__ = ["ScannerConfig", "ScanResult", "Signal", "SignalStrength"]
```

- [ ] **Step 2: Verify imports work**

Run: `python -c "from scripts.scanners.base import ScannerConfig, ScanResult, Signal, SignalStrength; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add scripts/scanners/__init__.py scripts/scanners/base.py
git commit -m "feat: add scanners package with base exports"
```

---

### Task 9: Scanner Runner

**Files:**
- Create: `scripts/scanner_runner.py`
- Create: `tests/unit/test_scanner_runner.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_scanner_runner.py
"""Tests for dynamic scanner dispatch."""

from __future__ import annotations

from datetime import datetime, UTC
from pathlib import Path
from unittest.mock import MagicMock, patch
import logging

import pytest

from scripts.config_loader import load_config, ScannerConfig, SignalForceConfig
from scripts.models import ScanResult, Signal, SignalStrength
from scripts.scanner_runner import run_all_scanners, _has_keywords

_FIXTURES = Path(__file__).parent.parent / "fixtures"


def _make_signal(signal_type: str = "github") -> Signal:
    return Signal(
        signal_type=signal_type,
        company_name="Test Co",
        signal_strength=SignalStrength.STRONG,
        source_url="https://example.com",
        raw_data={},
    )


def _make_scan_result(signals: list[Signal] | None = None) -> ScanResult:
    now = datetime.now(UTC)
    return ScanResult(
        scan_type="github",
        started_at=now,
        completed_at=now,
        signals_found=signals or [_make_signal()],
        total_raw_results=1,
        total_after_dedup=1,
    )


class TestRunAllScanners:
    def test_skips_disabled_scanner(self) -> None:
        config = load_config(_FIXTURES / "sample_config.yaml")
        # arxiv is disabled in sample_config.yaml
        with patch("scripts.scanner_runner.importlib") as mock_imp:
            run_all_scanners(config)
            # Should only import github, not arxiv
            mock_imp.import_module.assert_called_once()
            call_arg = mock_imp.import_module.call_args[0][0]
            assert "github" in call_arg

    def test_handles_missing_module(self, caplog: pytest.LogCaptureFixture) -> None:
        config = load_config(_FIXTURES / "sample_config.yaml")
        with caplog.at_level(logging.ERROR):
            signals = run_all_scanners(config)
        # Module doesn't exist, should log error and return empty
        assert "not found" in caplog.text.lower() or len(signals) == 0

    def test_handles_scanner_exception(self) -> None:
        config = load_config(_FIXTURES / "sample_config.yaml")
        mock_module = MagicMock()
        mock_module.scan.side_effect = RuntimeError("boom")
        with patch("scripts.scanner_runner.importlib.import_module", return_value=mock_module):
            signals = run_all_scanners(config)
        assert signals == []

    def test_collects_signals_from_scanner(self) -> None:
        config = load_config(_FIXTURES / "sample_config.yaml")
        mock_module = MagicMock()
        mock_module.scan.return_value = _make_scan_result([_make_signal()])
        with patch("scripts.scanner_runner.importlib.import_module", return_value=mock_module):
            signals = run_all_scanners(config)
        assert len(signals) == 1
        assert signals[0].company_name == "Test Co"


class TestHasKeywords:
    def test_empty_config(self) -> None:
        config = ScannerConfig(module="test")
        assert _has_keywords(config) is False

    def test_with_keywords(self) -> None:
        config = ScannerConfig(module="test", keywords=["k1"])
        assert _has_keywords(config) is True

    def test_with_topics(self) -> None:
        config = ScannerConfig(module="test", topics=["t1"])
        assert _has_keywords(config) is True
```

- [ ] **Step 2: Run tests — verify FAIL**

Run: `pytest tests/unit/test_scanner_runner.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.scanner_runner'`

- [ ] **Step 3: Implement scanner_runner.py**

```python
# scripts/scanner_runner.py
"""Dynamic scanner dispatch engine.

Loads scanner modules specified in config.yaml and runs them.
Each scanner implements: scan(ScannerConfig) -> ScanResult.
"""

from __future__ import annotations

import importlib
import logging

from scripts.config_loader import ScannerConfig, SignalForceConfig
from scripts.models import ScanResult, Signal

logger = logging.getLogger(__name__)


def run_all_scanners(config: SignalForceConfig) -> list[Signal]:
    """Run all enabled scanners and return a flat list of Signal objects.

    Each scanner returns a ScanResult (containing signals_found: list[Signal]).
    This runner flattens them into a single list for downstream processing.
    Failed scanners are logged and skipped — one scanner's failure does not
    block the others.
    """
    all_signals: list[Signal] = []

    for name, scanner_config in config.scanners.items():
        if not scanner_config.enabled:
            logger.info("Scanner '%s' disabled, skipping", name)
            continue

        if not _has_keywords(scanner_config):
            logger.warning(
                "Scanner '%s' enabled but no keywords configured — will return no results",
                name,
            )

        try:
            module = importlib.import_module(scanner_config.module)
            scan_fn = getattr(module, "scan")
            result: ScanResult = scan_fn(scanner_config)
            logger.info("Scanner '%s' returned %d signals", name, len(result.signals_found))
            all_signals.extend(result.signals_found)
        except ModuleNotFoundError:
            logger.error("Scanner module '%s' not found for '%s'", scanner_config.module, name)
        except AttributeError:
            logger.error("Module '%s' has no scan() function", scanner_config.module)
        except Exception:
            logger.exception("Scanner '%s' failed, skipping", name)

    return all_signals


def _has_keywords(config: ScannerConfig) -> bool:
    """Check if a scanner config has any search terms configured."""
    return bool(
        config.keywords
        or config.topics
        or config.libraries
        or config.queries
        or config.training_tags
        or config.card_keywords
        or config.titles
        or config.skills
    )
```

- [ ] **Step 4: Run tests — verify PASS**

Run: `pytest tests/unit/test_scanner_runner.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
ruff format scripts/scanner_runner.py tests/unit/test_scanner_runner.py
git add scripts/scanner_runner.py tests/unit/test_scanner_runner.py
git commit -m "feat: add scanner runner with dynamic module dispatch"
```

---

### Task 10: Refactor Scanners (all 6)

**Files:** 6 scanner moves + 6 test updates (see sub-tasks below)

**Transformation pattern (same for all 6):**
1. `git mv` the file to `scripts/scanners/`
2. Remove hardcoded keyword constants
3. Remove class wrapper → extract to module-level `scan(config: ScannerConfig) -> ScanResult`
4. Read keywords/topics/libraries from `config` parameter
5. Keep all API interaction logic unchanged
6. Add `from scripts.scanners.base import ScannerConfig, ScanResult, Signal, SignalStrength`
7. Remove `SignalType` imports → use string signal types
8. Update `if __name__ == "__main__"` to load config first
9. Update module docstring: remove "RL" references
10. Update test: new import path, `ScannerConfig` fixture, string signal types

---

#### Task 10a: GitHub Scanner

- [ ] **Move:** `git mv scripts/github_rl_scanner.py scripts/scanners/github_scanner.py`
- [ ] **Transform:** Remove `RL_TOPICS`, `RL_LIBRARIES`. Signal type: `"github_repo"`. Scanner validates `repo_name` in metadata (moved from models.py validator).
- [ ] **Update test:** `tests/unit/test_github_rl_scanner.py` — update imports to `from scripts.scanners.github_scanner import scan`
- [ ] **Run:** `pytest tests/unit/test_github_rl_scanner.py -v` → PASS
- [ ] **Commit:** `git commit -m "refactor: move github scanner to scanners package, read config"`

#### Task 10b: ArXiv Scanner

- [ ] **Move:** `git mv scripts/arxiv_monitor.py scripts/scanners/arxiv_scanner.py`
- [ ] **Transform:** Remove `RL_SEARCH_QUERIES`. Signal type: `"arxiv_paper"`. Semantic Scholar API key stays in `config.py` (env vars), not config.yaml.
- [ ] **Update test:** `tests/unit/test_arxiv_monitor.py` — update imports
- [ ] **Run:** `pytest tests/unit/test_arxiv_monitor.py -v` → PASS
- [ ] **Commit:** `git commit -m "refactor: move arxiv scanner to scanners package, read config"`

#### Task 10c: HuggingFace Scanner

- [ ] **Move:** `git mv scripts/hf_model_monitor.py scripts/scanners/hf_scanner.py`
- [ ] **Transform:** Remove `RL_TRAINING_TAGS`, `RL_KEYWORDS_IN_CARD`. Signal type: `"huggingface_model"`. Reads `training_tags` and `card_keywords` from config.
- [ ] **Update test:** `tests/unit/test_hf_model_monitor.py` — update imports
- [ ] **Run:** `pytest tests/unit/test_hf_model_monitor.py -v` → PASS
- [ ] **Commit:** `git commit -m "refactor: move hf scanner to scanners package, read config"`

#### Task 10d: Job Posting Scanner

- [ ] **Move:** `git mv scripts/job_posting_scanner.py scripts/scanners/job_scanner.py`
- [ ] **Transform:** Remove `_RL_SKILLS`, `JOB_TITLES`. Signal type: `"job_posting"`. Reads `titles` and `skills` from config.
- [ ] **Update test:** `tests/unit/test_job_posting_scanner.py` — update imports
- [ ] **Run:** `pytest tests/unit/test_job_posting_scanner.py -v` → PASS
- [ ] **Commit:** `git commit -m "refactor: move job scanner to scanners package, read config"`

#### Task 10e: Funding Scanner

- [ ] **Move:** `git mv scripts/funding_tracker.py scripts/scanners/funding_scanner.py`
- [ ] **Transform:** Remove hardcoded "reinforcement learning" from search queries. Signal type: `"funding_event"`. Reads `keywords` from config.
- [ ] **Update test:** `tests/unit/test_funding_tracker.py` — update imports
- [ ] **Run:** `pytest tests/unit/test_funding_tracker.py -v` → PASS
- [ ] **Commit:** `git commit -m "refactor: move funding scanner to scanners package, read config"`

#### Task 10f: LinkedIn Scanner

- [ ] **Move:** `git mv scripts/linkedin_activity.py scripts/scanners/linkedin_scanner.py`
- [ ] **Transform:** Remove `RL_KEYWORDS`. Signal type: `"linkedin_activity"`. Reads `keywords` from config.
- [ ] **Update test:** `tests/unit/test_linkedin_activity.py` — update imports
- [ ] **Run:** `pytest tests/unit/test_linkedin_activity.py -v` → PASS
- [ ] **Commit:** `git commit -m "refactor: move linkedin scanner to scanners package, read config"`

#### Task 10g: Full Suite Verification

- [ ] **Verify old files deleted:** No scanner files remain in `scripts/` (only in `scripts/scanners/`)
- [ ] **Run full suite:** `pytest --tb=short -q` → All PASS
- [ ] **Lint:** `ruff format scripts/scanners/ tests/unit/ && ruff check scripts/scanners/ tests/unit/ --fix`

---

## Phase 4: Config Content & Directory Structure

### Task 11: Create config.example/ with RL Defaults

**Files:**
- Create: `config.example/config.yaml`
- Move: `.agents/gtm-context.md` → `config.example/gtm-context.md`
- Move: `templates/email-sequences/*.md` → `config.example/templates/email-sequences/`
- Move: `templates/linkedin-sequences/*.md` → `config.example/templates/linkedin-sequences/`
- Modify: `.gitignore` (add `config/`)

- [ ] **Step 1: Create config.example/config.yaml**

Write the full RL config.yaml with:
- `company.name: "Collinear AI"`, product, category from current `.agents/gtm-context.md`
- `icp.tiers`: 4 tiers from current gtm-context (AI Lab, Agent Builder, Robotics, Industry)
- `icp.maturity_stages`: EXPLORING, BUILDING, SCALING, PRODUCTIONIZING
- `icp.target_titles`: from current gtm-context
- `scanners`: all 6 enabled with RL keywords extracted from old scanner constants
- `scoring`: current intent weights and half-lives

- [ ] **Step 2: Move gtm-context.md**

```bash
mkdir -p config.example
cp .agents/gtm-context.md config.example/gtm-context.md
```

- [ ] **Step 3: Move templates and rename to remove "rl" from filenames**

```bash
mkdir -p config.example/templates/email-sequences
mkdir -p config.example/templates/linkedin-sequences
cp -r templates/email-sequences/ config.example/templates/email-sequences/
cp -r templates/linkedin-sequences/ config.example/templates/linkedin-sequences/
```

Then rename template files to match the new `_TEMPLATE_MAP` values from Task 7:
- `github-rl-signal.md` → `github-signal.md` (both email + linkedin directories)
- All other template filenames remain unchanged (they don't contain "rl")

- [ ] **Step 4: Update .gitignore**

Add to `.gitignore`:
```
# User's active ICP config (generated by /setup or copied from examples)
config/
```

- [ ] **Step 5: Create examples/rl-infrastructure/**

```bash
cp -r config.example examples/rl-infrastructure
```

- [ ] **Step 6: Commit**

```bash
git add config.example/ examples/rl-infrastructure/ .gitignore
git commit -m "feat: create config.example/ and examples/rl-infrastructure/ with RL defaults"
```

---

### Task 12: Example ICP Configs

**Files:**
- Create: `examples/cybersecurity/config.yaml` + `gtm-context.md` + 2-3 templates
- Create: `examples/devtools/config.yaml` + `gtm-context.md` + 2-3 templates
- Create: `examples/data-infra/config.yaml` + `gtm-context.md` + 2-3 templates

- [ ] **Step 1: Generate example configs**

For each vertical, create:
1. `config.yaml` — scanner keywords, ICP tiers, scoring weights appropriate to the domain
2. `gtm-context.md` — positioning, voice, target personas
3. `templates/email-sequences/` — 2-3 signal-specific email templates

Use the spec's descriptions (Section "Example ICP Configs") for keywords and ICP definitions. Label each as "Example — customize for your use case."

Details per vertical:
- **cybersecurity**: OWASP, DAST, SAST, API security. HuggingFace disabled.
- **devtools**: developer experience, CI/CD, platform engineering. ArXiv + HuggingFace disabled.
- **data-infra**: data pipeline, ETL, Airflow, dbt. ArXiv enabled. HuggingFace disabled.

- [ ] **Step 2: Commit**

```bash
git add examples/cybersecurity/ examples/devtools/ examples/data-infra/
git commit -m "feat: add 3 example ICP configs (cybersecurity, devtools, data-infra)"
```

---

## Phase 5: Skills & Workflows

### Task 13: Update 11 Existing Skills

**Files:**
- Modify: all 11 `skills/*/SKILL.md` files

- [ ] **Step 1: For each skill, apply these changes:**

1. Replace `.agents/gtm-context.md` → `config/gtm-context.md` in any `@` references
2. Replace `templates/email-sequences/` → `config/templates/email-sequences/`
3. Replace `templates/linkedin-sequences/` → `config/templates/linkedin-sequences/`
4. Replace "RL maturity" → "domain maturity"
5. Replace "RL keywords" → "domain keywords"
6. Replace "reinforcement learning" → generic language about "your ICP's domain"
7. Replace "rl-gtm-engine" → "SignalForce"
8. Update signal-scanner description: remove "companies actively investing in reinforcement learning"
9. Update prospect-researcher: generalize RL maturity stages to reference config
10. Remove "Collinear AI" references from champion-tracker

- [ ] **Step 2: Commit**

```bash
git add skills/
git commit -m "refactor: update 11 skills to reference config/ and remove RL-specific language"
```

---

### Task 14: Create Setup Skill

**Files:**
- Create: `skills/setup/SKILL.md`

- [ ] **Step 1: Write the setup skill**

The skill should instruct Claude to:
1. Ask "What does your company sell, and who do you sell to?"
2. Auto-generate `config/config.yaml`, `config/gtm-context.md`, and `config/templates/` from the response
3. Present the inferred ICP for review ("Here's what I inferred... What did I get wrong?")
4. Iterate on corrections
5. Run `/validate` automatically before confirming
6. Reference `config.example/config.yaml` as the schema template

Follow writing-skills standards:
- YAML frontmatter: `name: setup`, `description: "Use when configuring SignalForce for a new ICP, when setting up the project for the first time, or when switching to a different target market"`
- Under 500 words
- No workflow summary in description

- [ ] **Step 2: Commit**

```bash
git add skills/setup/SKILL.md
git commit -m "feat: add /setup skill for hybrid ICP config generation"
```

---

### Task 15: Create Validate Skill

**Files:**
- Create: `skills/validate/SKILL.md`

- [ ] **Step 1: Write the validate skill**

The skill should instruct Claude to:
1. Load `config/config.yaml` and validate against Pydantic schema
2. For each scanner: check module is importable, has `scan()` function
3. For each enabled scanner: check matching templates exist in `config/templates/`
4. Warn on empty keyword lists for enabled scanners
5. Warn on missing optional fields
6. Print a summary report (OK/WARN/ERROR per check)

YAML frontmatter: `name: validate`, `description: "Use when verifying config.yaml is valid after editing, when troubleshooting why scanners return no results, or after running /setup to confirm the generated config works"`

- [ ] **Step 2: Commit**

```bash
git add skills/validate/SKILL.md
git commit -m "feat: add /validate skill for config validation"
```

---

### Task 16: Update n8n Workflows

**Files:**
- Modify: `n8n-workflows/daily-signal-scan.json`
- Modify: `n8n-workflows/sequence-launcher.json`
- Modify: `n8n-workflows/enrichment-pipeline.json`
- Modify: `n8n-workflows/crm-sync.json`

- [ ] **Step 1: Update daily-signal-scan.json**

1. Update scanner command paths: `scripts.github_rl_scanner` → `scripts.scanners.github_scanner` (all 6)
2. Add `--config config/config.yaml` flag to scanner invocations
3. Change Slack alert text: `"🚨 *A-Tier RL Signals Detected*"` → `"🚨 *A-Tier Signals Detected*"`

- [ ] **Step 2: Update sequence-launcher.json**

1. Update template routing to use string signal types
2. Change LLM prompt: remove "RL infrastructure", reference `config/gtm-context.md`
3. Update deal name template: remove "RL Signal"

- [ ] **Step 3: Minimal updates to enrichment-pipeline.json and crm-sync.json**

Remove any "RL" references in message strings. These workflows are already mostly generic.

- [ ] **Step 4: Commit**

```bash
git add n8n-workflows/
git commit -m "refactor: update n8n workflows for new scanner paths and generic messaging"
```

---

## Phase 6: Documentation & Rename

### Task 17: Project Rename

**Files:**
- Modify: All files containing "rl-gtm-engine"

- [ ] **Step 1: Find and replace across the codebase**

Search for `rl-gtm-engine` and `rl_gtm_engine` in all files. Replace with `SignalForce` or `signalforce` as appropriate. Key files:
- `CLAUDE.md`
- `README.md`
- `docs/architecture.md`
- `docs/user-guide.md`
- `docs/demo-walkthrough.md`
- `pyproject.toml` (if project name is set)
- All skill files (already done in Task 13)

- [ ] **Step 2: Commit**

```bash
git add -A
git commit -m "chore: rename project from rl-gtm-engine to SignalForce"
```

---

### Task 18: README Rewrite

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Rewrite README**

New structure:
1. **Header**: "SignalForce — Signal-based outbound sales engine"
2. **One-liner**: "Configure for any ICP. Detect buying signals, score intent, generate personalized outreach."
3. **30-second quickstart**: Clone → run `/setup` → scan
4. **How it works**: 3-layer architecture diagram (Skills → Scripts → n8n)
5. **Example**: Show the RL infrastructure example as a concrete demo
6. **Available skills**: Table of all 13 skills
7. **Custom scanners**: Brief guide to adding your own
8. **Examples directory**: Link to the 4 example configs
9. **Contributing**: Point to architecture.md

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: rewrite README for generic positioning with quickstart guide"
```

---

### Task 19: Update Architecture & CLAUDE.md

**Files:**
- Modify: `docs/architecture.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update architecture.md**

1. Replace "rl-gtm-engine" → "SignalForce" throughout
2. Update data flow diagram: add Config Loader between signal sources and scanners
3. Update scanner names: `github_rl_scanner` → `scanners.github_scanner`, etc.
4. Remove "reinforcement learning infrastructure buyers (Collinear AI's ICP)" → "configurable ICP"
5. Update Signal Sources table with new scanner paths
6. Update Data Model Relationships section for free-form strings
7. Add Design Decision: "Config-driven ICP" explaining the config.yaml / config.example/ pattern
8. Update External APIs table: clarify Semantic Scholar is used by arxiv_scanner for affiliation mapping

- [ ] **Step 2: Update CLAUDE.md**

1. Replace "rl-gtm-engine" → "SignalForce" throughout
2. Update Directory Structure section: add `config.example/`, `config/`, `examples/`, `scripts/scanners/`
3. Update Commands section: scanner paths now use `scripts.scanners.*`
4. Update Key Files section: add `scripts/config_loader.py`, `scripts/scanner_runner.py`
5. Remove `.agents/gtm-context.md` reference → `config/gtm-context.md`

- [ ] **Step 3: Commit**

```bash
git add docs/architecture.md CLAUDE.md
git commit -m "docs: update architecture and CLAUDE.md for configurable ICP"
```

---

### Task 20: Cleanup & TODOS.md

**Files:**
- Create: `TODOS.md`
- Modify: `.gitignore`
- Delete: `.agents/gtm-context.md` (moved to config.example/)

- [ ] **Step 1: Create TODOS.md**

```markdown
# TODOS

## P2: Community Config Repository
**What:** Create a separate GitHub repo (e.g., signalforce-configs) for community-contributed ICP configurations.
**Why:** Network effects — new users browse configs for their vertical instead of starting from scratch.
**Pros:** Viral adoption, reduced onboarding friction, community engagement.
**Cons:** Maintenance burden, quality control of submitted configs.
**Context:** Accepted as P2 during CEO review (2026-03-18). Depends on configurable ICP refactor shipping first. Users would submit PRs with their config.yaml + gtm-context.md + templates for their vertical.
**Effort:** M (human: ~1 week / CC: ~2 hours)
**Depends on:** Configurable ICP feature (this refactor)
```

- [ ] **Step 2: Remove deprecated .agents/ directory**

```bash
git rm -r .agents/
```

Add `.agents/` to `.gitignore` to prevent stale copies.

- [ ] **Step 3: Run full test suite — final verification**

Run: `pytest --cov=scripts --cov-report=term-missing -v`
Expected: All PASS, coverage ≥ 80%

- [ ] **Step 4: Lint entire project**

```bash
ruff format .
ruff check . --fix
```

- [ ] **Step 5: Commit**

```bash
git add TODOS.md .gitignore
git rm -r .agents/ 2>/dev/null || true
git add -A
git commit -m "chore: add TODOS.md, remove deprecated .agents/, final cleanup"
```

---

## Execution Order & Dependencies

```
Phase 1: Config Foundation
  Task 1 (config_loader) ─────────────────────┐
  Task 2 (first-run guard tests)               │
                                               │
Phase 2: Models & Scoring                      │
  Task 3 (models.py)     ←── depends on ───────┘
  Task 4 (recency.py)    ←── depends on Task 3
  Task 5 (intent_scorer)  ←── depends on Task 3 + Task 1
  Task 6 (signal_stacker) ←── depends on Task 5
  Task 7 (sequencer)      ←── depends on Task 3
                                               │
Phase 3: Scanner Package                       │
  Task 8 (base.py)       ←── depends on Task 1 │
  Task 9 (scanner_runner) ←── depends on Task 8 │
  Task 10 (6 scanners)   ←── depends on Task 8 + Task 3
                                               │
Phase 4: Config Content                        │
  Task 11 (config.example) ←── depends on Task 10 (needs scanner keywords)
  Task 12 (example configs) ←── depends on Task 11
                                               │
Phase 5: Skills & Workflows                    │
  Task 13 (update skills) ←── depends on Task 11
  Task 14 (setup skill)   ←── depends on Task 11
  Task 15 (validate skill) ←── depends on Task 1
  Task 16 (n8n workflows) ←── depends on Task 10
                                               │
Phase 6: Docs & Rename                         │
  Task 17 (project rename) ←── can run anytime after Phase 3
  Task 18 (README)         ←── depends on Task 17
  Task 19 (architecture)   ←── depends on Task 17
  Task 20 (cleanup)        ←── LAST — depends on everything
```

**Parallelizable within phases:**
- Phase 2: Tasks 3-4 can run before Task 5-7
- Phase 3: Task 8 can run in parallel with Phase 2
- Phase 5: Tasks 13, 14, 15, 16 are independent of each other
- Phase 6: Tasks 17, 18, 19 can run in parallel
