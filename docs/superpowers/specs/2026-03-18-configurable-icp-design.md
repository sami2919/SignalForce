# Configurable ICP — Design Spec

## Problem

SignalForce is hardcoded to one ICP: reinforcement learning infrastructure buyers (Collinear AI). RL-specific content is embedded across 30+ files — scanner keyword lists, email templates, ICP tier definitions, scoring rubrics, n8n workflows, and documentation. Anyone who wants to use SignalForce for a different vertical must hunt through every file and replace RL content manually. This is the #1 barrier to open-source adoption.

## Goal

Make SignalForce configurable so any company can use it with their own ICP. A new user should go from "I sell X to Y" to a running signal detection + outreach pipeline in under 5 minutes.

## Approach

**Extract & Configure** — Pull all domain-specific content into a config directory. The engine reads from config at runtime. Ship the RL configuration as a working example. Add a setup skill that auto-generates config from a company description.

Two tiers of configurability:
1. **Config file** (`config.yaml`) for structured data — keywords, search queries, job titles, ICP tiers, scoring weights, signal types, scanner module paths.
2. **Template directory** (`config/templates/`) for outreach copy — users write or generate email/LinkedIn templates for their domain.

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Approach | Extract & Configure (not plugin SDK, not YAML-only) | Fully adoptable without over-engineering |
| Config git strategy | `config/` gitignored, `config.example/` committed | Mirrors `.env` / `.env.example` pattern |
| Signal types | Free-form strings (not hardcoded enums) | Zero code changes when switching domains |
| Maturity stages | Defined in config (not code enums) | Each ICP defines its own maturity model |
| Scanner interface | Convention-based (`scan(ScannerConfig) -> list[ScanResult]`) | Simple, no registry needed, `module` field enables custom scanners |
| Empty keyword behavior | Warn + continue (scanner returns []) | Prevents silent "why no signals?" debugging |
| Setup skill mode | Hybrid (auto-generate draft, then iterate) | Respects user time while catching bad inferences |
| Project name | Rename rl-gtm-engine to SignalForce | Domain-neutral for public launch |

---

## Architecture

### Directory Structure (after refactoring)

```
SignalForce/
├── config.example/                  # Committed — reference config
│   ├── config.yaml                  # Master config schema with RL defaults
│   ├── gtm-context.md               # Positioning, voice, personas
│   └── templates/
│       ├── email-sequences/         # Signal-specific email templates
│       └── linkedin-sequences/      # Signal-specific LinkedIn templates
│
├── config/                          # Gitignored — user's active config
│   └── (same structure as config.example/)
│
├── examples/                        # Committed — multi-vertical examples
│   ├── rl-infrastructure/           # Current RL config (full working example)
│   ├── cybersecurity/               # API security tools → DevSecOps
│   ├── devtools/                    # Dev productivity → engineering leads
│   └── data-infra/                  # Data pipeline tools → data engineers
│
├── scripts/
│   ├── scanners/                    # Refactored from flat scripts/
│   │   ├── base.py                  # ScannerConfig + ScanResult models, scan() protocol
│   │   ├── github_scanner.py        # Reads keywords from config
│   │   ├── arxiv_scanner.py
│   │   ├── hf_scanner.py
│   │   ├── job_scanner.py
│   │   ├── funding_scanner.py
│   │   └── linkedin_scanner.py
│   ├── config_loader.py             # NEW — loads + validates config.yaml
│   ├── scanner_runner.py            # NEW — dynamic scanner dispatch
│   ├── models.py                    # Generalized (no RL-specific enums)
│   ├── intent_scorer.py             # Reads weights from config
│   ├── signal_stacker.py            # Updated: accepts config, passes to IntentScorer
│   ├── recency.py                   # Reads half-lives from config
│   ├── multi_channel_sequencer.py   # Reads template mapping from config
│   ├── config.py                    # Unchanged (env vars / API keys)
│   └── api_client.py                # Unchanged
│
├── skills/
│   ├── setup/SKILL.md               # NEW — hybrid config generation wizard
│   ├── validate/SKILL.md            # NEW — config validation checker
│   └── ...existing skills...        # Updated to read from config/
│
├── templates/
│   └── scoring-rubrics/
│       └── icp-scoring-model.md     # Formula stays, examples reference config
│
├── tests/
│   ├── unit/
│   │   ├── test_config_loader.py    # NEW
│   │   ├── test_scanner_runner.py   # NEW
│   │   └── ...existing tests...     # Updated for config injection
│   └── fixtures/
│       └── sample_config.yaml       # NEW — test fixture
│
└── docs/                            # Updated for generic positioning
```

### System Flow

```
config.example/              config/                    examples/
(committed, reference)       (gitignored, user's)       (committed, multi-vertical)
     │                            │                          │
     │   cp -r config.example/    │   cp -r examples/X/      │
     │   config/                  │   config/                │
     └────────────────────────────┤────────────────────────────┘
                                  │
                                  ▼
            ┌─────────────────────────────────────────┐
            │         CONFIG LOADER (new)              │
            │  scripts/config_loader.py                │
            │  1. Check config/ exists (first-run)     │
            │  2. Parse YAML                           │
            │  3. Validate with Pydantic               │
            │  4. Return typed SignalForceConfig        │
            └────────────────┬────────────────────────┘
                             │ SignalForceConfig
                             ▼
            ┌─────────────────────────────────────────┐
            │        SCANNER RUNNER (new)              │
            │  scripts/scanner_runner.py               │
            │  For each enabled scanner:               │
            │    importlib.import_module(module)        │
            │    module.scan(ScannerConfig)             │
            │    → list[ScanResult]                    │
            │  Skips disabled, logs warnings            │
            └────────────────┬────────────────────────┘
                             │ list[ScanResult]
                             ▼
            ┌─────────────────────────────────────────┐
            │           ENGINE (unchanged)             │
            │  intent_scorer → signal_stacker →        │
            │  multi_channel_sequencer                 │
            │  (weights + half-lives from config)      │
            └────────────────┬────────────────────────┘
                             │
                             ▼
            ┌─────────────────────────────────────────┐
            │         SKILLS (updated)                 │
            │  Read from config/ for ICP context       │
            │  Reference config/gtm-context.md         │
            │  Use config/templates/ for outreach      │
            └─────────────────────────────────────────┘
```

---

## Config Schema

### config.yaml

```yaml
# SignalForce Configuration
# Generated by /setup or copied from examples/

company:
  name: "Acme Corp"
  product: "One-line product description"
  category: "Product category"
  website: "https://acme.com"

icp:
  tiers:
    - name: "Tier 1 Name"
      description: "Who these buyers are"
      signals: ["signal indicators for this tier"]
    - name: "Tier 2 Name"
      description: "..."
      signals: ["..."]

  maturity_stages:
    # User-defined progression model (replaces RLMaturityStage)
    - EXPLORING
    - BUILDING
    - SCALING
    - EMBEDDED

  target_titles:
    - "Title 1"
    - "Title 2"

  disqualifiers:
    - "No activity in target domain"

scanners:
  github:
    enabled: true
    module: scripts.scanners.github_scanner
    topics: ["topic-1", "topic-2"]
    libraries: ["lib-1", "lib-2"]
    keywords: ["keyword-1", "keyword-2"]
    lookback_days: 7
  arxiv:
    enabled: true
    module: scripts.scanners.arxiv_scanner
    queries: ["search query 1", "search query 2"]
    lookback_days: 14
  huggingface:
    enabled: true
    module: scripts.scanners.hf_scanner
    training_tags: ["tag-1", "tag-2"]
    card_keywords: ["keyword-1", "keyword-2"]
    lookback_days: 7
  jobs:
    enabled: true
    module: scripts.scanners.job_scanner
    titles: ["Job Title 1", "Job Title 2"]
    skills: ["skill-1", "skill-2"]
    lookback_days: 14
  funding:
    enabled: true
    module: scripts.scanners.funding_scanner
    keywords: ["industry keyword 1", "industry keyword 2"]
    lookback_days: 30
  linkedin:
    enabled: true
    module: scripts.scanners.linkedin_scanner
    keywords: ["keyword-1", "keyword-2"]
    lookback_days: 2

scoring:
  intent_weights:
    github: 2.5
    arxiv: 3.0
    huggingface: 2.5
    jobs: 2.0
    funding: 1.5
    linkedin: 3.0
  half_lives_days:
    github: 5
    arxiv: 10
    huggingface: 7
    jobs: 10
    funding: 21
    linkedin: 2
  icp_weight: 0.4
  intent_weight: 0.6
  grade_thresholds:
    A: 8.0
    B: 5.0
    C: 2.0
    # D is implicit: any score below C threshold
```

### Config Pydantic Models

```python
# scripts/config_loader.py

from pathlib import Path
from pydantic import BaseModel, ConfigDict
import yaml

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_CONFIG_DIR = _PROJECT_ROOT / "config"
_CONFIG_FILE = _CONFIG_DIR / "config.yaml"
_EXAMPLE_DIR = _PROJECT_ROOT / "config.example"


class CompanyConfig(BaseModel, frozen=True):
    model_config = ConfigDict(extra="ignore")
    name: str
    product: str
    category: str
    website: str = ""


class ICPTierConfig(BaseModel, frozen=True):
    model_config = ConfigDict(extra="ignore")
    name: str
    description: str
    signals: list[str] = []


class ICPConfig(BaseModel, frozen=True):
    model_config = ConfigDict(extra="ignore")
    tiers: list[ICPTierConfig]
    maturity_stages: list[str]
    target_titles: list[str]
    disqualifiers: list[str] = []


class ScannerConfig(BaseModel, frozen=True):
    model_config = ConfigDict(extra="ignore")
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
    custom_params: dict[str, object] = {}  # escape hatch for custom scanners


class ScoringConfig(BaseModel, frozen=True):
    model_config = ConfigDict(extra="ignore")
    intent_weights: dict[str, float]
    half_lives_days: dict[str, float]
    icp_weight: float = 0.4
    intent_weight: float = 0.6
    grade_thresholds: dict[str, float] = {
        "A": 8.0, "B": 5.0, "C": 2.0,
    }


class SignalForceConfig(BaseModel, frozen=True):
    model_config = ConfigDict(extra="ignore")
    company: CompanyConfig
    icp: ICPConfig
    scanners: dict[str, ScannerConfig]
    scoring: ScoringConfig


def load_config(config_path: Path = _CONFIG_FILE) -> SignalForceConfig:
    """Load and validate SignalForce configuration.

    Raises FileNotFoundError with helpful message if config missing.
    Raises yaml.YAMLError or pydantic.ValidationError on bad config.
    """
    if not config_path.exists():
        raise FileNotFoundError(
            f"No config found at {config_path}. "
            "Run the /setup skill to configure SignalForce for your ICP, "
            "or copy an example: cp -r config.example/ config/"
        )
    raw = yaml.safe_load(config_path.read_text())
    return SignalForceConfig.model_validate(raw)
```

---

## Scanner Interface

### Key Terminology

The existing codebase has two relevant models:
- **`Signal`** (models.py line 124) — A single detected market signal (company, type, strength, URL, metadata). This is the per-signal record.
- **`ScanResult`** (models.py line 255) — A scan-run summary containing `signals_found: list[Signal]`, timing info, and error counts.

Both models are preserved. Scanners return `ScanResult` (which wraps a list of `Signal` objects), matching the existing contract.

### Protocol

Every scanner — built-in or custom — implements one function:

```python
def scan(config: ScannerConfig) -> ScanResult:
    """Run a scan using the provided configuration. Returns a ScanResult containing Signal objects."""
    ...
```

The `Signal` model is updated to use free-form strings for `signal_type` (see Models Generalization below), but `SignalStrength` remains an `IntEnum` (WEAK=1, MODERATE=2, STRONG=3) because the scoring engine uses it numerically in `signal_strength * intent_weight * recency_decay`.

### Scanner base module

```python
# scripts/scanners/base.py

# Re-export the models that scanners need
from scripts.config_loader import ScannerConfig
from scripts.models import ScanResult, Signal, SignalStrength

__all__ = ["ScannerConfig", "ScanResult", "Signal", "SignalStrength"]
```

```python
# scripts/scanners/__init__.py

"""Scanner package. Each scanner implements scan(ScannerConfig) -> ScanResult."""
from scripts.scanners.base import ScannerConfig, ScanResult, Signal, SignalStrength

__all__ = ["ScannerConfig", "ScanResult", "Signal", "SignalStrength"]
```

### Scanner Runner

```python
# scripts/scanner_runner.py

import importlib
import logging

from scripts.config_loader import SignalForceConfig
from scripts.models import ScanResult, Signal

logger = logging.getLogger(__name__)

def run_all_scanners(config: SignalForceConfig) -> list[Signal]:
    """Run all enabled scanners and return a flat list of Signal objects.

    Each scanner returns a ScanResult (which contains signals_found: list[Signal]).
    This runner flattens them into a single list for downstream processing.
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
    return bool(
        config.keywords or config.topics or config.libraries
        or config.queries or config.training_tags or config.card_keywords
        or config.titles or config.skills
    )
```

### Custom Scanner Example

A user who wants to add a CVE database scanner:

```python
# scripts/custom/cve_scanner.py

from datetime import datetime, UTC
from scripts.scanners.base import ScannerConfig, ScanResult, Signal, SignalStrength

def scan(config: ScannerConfig) -> ScanResult:
    started = datetime.now(UTC)
    signals = []  # Hit NVD API with config.keywords, build Signal objects
    # ... API logic here ...
    return ScanResult(
        scan_type="cve_alert",
        started_at=started,
        completed_at=datetime.now(UTC),
        signals_found=signals,
        total_raw_results=len(signals),
        total_after_dedup=len(signals),
    )
```

```yaml
# config/config.yaml (add to scanners section)
scanners:
  arxiv:
    enabled: false         # not relevant for cybersecurity ICP
  custom_cve:
    enabled: true
    module: scripts.custom.cve_scanner
    keywords: ["RCE", "authentication bypass", "API vulnerability"]
```

---

## Models Generalization

### Changes to scripts/models.py

```
BEFORE                              AFTER
─────────────────────────────       ─────────────────────────────
SignalType (enum)                   signal_type: str (free-form)
  GITHUB_RL_REPO                      "github_repo"
  ARXIV_PAPER                         "arxiv_paper"
  JOB_POSTING                         "job_posting"
  HUGGINGFACE_MODEL                   "huggingface_model"
  FUNDING_EVENT                       "funding_event"
  LINKEDIN_ACTIVITY                   "linkedin_activity"

RLMaturityStage (enum)              maturity_stage: str (free-form)
  PRODUCTIONIZING                     (from config.icp.maturity_stages)
  SCALING
  BUILDING
  EXPLORING
  NONE

ICPTier (enum)                      icp_tier: str (free-form)
  TIER_1_AI_LAB                       (from config.icp.tiers[].name)
  TIER_2_AGENT_BUILDER
  TIER_3_ROBOTICS
  TIER_4_INDUSTRY

ContactTitle (enum)                 target_title: str (free-form)
  RL_ENGINEER                         (from config.icp.target_titles)
  ...

ScanResult.scan_type (SignalType)   scan_type: str (free-form)
                                      Matches signal_type strings
```

### Enums that REMAIN (domain-agnostic)
- `SignalStrength` (IntEnum: WEAK=1, MODERATE=2, STRONG=3) — **must stay as IntEnum** because `intent_scorer.py` uses it numerically: `int(signal.signal_strength) * intent_weight * recency_decay`
- `ICPScore` (A, B, C, D) — grade labels are universal
- `DealStage` — pipeline stages are universal
- `OutreachChannel` (EMAIL, LINKEDIN, LINKEDIN_INMAIL) — universal
- `EmailVariant` (PROBLEM_FOCUSED, OUTCOME_FOCUSED, SOCIAL_PROOF_FOCUSED) — universal
- `EnrichmentSource` (APOLLO, HUNTER, PROSPEO, etc.) — universal

### Signal model validator change

The existing `Signal.validate_github_metadata` validator (models.py line 139) checks `signal_type == SignalType.GITHUB_RL_REPO` and requires `repo_name` in metadata. With free-form signal types, this validator is **removed from the shared model**. Signal-type-specific validation moves into each scanner — the GitHub scanner is responsible for ensuring its signals contain `repo_name` in metadata before returning them.

```python
# BEFORE (models.py — shared model)
@model_validator(mode="after")
def validate_github_metadata(self) -> "Signal":
    if self.signal_type == SignalType.GITHUB_RL_REPO:
        if "repo_name" not in self.metadata:
            raise ValueError(...)
    return self

# AFTER — validator removed from Signal model
# GitHub scanner validates its own output before returning ScanResult
```

### intent_scorer.py and recency.py refactoring

Both files currently use `SignalType` enum as dict keys. After refactoring, they read weights and half-lives from config:

```python
# BEFORE (intent_scorer.py)
INTENT_WEIGHTS: dict[SignalType, float] = {
    SignalType.LINKEDIN_ACTIVITY: 3.0,
    SignalType.ARXIV_PAPER: 3.0,
    ...
}
_HALF_LIVES: dict[SignalType, float] = {
    SignalType.GITHUB_RL_REPO: SignalHalfLife.GITHUB_RL_REPO,
    ...
}

# AFTER (intent_scorer.py) — reads from config, keyed by string
class IntentScorer:
    def __init__(self, config: SignalForceConfig):
        self._weights: dict[str, float] = config.scoring.intent_weights
        self._half_lives: dict[str, float] = config.scoring.half_lives_days
        self._icp_weight = config.scoring.icp_weight
        self._intent_weight = config.scoring.intent_weight
        self._grade_thresholds = config.scoring.grade_thresholds

    def score_signals(self, signals: list[Signal], icp_fit: float, ...) -> ScoringResult:
        # Same math, but uses self._weights[signal.signal_type]
        # with fallback: self._weights.get(signal.signal_type, 1.0)
        ...
```

```python
# BEFORE (recency.py)
class SignalHalfLife:
    GITHUB_RL_REPO = 5
    ARXIV_PAPER = 10
    ...

# AFTER (recency.py) — SignalHalfLife class REMOVED
# Half-lives come from config.scoring.half_lives_days
# The calculate_decay_factor() and apply_recency_weight() functions are unchanged
# (they already accept half_life_days as a parameter)
```

### signal_stacker.py config threading

`SignalStacker` currently instantiates `IntentScorer()` with no args. After refactoring, it must accept a `SignalForceConfig` and pass it to `IntentScorer(config)`. The stacker's public API changes:

```python
# BEFORE
stacker = SignalStacker()
profiles = stacker.stack_signals(scan_results)

# AFTER
stacker = SignalStacker(config)
profiles = stacker.stack_signals(scan_results)
```

The CLI `__main__` block loads config first, then passes it to the stacker. Same pattern as the scanners.

### Breadth multiplier

`_BREADTH_MULTIPLIER` and `_BREADTH_FALLBACK` in intent_scorer.py remain as hardcoded constants (not moved to config). Rationale: these are scoring mechanics, not domain-specific values. The multiplier rewards signal breadth regardless of which domain you're scanning for. If a future user wants to tune these, it's a straightforward follow-up to add `breadth_multiplier` to the scoring config.

### config.py naming distinction

The existing `scripts/config.py` handles **secrets and API keys** (loaded from `.env` via python-dotenv). The new `scripts/config_loader.py` handles **ICP configuration** (loaded from `config/config.yaml`). These are distinct responsibilities:
- `config.py` → "What API keys do I have?" (secrets, environment)
- `config_loader.py` → "What am I scanning for?" (domain, keywords, scoring)

Both are kept. No renaming needed — the naming distinction is clear.

---

## Setup Skill (/setup)

### Behavior

Hybrid mode: auto-generate draft from minimal input, then iterate.

**Step 1: Gather minimal input**
```
Claude: "What does your company sell, and who do you sell to?"
User:   "We sell API security testing tools to enterprise DevSecOps teams"
```

**Step 2: Auto-generate draft config**
Claude uses its knowledge of the industry to generate:
- `config/config.yaml` with keywords, job titles, ICP tiers, scoring weights
- `config/gtm-context.md` with positioning, voice, personas
- `config/templates/` with draft outreach copy for each enabled signal type

**Step 3: Present for review**
```
Claude: "Here's what I inferred:
  - ICP Tier 1: Enterprise security teams (500+ employees, dedicated AppSec)
  - ICP Tier 2: API-first SaaS companies (large API surface, no dedicated security)
  - Key signals: GitHub security repos, security conference papers, AppSec hiring
  - Disabled: HuggingFace scanner (not relevant for cybersecurity)

  What did I get wrong?"
```

**Step 4: Iterate**
User corrects any misses. Claude regenerates affected sections.

**Step 5: Validate**
Automatically runs `/validate` on the generated config before confirming.

### Skill File Structure

```
skills/
  setup/
    SKILL.md        # Hybrid wizard instructions
```

The setup skill references `config.example/config.yaml` as a schema template and uses Claude's domain knowledge for keyword generation. No external API calls needed for setup.

---

## Validate Skill (/validate)

### Checks performed

1. **Schema validation** — config.yaml parses as valid YAML and passes Pydantic schema
2. **Module existence** — every `scanner.module` path is importable
3. **Function existence** — every imported module has a `scan()` callable
4. **Template coverage** — each enabled scanner's signal type has matching templates in `config/templates/`
5. **Keyword sanity** — warns on empty keyword lists for enabled scanners
6. **Config completeness** — warns on missing optional fields (website, disqualifiers)

### Output

```
SignalForce Config Validation
=============================
  config.yaml schema      OK
  github scanner module   OK (scripts.scanners.github_scanner)
  arxiv scanner module    OK (scripts.scanners.arxiv_scanner)
  hf scanner              DISABLED (skipped)
  jobs scanner module     OK (scripts.scanners.job_scanner)
  funding scanner module  OK (scripts.scanners.funding_scanner)
  linkedin scanner module OK (scripts.scanners.linkedin_scanner)

  Template coverage:
    github  → email: OK, linkedin: OK
    arxiv   → email: OK, linkedin: OK
    jobs    → email: OK, linkedin: MISSING (warn)
    funding → email: OK, linkedin: OK

  Warnings:
    - jobs scanner: linkedin template missing (config/templates/linkedin-sequences/job-signal.md)
    - company.website is empty

  Result: VALID (2 warnings)
```

---

## First-Run Onboarding Guard

Every entry point checks for config at startup:

```python
# Added to scanner_runner.py, each scanner CLI, and skill-invoked scripts

def check_config_exists(config_dir: Path = Path("config")) -> None:
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
```

---

## Scanner Refactoring

### File moves

```
BEFORE                              AFTER
─────────────────────────────       ─────────────────────────────
scripts/github_rl_scanner.py   →   scripts/scanners/github_scanner.py
scripts/arxiv_monitor.py       →   scripts/scanners/arxiv_scanner.py
scripts/hf_model_monitor.py    →   scripts/scanners/hf_scanner.py
scripts/job_posting_scanner.py →   scripts/scanners/job_scanner.py
scripts/funding_tracker.py     →   scripts/scanners/funding_scanner.py
scripts/linkedin_activity.py   →   scripts/scanners/linkedin_scanner.py
(new)                          →   scripts/scanners/__init__.py
(new)                          →   scripts/scanners/base.py
```

### What changes in each scanner

1. **Remove** hardcoded keyword/topic/library constants (RL_TOPICS, RL_LIBRARIES, etc.)
2. **Add** `scan(config: ScannerConfig) -> ScanResult` as the entry point
3. **Read** keywords, topics, libraries, queries from `config` parameter
4. **Keep** all API interaction logic unchanged (GitHub API calls, ArXiv queries, etc.)
5. **Keep** CLI `__main__` block but have it load config first

Example transformation (github_scanner.py):

```python
# BEFORE
class GitHubRLScanner:
    RL_TOPICS = ["reinforcement-learning", "rl", "rlhf", "grpo"]
    RL_LIBRARIES = ["gymnasium", "stable-baselines3", ...]

    def scan(self, lookback_days: int) -> ScanResult:
        # uses self.RL_TOPICS, self.RL_LIBRARIES
        ...

# AFTER
from scripts.scanners.base import ScannerConfig, ScanResult, Signal, SignalStrength

def scan(config: ScannerConfig) -> ScanResult:
    topics = config.topics        # from config.yaml
    libraries = config.libraries  # from config.yaml
    # same GitHub API logic, reads from config instead of constants
    # scanner is responsible for validating its own output
    # (e.g., ensuring GitHub signals include repo_name in metadata)
    ...

if __name__ == "__main__":
    from scripts.config_loader import load_config
    cfg = load_config()
    result = scan(cfg.scanners["github"])
    ...
```

---

## Skills Updates

All 11 existing skills need these changes:

1. **Remove** hardcoded RL references from descriptions and workflows
2. **Reference** `config/gtm-context.md` instead of `.agents/gtm-context.md` for ICP context
3. **Reference** `config/templates/` instead of `templates/` for outreach copy
4. **Generalize** language (e.g., "RL maturity" → "domain maturity", "RL keywords" → "domain keywords")

The `.agents/gtm-context.md` file is replaced by `config/gtm-context.md`. Skills that reference it update their `@` path.

---

## n8n Workflow Updates

### daily-signal-scan.json
- Update scanner command paths: `scripts.github_rl_scanner` → `scripts.scanners.github_scanner`
- Scanner nodes should pass `--config config/config.yaml` flag
- Slack alert text: remove "RL" from message strings

### sequence-launcher.json
- Template routing reads from config instead of hardcoded signal type → template mapping
- LLM prompt references `config/gtm-context.md` for voice/positioning

### enrichment-pipeline.json
- Minimal changes (already generic)

### crm-sync.json
- Minimal changes (already generic)

---

## Documentation Updates

### README.md (rewrite)
- Lead with generic value prop: "Signal-based outbound sales engine — configure for any ICP"
- 30-second quickstart: clone → /setup → scan
- Use RL as a concrete example, not the product definition
- Link to examples/ for multiple verticals

### architecture.md (update)
- Replace "rl-gtm-engine" with "SignalForce" throughout
- Update data flow diagram with config loader
- Update scanner names and paths
- Remove RL-specific terminology from component descriptions
- Update External APIs table: clarify that Semantic Scholar is used by `arxiv_scanner.py` for paper-to-company affiliation mapping (not a separate scanner). API key handling stays in `config.py` (env vars), not in `config.yaml`.

### CLAUDE.md (update)
- Replace "rl-gtm-engine" with "SignalForce"
- Update directory structure section
- Add config/ and config.example/ descriptions
- Update commands section with new scanner paths

### Project rename
- All references to "rl-gtm-engine" → "SignalForce" across docs, skills, comments

---

## Example ICP Configs

Ship 3 additional examples alongside the RL reference:

### examples/rl-infrastructure/
Current RL config, moved from root. Full working example with all templates.

### examples/cybersecurity/
- Company: API security testing tools
- ICP: Enterprise DevSecOps teams, API-first SaaS companies
- Scanners: GitHub (security repos), ArXiv (security papers), Jobs (AppSec roles), Funding, LinkedIn. HuggingFace disabled.
- Keywords: OWASP, DAST, SAST, API security, zero-day, penetration testing

### examples/devtools/
- Company: Developer productivity platform
- ICP: Engineering leaders at mid-size SaaS, platform engineering teams
- Scanners: GitHub (devtools repos), Jobs (platform eng roles), Funding, LinkedIn. ArXiv and HuggingFace disabled.
- Keywords: developer experience, CI/CD, internal tooling, platform engineering

### examples/data-infra/
- Company: Data pipeline orchestration
- ICP: Data engineering teams, analytics-heavy organizations
- Scanners: GitHub (data pipeline repos), Jobs (data eng roles), Funding, LinkedIn. ArXiv enabled (data systems papers). HuggingFace disabled.
- Keywords: data pipeline, ETL, data lakehouse, streaming, Airflow, dbt

Each example includes: `config.yaml`, `gtm-context.md`, and 2-3 email templates (not full coverage — labeled as starting points).

---

## Testing Strategy

### New test files

- `tests/unit/test_config_loader.py` — valid config, missing file, bad YAML, bad schema, extra fields, empty keywords, missing optional fields, forward compatibility, relative vs absolute path handling
- `tests/unit/test_scanner_runner.py` — happy path, missing module, no scan() function, scanner raises, disabled scanner, empty keywords warning
- `tests/unit/test_first_run_guard.py` — config dir missing, config dir exists but yaml missing, config dir exists with yaml (happy path)
- `tests/fixtures/sample_config.yaml` — valid test fixture
- `tests/fixtures/bad_config.yaml` — invalid fixture for error testing

### Updated test files

All 6 scanner test files updated:
- Remove assertions on hardcoded keywords
- Test that scanners correctly read from ScannerConfig
- Mock API calls unchanged

`test_models.py`:
- Update for renamed/removed enums (no RLMaturityStage, no RL-specific SignalType values)
- Test that free-form string fields accept arbitrary values

`test_intent_scorer.py`:
- Test with weights loaded from config instead of hardcoded INTENT_WEIGHTS

### Test fixtures

```yaml
# tests/fixtures/sample_config.yaml
company:
  name: "Test Corp"
  product: "Test product"
  category: "Testing"

icp:
  tiers:
    - name: "Tier 1"
      description: "Primary buyers"
      signals: ["signal-1"]
  maturity_stages: ["EXPLORING", "BUILDING", "SCALING"]
  target_titles: ["Engineer", "Manager"]

scanners:
  github:
    enabled: true
    module: scripts.scanners.github_scanner
    topics: ["test-topic"]
    keywords: ["test-keyword"]
  arxiv:
    enabled: false
    module: scripts.scanners.arxiv_scanner

scoring:
  intent_weights:
    github: 2.5
    arxiv: 3.0
  half_lives_days:
    github: 5
    arxiv: 10
```

---

## Error Handling

```
CODEPATH                 | FAILURE                  | RESCUE                  | USER SEES
-------------------------|--------------------------|-------------------------|------------------
config_loader.load()     | config/ missing          | First-run guard         | Setup instructions
config_loader.load()     | Bad YAML syntax          | yaml.YAMLError caught   | Syntax error + line
config_loader.load()     | Schema validation fail   | ValidationError caught  | Which fields failed
scanner_runner.run_all() | Module not found          | ModuleNotFoundError     | Module path error
scanner_runner.run_all() | No scan() function       | AttributeError caught   | Module name error
scanner_runner.run_all() | Scanner runtime error    | Exception caught, skip  | Warning, continues
scanner (any)            | Empty keyword list       | Warning logged          | Warning message
/validate                | Any validation failure   | Reported in summary     | Check-by-check report
```

All errors produce actionable messages. No silent failures.

---

## Migration Path (existing RL users)

1. Pull latest code
2. Copy RL example: `cp -r examples/rl-infrastructure/ config/`
3. Delete stale file: `rm -rf .agents/gtm-context.md` (replaced by `config/gtm-context.md`)
4. Everything works exactly as before

The `.agents/` directory is deprecated. All skills that previously referenced `.agents/gtm-context.md` now reference `config/gtm-context.md`. The `.agents/` directory should be removed from the repo and added to `.gitignore` to prevent stale copies from causing confusion.

No breaking changes for users who follow this migration.

---

## Scope

### In scope
- Config schema + config loader + Pydantic validation
- Scanner interface convention + scanner runner
- Refactor 6 scanners to read from config
- Generalize models.py (remove RL-specific enums)
- Move RL content to examples/rl-infrastructure/
- Create config.example/ with RL defaults
- Setup skill (hybrid auto-generate wizard)
- Validate skill (config checker)
- 3 additional example ICP configs
- First-run onboarding guard
- README rewrite for generic positioning
- Project rename (rl-gtm-engine → SignalForce)
- Update all 11 skills to reference config/
- Update n8n workflows for new scanner paths
- Update architecture.md, CLAUDE.md
- Test updates for all changed code

### NOT in scope
- Template marketplace / community config sharing (requires hosting infrastructure)
- CLI wrapper for non-Claude-Code users (different product direction)
- Multi-ICP simultaneous scanning (YAGNI)
- pip-installable scanner plugins (plugin SDK, rejected approach)
- Web UI for config management

### Deferred (TODOS.md)
- Community config repository (P2, after this ships)
