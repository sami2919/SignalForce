# rl-gtm-engine Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an open-source collection of Claude Code agent skills, Python scripts, and n8n automation workflows for signal-based outbound sales targeting reinforcement learning infrastructure buyers.

**Architecture:** Skills-first design. Claude Code skills (SKILL.md files) are the primary user interface — they instruct Claude on how to perform GTM tasks. Python scripts are executable tools that skills invoke for API interactions. n8n workflows handle scheduled, autonomous automation. Templates provide reusable copy and scoring logic. Each layer has a single responsibility and clear interfaces between them.

**Tech Stack:** Python 3.11+ (scripts), Claude Code skills (SKILL.md), n8n (workflow orchestration), GitHub/Semantic Scholar/Hugging Face Hub APIs (signal sources), Apollo/Hunter/Prospeo APIs (enrichment), Instantly.ai (email sequencing), HubSpot (CRM), pytest (testing)

---

## How This Plan Is Structured

This plan has **8 phases** with **31 tasks**. Each task is a self-contained prompt designed to run in a **fresh context window**. Every prompt includes:

1. **Context** — what exists so far, what this task connects to
2. **Logic** — WHY we're doing this, not just what
3. **Exact files** to create or modify
4. **Skills/agents** to invoke during execution
5. **Verification** — how to confirm the task is done correctly
6. **Commit** — what to commit and the message format

**Execution order matters within each phase. Phases can overlap where noted.**

---

## Phase 0: Repository Foundation

**Why this phase exists:** Every subsequent task assumes a properly initialized repo with a CLAUDE.md, git history, and the correct directory structure. Without this foundation, subagents will waste time asking "where do files go?" and "what are the project conventions?"

---

### Task 0.1: Initialize Repository and Directory Structure

**Files:**
- Create: `README.md` (skeleton)
- Create: `CLAUDE.md`
- Create: `.gitignore`
- Create: `pyproject.toml`
- Create: `LICENSE`
- Create: all directories in the project tree

**Prompt:**
```
You are initializing a new open-source Python + Claude Code skills project called "rl-gtm-engine" in /Users/sami/SignalForce.

SKILLS TO USE: superpowers:test-driven-development (for pyproject.toml setup)

WHAT TO DO:

1. Initialize a git repository:
   git init
   git branch -M main

2. Create the full directory structure (create empty .gitkeep files in leaf directories):
   .agents/
   skills/signal-scanner/
   skills/prospect-researcher/
   skills/contact-finder/
   skills/email-writer/
   skills/pipeline-tracker/
   skills/deliverability-manager/
   skills/champion-tracker/
   skills/compliance-manager/
   n8n-workflows/
   templates/email-sequences/
   templates/scoring-rubrics/
   docs/
   scripts/
   tests/
   tests/unit/
   tests/integration/

3. Create .gitignore with:
   - Python: __pycache__/, *.pyc, .pytest_cache/, dist/, build/, *.egg-info/
   - Environment: .env, .env.local, .env.*.local
   - IDE: .vscode/, .idea/
   - OS: .DS_Store, Thumbs.db
   - n8n: Do NOT ignore n8n-workflows/*.json (those are tracked)
   - Virtual env: venv/, .venv/

4. Create pyproject.toml:
   - Project name: rl-gtm-engine
   - Version: 0.1.0
   - Python requires: >=3.11
   - Dependencies: requests, pydantic (for data models), python-dotenv
   - Dev dependencies: pytest, pytest-cov, pytest-asyncio, ruff
   - Ruff config: line-length 100, target python 3.11
   - Pytest config: testpaths = ["tests"], minimum coverage = 80%

5. Create LICENSE: MIT license, copyright 2026 Sami Rahman

6. Create a skeleton README.md with just:
   # rl-gtm-engine
   > A Signal-Based Outbound Engine for RL Infrastructure — Built with Claude Code Skills, n8n, and Clay

   **Status:** 🚧 Under Development

7. Commit everything:
   git add -A
   git commit -m "chore: initialize repository structure and project config"

VERIFICATION:
- Run: tree -I '__pycache__|.git' to confirm structure
- Run: python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['name'])" to verify pyproject.toml parses
- Confirm git log shows the initial commit
```

---

### Task 0.2: Create CLAUDE.md Project Configuration

**Files:**
- Create: `CLAUDE.md`

**Why this matters:** CLAUDE.md is the single most important file for agentic development. Every Claude Code session reads it first. It tells Claude what the project is, what conventions to follow, and how to behave. Without it, every subagent starts from zero context.

**Prompt:**
```
You are creating the CLAUDE.md file for the rl-gtm-engine project in /Users/sami/SignalForce.

This file is the project's "constitution" — every Claude Code session reads it before doing anything. It must be concise but complete.

WHAT TO DO:

Create CLAUDE.md at the project root with these sections:

## Project Overview
- rl-gtm-engine is an open-source collection of Claude Code agent skills and n8n workflows for signal-based outbound sales targeting RL infrastructure buyers
- Three layers: Skills (SKILL.md) → Python scripts → n8n workflows
- Skills are the primary interface; scripts are tools skills invoke; n8n handles scheduling

## Architecture
- skills/ — Claude Code SKILL.md files that instruct Claude how to perform GTM tasks
- scripts/ — Python modules that hit external APIs (GitHub, Semantic Scholar, HF Hub, etc.)
- n8n-workflows/ — JSON workflow definitions for scheduled automation
- templates/ — Reusable email copy and scoring rubrics
- .agents/ — Shared context files loaded by all skills
- tests/ — pytest test suite for all Python code

## Conventions
- Python: Use Pydantic models for all data structures. Type hints required. Ruff for formatting.
- Scripts: Every script must be importable as a module AND runnable as CLI (if __name__ == "__main__")
- Skills: Follow superpowers:writing-skills format. Each SKILL.md must have YAML frontmatter with name and description.
- Immutability: Never mutate data structures. Return new objects.
- Error handling: All API calls must handle rate limits, timeouts, and auth failures gracefully. Log errors with context.
- Environment variables: All API keys loaded via python-dotenv from .env. Never hardcode secrets.
- Testing: pytest with 80% minimum coverage. TDD workflow required.

## Commands
- Run tests: pytest --cov=scripts --cov-report=term-missing
- Format: ruff format .
- Lint: ruff check . --fix
- Run a script: python -m scripts.github_rl_scanner

## Dependencies
- See pyproject.toml for full list
- External APIs: GitHub API, Semantic Scholar API, Hugging Face Hub API, Apollo.io, Hunter.io, Prospeo, Instantly.ai, HubSpot

Commit:
git add CLAUDE.md
git commit -m "docs: add CLAUDE.md project configuration"

VERIFICATION:
- Read CLAUDE.md and confirm it covers all sections
- Confirm it's under 100 lines (concise enough to be useful)
```

---

### Task 0.3: Create GTM Context File

**Files:**
- Create: `.agents/gtm-context.md`

**Why this matters:** This file is the "brain" of the entire system. Every skill loads it to understand WHO we're selling to, WHAT we're selling, and HOW to talk about it. It's the single source of truth for ICP definitions, product positioning, voice/tone, and competitive intelligence. Without it, each skill would need to redundantly define these things.

**Logic:** The GTM context file follows the pattern from the extruct-ai/gtm-skills repo. It separates "what we know about the market" from "how we execute against it." Skills reference this file for context but contain their own execution logic. This means you can swap the GTM context for a different company/product and the skills still work — making the project truly reusable for the open-source community.

**Prompt:**
```
You are creating the GTM context file for rl-gtm-engine. This file is loaded by all skills to provide shared context about the target market, product, and ICP.

WHAT TO DO:

Create .agents/gtm-context.md with these sections:

## Company
- Collinear AI — Environment-as-a-Service for reinforcement learning
- Founded 2023, ~16 employees, Mountain View CA
- CEO: Nazneen Rajani (Stanford, ex-Hugging Face)
- Stage: Seed/Series A

## Product
- Creates production-grade RL environments from enterprise proprietary data
- Enterprises bring their workflows (Jira, ServiceNow, Shopify); Collinear builds configurable virtual worlds for agent training, evaluation, and data generation
- Key differentiator: Managed environments vs. building in-house (which is what most teams do today)
- Gymnasium-compatible API (drop-in replacement for teams already using Gymnasium)

## ICP Tiers (in priority order)

### Tier 1: AI Labs (Frontier Model Training)
- Companies: OpenAI, Anthropic, DeepMind, Mistral, Cohere, xAI, Meta AI
- Buyer signal: Active RLHF/GRPO/reward modeling work
- Decision makers: Head of Post-Training, RL Research Lead
- Why they buy: Need diverse, high-quality environments for RLHF at scale
- Deal size: $200K-$1M+ ARR

### Tier 2: Enterprise AI Agent Builders
- Companies building LLM-powered agents for enterprise workflows
- Buyer signal: Integrating LLMs with Jira/ServiceNow/Shopify/Salesforce
- Decision makers: VP Engineering, Head of AI/ML
- Why they buy: Need safe training environments that mirror real enterprise systems
- Deal size: $100K-$500K ARR

### Tier 3: Robotics & Autonomous Systems
- Companies using RL for policy learning in physical systems
- Buyer signal: Sim-to-real transfer work, custom Gymnasium environments
- Decision makers: Head of Simulation, Principal Robotics Engineer
- Why they buy: Need high-fidelity simulation environments
- Deal size: $100K-$300K ARR

### Tier 4: Industry-Specific RL Users
- Finance (trading), Energy (grid optimization), Gaming (NPC behavior), RecSys
- Buyer signal: Domain-specific RL publications or repos
- Decision makers: VP Engineering, Head of ML
- Why they buy: Need environments modeling their specific domain
- Deal size: $50K-$200K ARR

## Target Titles (priority order)
1. Head of ML / Director of ML / VP of Machine Learning
2. Head of AI / VP of AI
3. Principal ML Engineer / Staff ML Engineer
4. VP Engineering / CTO (at companies <100 employees)
5. RL-specific: RL Engineer, Simulation Engineer, Reward Modeling Lead

## Voice & Tone
- Technical peer, not sales rep
- Lead with problems, not features
- Reference specific technical work (their papers, repos, models)
- Maximum brevity — 4 sentences max in initial outreach
- Never use: "I hope this email finds you well", "I noticed your company", "touching base"
- Always use: specific signal references, technical terminology, low-friction CTAs

## Competitors
- Primary competitor: Building in-house (most teams DIY their environments)
- Idler — RL environment platform (early stage)
- Mechanize — AI agent training environments
- Applied Compute — compute for RL training
- Osmosis — environment generation

## Proof Points
- Kore.ai: 91% improvement in agent performance using Collinear environments
- ServiceNow: Collaboration on enterprise workflow simulation
- MasterClass: Partnership for content recommendation training

## Disqualification Criteria
- No RL activity (no repos, no papers, no hiring, no models)
- Already using a competing managed solution and locked in
- Company too small (<10 employees) or too early (pre-product)
- Budget holder explicitly said "building in-house and committed"

Commit:
git add .agents/gtm-context.md
git commit -m "docs: add GTM context file with ICP definitions and positioning"

VERIFICATION:
- Read the file and confirm all 4 ICP tiers are defined with specific criteria
- Confirm voice/tone section has concrete do/don't examples
- Confirm disqualification criteria are specific enough to actually filter accounts
```

---

## Phase 1: Data Models and Shared Infrastructure

**Why this phase exists:** Before writing any scripts or skills, we need to define the data structures that flow between components. A Signal detected by the scanner must have a consistent shape when it's passed to the researcher, then to the contact finder, then to the email writer. Pydantic models enforce this contract at runtime. Without them, each component invents its own format and integration becomes a nightmare.

**Logic:** We use Pydantic (not plain dicts or dataclasses) because:
1. Runtime validation — if an API returns unexpected data, we get a clear error instead of a silent bug
2. Serialization — `.model_dump_json()` gives us JSON for n8n workflows, `.model_dump()` for Python
3. Documentation — the model IS the documentation of what data looks like
4. Immutability — Pydantic models are immutable by default (frozen=True), aligning with our coding standards

---

### Task 1.1: Define Core Data Models

**Files:**
- Create: `scripts/__init__.py`
- Create: `scripts/models.py`
- Create: `tests/__init__.py`
- Create: `tests/unit/__init__.py`
- Create: `tests/unit/test_models.py`

**Prompt:**
```
You are creating the shared data models for rl-gtm-engine. These Pydantic models define the shape of data flowing between all components: scanners → researcher → contact finder → email writer → pipeline tracker.

SKILLS TO USE:
- superpowers:test-driven-development — Write tests FIRST, then implement models

CONTEXT:
- This is a GTM (go-to-market) automation tool for selling RL infrastructure
- Read .agents/gtm-context.md for ICP tier definitions and signal types
- Read CLAUDE.md for project conventions

WHAT TO BUILD:

Define these Pydantic models in scripts/models.py:

1. SignalType (str enum):
   GITHUB_RL_REPO, ARXIV_PAPER, JOB_POSTING, HUGGINGFACE_MODEL, FUNDING_EVENT

2. SignalStrength (int enum):
   WEAK = 1, MODERATE = 2, STRONG = 3

3. Signal (BaseModel, frozen=True):
   - id: str (UUID, auto-generated)
   - signal_type: SignalType
   - company_name: str
   - company_domain: str | None
   - signal_strength: SignalStrength
   - source_url: str
   - raw_data: dict (the API response payload — kept for debugging)
   - detected_at: datetime (defaults to now)
   - metadata: dict = {} (flexible additional data per signal type)

   Logic: Each signal represents ONE detected buying indicator from ONE source.
   The raw_data preserves the original API response so we can debug scoring logic.
   metadata holds signal-type-specific fields (e.g., paper_title for ArXiv, repo_stars for GitHub).

4. ICPTier (str enum):
   TIER_1_AI_LAB, TIER_2_AGENT_BUILDER, TIER_3_ROBOTICS, TIER_4_INDUSTRY

5. ICPScore (str enum):
   A, B, C, D

6. RLMaturityStage (str enum):
   EXPLORING, BUILDING, SCALING, PRODUCTIONIZING

   Logic: These four stages represent increasing RL investment. A company EXPLORING
   mentions RL in blog posts; a company PRODUCTIONIZING has RL in production and
   publishes research. Different stages get different messaging.

7. CompanyProfile (BaseModel, frozen=True):
   - company_name: str
   - domain: str
   - icp_tier: ICPTier | None
   - icp_score: ICPScore | None
   - rl_maturity: RLMaturityStage | None
   - employee_count: int | None
   - funding_stage: str | None
   - founded_year: int | None
   - hq_location: str | None
   - tech_stack: list[str] = []
   - signals: list[Signal] = []
   - composite_signal_score: float = 0.0
   - researched_at: datetime | None
   - notes: str = ""

8. ContactTitle (str enum):
   HEAD_OF_ML, VP_AI, PRINCIPAL_ML_ENGINEER, VP_ENGINEERING, CTO, RL_ENGINEER, OTHER

9. EnrichmentSource (str enum):
   APOLLO, HUNTER, PROSPEO, PEOPLE_DATA_LABS, MANUAL

10. Contact (BaseModel, frozen=True):
    - id: str (UUID, auto-generated)
    - full_name: str
    - title: str
    - title_category: ContactTitle
    - email: str | None
    - email_verified: bool = False
    - email_verification_source: str | None
    - linkedin_url: str | None
    - enrichment_source: EnrichmentSource | None
    - company_domain: str
    - confidence_score: float = 0.0 (0.0 to 1.0)
    - found_at: datetime | None

11. EmailVariant (str enum):
    PROBLEM_FOCUSED, OUTCOME_FOCUSED, SOCIAL_PROOF_FOCUSED

12. GeneratedEmail (BaseModel, frozen=True):
    - id: str (UUID, auto-generated)
    - contact_id: str
    - signal_type: SignalType
    - signal_reference: str (the specific paper title, repo name, job URL, etc.)
    - subject_line: str
    - body: str
    - cta: str
    - variant: EmailVariant
    - template_name: str
    - generated_at: datetime

13. DealStage (str enum):
    SIGNAL_DETECTED, RESEARCHED, ENRICHED, SEQUENCED, ENGAGED, RESPONDED, MEETING_SCHEDULED, DISQUALIFIED

14. Deal (BaseModel, frozen=True):
    - id: str (UUID, auto-generated)
    - company_profile: CompanyProfile
    - contacts: list[Contact] = []
    - emails_sent: list[GeneratedEmail] = []
    - stage: DealStage = DealStage.SIGNAL_DETECTED
    - hubspot_deal_id: str | None
    - instantly_campaign_id: str | None
    - created_at: datetime
    - updated_at: datetime
    - notes: str = ""

15. ScanResult (BaseModel, frozen=True):
    - scan_id: str (UUID)
    - scan_type: SignalType
    - started_at: datetime
    - completed_at: datetime
    - signals_found: list[Signal]
    - total_raw_results: int (before filtering)
    - total_after_dedup: int (after dedup)
    - errors: list[str] = []

TDD APPROACH:
Write tests/unit/test_models.py FIRST with tests for:
- Creating each model with valid data
- Validating that frozen=True prevents mutation (raises error)
- Enum values are correct
- Default values work (auto-generated UUIDs, default datetimes)
- Optional fields accept None
- Invalid data raises ValidationError (e.g., negative employee_count, confidence_score > 1.0)
- Serialization round-trip: model → JSON → model produces identical result

Then implement the models to make all tests pass.

IMPORTANT CONSTRAINTS:
- Add a validator on Contact.confidence_score: must be between 0.0 and 1.0
- Add a validator on Signal: if signal_type is GITHUB_RL_REPO, metadata must contain "repo_name"
- All models use frozen=True (immutability)
- Use uuid4() for auto-generating IDs (as default_factory)
- Use datetime.now(UTC) for timestamps

Commit:
git add scripts/ tests/
git commit -m "feat: add core Pydantic data models for GTM pipeline"

VERIFICATION:
- Run: pytest tests/unit/test_models.py -v
- All tests pass
- Run: pytest --cov=scripts --cov-report=term-missing
- Coverage on scripts/models.py should be >90%
```

---

### Task 1.2: Create API Client Base Class and Configuration

**Files:**
- Create: `scripts/config.py`
- Create: `scripts/api_client.py`
- Create: `tests/unit/test_config.py`
- Create: `tests/unit/test_api_client.py`

**Why this matters:** Every scanner script hits a different API, but they all share common concerns: authentication, rate limiting, retries, timeout handling, and error logging. Instead of duplicating this logic in every script, we build a base API client that handles all of it. Each scanner then subclasses it and only implements the API-specific logic.

**Logic behind the design:**
- `config.py` centralizes all environment variable loading. It validates at import time that required keys are present, so we fail fast with a clear error instead of discovering a missing API key 30 minutes into a scan.
- `api_client.py` provides a `BaseAPIClient` with retry logic using exponential backoff. GitHub's API returns 403 with a `Retry-After` header when rate limited; Semantic Scholar returns 429. Our base client handles both patterns.
- We use `requests` for now (simple, well-known). We can migrate to `httpx` later if we need async for parallel scanning.

**Prompt:**
```
You are creating the configuration and base API client for rl-gtm-engine.

SKILLS TO USE:
- superpowers:test-driven-development — Write tests FIRST
- security-review — Verify no secrets are hardcoded

CONTEXT:
- Read CLAUDE.md for project conventions
- Read scripts/models.py for data model definitions
- All API keys come from .env file via python-dotenv
- This project hits: GitHub API, Semantic Scholar API, Hugging Face Hub API, Apollo, Hunter, Prospeo, Instantly.ai, HubSpot

WHAT TO BUILD:

### scripts/config.py

Create a configuration module that:

1. Loads .env file using python-dotenv
2. Defines a frozen Pydantic Settings model (BaseSettings) called AppConfig with:
   - github_token: str | None = None
   - semantic_scholar_key: str | None = None
   - apollo_api_key: str | None = None
   - hunter_api_key: str | None = None
   - prospeo_api_key: str | None = None
   - instantly_api_key: str | None = None
   - hubspot_api_key: str | None = None
   - openai_api_key: str | None = None
   - clay_api_key: str | None = None
   - zerobounce_api_key: str | None = None
   - scan_lookback_days: int = 7 (how far back to look for signals)
   - min_signal_strength: int = 1 (minimum score to keep a signal)
   - log_level: str = "INFO"

3. A function get_config() that returns a singleton AppConfig instance
4. A function validate_keys_for_scanner(scanner_name: str) that checks if the required keys for a specific scanner are present and raises ValueError with a helpful message if not. Map:
   - "github": requires github_token
   - "arxiv": requires semantic_scholar_key (optional, works without but rate limited)
   - "huggingface": no key required (public API)
   - "enrichment": requires at least one of apollo, hunter, or prospeo

Logic: We make all keys optional because not every user will have every API key.
The validate_keys_for_scanner function is called at the START of each scanner so
users get a clear error immediately rather than discovering missing keys mid-scan.

### scripts/api_client.py

Create a base API client class:

1. BaseAPIClient:
   - __init__(self, base_url: str, auth_header: dict | None, timeout: int = 30)
   - _request(self, method: str, endpoint: str, params: dict, data: dict) -> dict
     - Handles: rate limiting (429/403), retries with exponential backoff (max 3), timeouts
     - Logs: request URL, response status, retry attempts
     - Returns: parsed JSON response
     - Raises: APIError (custom exception) on non-retryable failures
   - get(self, endpoint, params) -> dict
   - post(self, endpoint, data) -> dict

2. APIError(Exception):
   - status_code: int
   - message: str
   - url: str

3. RateLimitError(APIError):
   - retry_after: int | None

Logic for retry strategy:
- On 429 (Too Many Requests): Check Retry-After header, sleep that long, retry
- On 403 (GitHub rate limit): Check X-RateLimit-Reset header, calculate wait time
- On 500/502/503 (server errors): Exponential backoff (1s, 2s, 4s), max 3 retries
- On 400/401/404: Do NOT retry (client error, won't succeed on retry)
- On timeout: Retry once with doubled timeout

Use the `requests` library (already in dependencies). We can add httpx/async later.

Create a .env.example file at project root with all the env var names (no values)
as documentation for users.

TDD APPROACH:
Write tests FIRST using unittest.mock to mock HTTP responses:
- Test successful request returns parsed JSON
- Test 429 triggers retry with correct backoff
- Test 403 with Retry-After header respects the header value
- Test 500 retries with exponential backoff
- Test 400 raises APIError immediately (no retry)
- Test max retries exceeded raises APIError
- Test timeout triggers one retry
- Test config loads from environment variables
- Test validate_keys_for_scanner raises for missing keys
- Test validate_keys_for_scanner passes when keys present

Commit:
git add scripts/config.py scripts/api_client.py tests/unit/test_config.py tests/unit/test_api_client.py .env.example
git commit -m "feat: add configuration management and base API client with retry logic"

VERIFICATION:
- Run: pytest tests/unit/test_config.py tests/unit/test_api_client.py -v
- All tests pass
- Run: ruff check scripts/config.py scripts/api_client.py
- No lint errors
- Confirm .env.example exists with all variable names
```

---

## Phase 2: Signal Scanner Scripts

**Why this phase exists:** The scanner scripts are the "eyes" of the system. They query external APIs to detect companies actively investing in RL. These scripts must work both as importable Python modules (so skills can call them) AND as standalone CLI tools (so n8n can execute them). Each scanner returns a list of `Signal` objects from the models we defined in Phase 1.

**Logic behind the scanner design:**
- Each scanner focuses on ONE signal source. This is the Unix philosophy: do one thing well. It also means scanners can be developed and tested independently.
- All scanners share the same interface: `scan() -> ScanResult`. This makes it trivial to add new signal sources later.
- Raw API responses are preserved in `Signal.raw_data` so we can debug scoring logic without re-querying APIs.
- Deduplication happens within each scanner (same company from same source) and again when signals are stacked across sources (in the signal-stacking logic later).

---

### Task 2.1: Build GitHub RL Repository Scanner

**Files:**
- Create: `scripts/github_rl_scanner.py`
- Create: `tests/unit/test_github_rl_scanner.py`
- Create: `tests/fixtures/github_responses.json`

**Why this scanner matters:** GitHub is the highest-fidelity signal source. If a company's engineers are actively pushing code to RL repositories, that company is building RL capabilities RIGHT NOW. This isn't "they mentioned AI on their website" — this is actual engineering investment, visible through commit history.

**Logic for what we query:**
- We search for repositories using GitHub's search API with queries like `topic:reinforcement-learning` and library-specific queries (`gymnasium`, `stable-baselines3`, `rllib`, `torchrl`, `cleanrl`, `tianshou` in requirements or imports).
- We filter for ORGANIZATIONAL accounts only. A personal hobby project (`johndoe/rl-experiments`) is not a buying signal — we need `company-org/rl-project`.
- We check commit recency: repos with no commits in 90 days are stale (the team may have abandoned RL).
- We capture metadata: repo count per org, total stars, contributor count, primary languages. More repos + more contributors = higher signal strength.

**Signal strength scoring logic:**
- 1 RL repo with recent activity → WEAK (score 1). Could be an experiment.
- 2-3 RL repos OR 1 repo with 5+ contributors → MODERATE (score 2). Dedicated effort.
- 4+ RL repos OR dedicated RL team (10+ contributors across repos) → STRONG (score 3). Major investment.

**Prompt:**
```
You are building the GitHub RL Repository Scanner for rl-gtm-engine.

SKILLS TO USE:
- superpowers:test-driven-development — Write ALL tests first, then implement
- coding-standards — Follow project conventions

CONTEXT:
- Read CLAUDE.md for project conventions
- Read scripts/models.py — you'll return Signal and ScanResult objects
- Read scripts/api_client.py — subclass BaseAPIClient for GitHub
- Read scripts/config.py — use get_config() for the GitHub token
- Read .agents/gtm-context.md — understand what RL libraries and signals matter

WHAT TO BUILD:

### scripts/github_rl_scanner.py

1. GitHubClient(BaseAPIClient):
   - Subclass with base_url="https://api.github.com"
   - Auth: token-based (Authorization: Bearer {token})
   - search_repos(query: str, sort: str = "updated") -> list[dict]
   - get_org_info(org_name: str) -> dict
   - get_repo_contributors_count(owner: str, repo: str) -> int

2. GitHubRLScanner:
   - __init__(self, config: AppConfig)
   - RL_TOPICS: list of topics to search: ["reinforcement-learning", "rl", "rlhf", "grpo"]
   - RL_LIBRARIES: list of libraries that indicate RL usage:
     ["gymnasium", "stable-baselines3", "sb3", "rllib", "ray[rllib]",
      "torchrl", "cleanrl", "tianshou", "d4rl", "minigrid", "pettingzoo"]

   - scan(self, lookback_days: int = 7) -> ScanResult:
     Main entry point. Orchestrates the full scan:
     a. Build search queries for each RL topic and library
     b. Query GitHub search API for repos updated in last lookback_days
     c. Filter: only keep repos owned by organizations (not personal accounts)
     d. Group results by organization
     e. For each org: count repos, sum stars, estimate contributors
     f. Score signal strength per org using the scoring logic above
     g. Deduplicate: if same org found via multiple queries, keep highest score
     h. Create Signal objects for each qualifying org
     i. Return ScanResult with all signals and scan metadata

   - _build_search_queries(self, lookback_days: int) -> list[str]:
     Build GitHub search query strings. Example:
     "topic:reinforcement-learning pushed:>2026-03-10 fork:false"
     "gymnasium in:file filename:requirements.txt pushed:>2026-03-10"

   - _is_organization(self, owner: dict) -> bool:
     Check if repo owner is an org (owner.type == "Organization")

   - _score_org(self, repos: list[dict], contributor_count: int) -> SignalStrength:
     Apply the scoring logic:
     - 1 repo, <5 contributors → WEAK
     - 2-3 repos OR 1 repo with 5+ contributors → MODERATE
     - 4+ repos OR 10+ contributors → STRONG

   - _create_signal(self, org_name: str, repos: list[dict], score: SignalStrength) -> Signal:
     Create a Signal object with:
     - signal_type = GITHUB_RL_REPO
     - company_name = org display name or login
     - source_url = org GitHub URL
     - metadata = {repo_names, repo_count, total_stars, primary_languages, top_repo_url}
     - raw_data = first repo's full API response (for debugging)

3. CLI interface (if __name__ == "__main__"):
   - Parse args: --lookback-days (default 7), --output (json file path), --min-strength (1/2/3)
   - Run scan
   - Print summary: "Found N signals from M organizations"
   - If --output: write ScanResult as JSON

### tests/fixtures/github_responses.json

Create realistic mock API responses for testing:
- A search result with 3 repos from "deepmind" org (RL topic)
- A search result with 1 repo from "some-startup" org (gymnasium in requirements)
- A search result with a personal account repo (should be filtered out)
- An org info response
- A rate limit error response (403 with headers)

### tests/unit/test_github_rl_scanner.py

Write tests FIRST:
- test_scan_returns_scan_result: Mock API, verify ScanResult shape
- test_filters_personal_repos: Only org repos pass through
- test_deduplicates_same_org: Org found via 2 queries → 1 signal
- test_scoring_weak: 1 repo, 2 contributors → WEAK
- test_scoring_moderate: 3 repos → MODERATE
- test_scoring_strong: 5 repos, 15 contributors → STRONG
- test_search_query_format: Verify date formatting in queries
- test_handles_rate_limit: 403 response triggers retry (via BaseAPIClient)
- test_handles_empty_results: No repos → empty signals list
- test_metadata_contains_repo_names: Signal metadata has expected fields
- test_cli_output: Mock scan, verify JSON output file

IMPORTANT:
- Use unittest.mock.patch to mock all HTTP calls
- Load test fixtures from tests/fixtures/github_responses.json
- Never make real API calls in tests

Commit:
git add scripts/github_rl_scanner.py tests/unit/test_github_rl_scanner.py tests/fixtures/
git commit -m "feat: add GitHub RL repository scanner with org detection and signal scoring"

VERIFICATION:
- Run: pytest tests/unit/test_github_rl_scanner.py -v
- All tests pass
- Run: pytest --cov=scripts/github_rl_scanner --cov-report=term-missing
- Coverage >80%
- Run: python -m scripts.github_rl_scanner --help (confirm CLI works)
```

---

### Task 2.2: Build ArXiv Research Paper Tracker

**Files:**
- Create: `scripts/arxiv_monitor.py`
- Create: `tests/unit/test_arxiv_monitor.py`
- Create: `tests/fixtures/semantic_scholar_responses.json`

**Why this scanner matters:** Academic publications are a leading indicator of RL investment. When a company's researchers publish an RL paper, the company has dedicated research resources to RL methods. The paper itself tells us exactly what they're working on, giving us a hyper-specific outreach angle ("I read your paper on reward shaping for multi-agent environments...").

**Logic for the approach:**
- We use the Semantic Scholar API (not ArXiv directly) because Semantic Scholar has better author-to-affiliation mapping. ArXiv doesn't reliably link authors to companies.
- Search queries target RL-specific terms: "reinforcement learning", "RLHF", "GRPO", "reward modeling", "RL environments", "policy optimization", "PPO", "DPO".
- For each paper, we extract author affiliations and map them to company names. This is imperfect — affiliations are free-text ("Google DeepMind", "DeepMind, a Google company", "Google Brain" are all Google) — so we need a normalization step.
- Signal strength is based on paper count per company in the lookback window: 1 paper = WEAK, 2-3 papers = MODERATE, 4+ papers = STRONG.

**Prompt:**
```
You are building the ArXiv Research Paper Tracker for rl-gtm-engine.

SKILLS TO USE:
- superpowers:test-driven-development — Write ALL tests first
- coding-standards — Follow project conventions

CONTEXT:
- Read CLAUDE.md for conventions
- Read scripts/models.py for Signal and ScanResult models
- Read scripts/api_client.py — subclass BaseAPIClient for Semantic Scholar
- Read scripts/config.py — Semantic Scholar key is optional (works without, but rate limited)
- Read scripts/github_rl_scanner.py — follow the same patterns (scan() → ScanResult)

WHAT TO BUILD:

### scripts/arxiv_monitor.py

1. SemanticScholarClient(BaseAPIClient):
   - base_url = "https://api.semanticscholar.org/graph/v1"
   - Auth: api key header if available, otherwise no auth (lower rate limit)
   - search_papers(query: str, year: str, limit: int = 100, fields: list[str]) -> list[dict]
   - get_paper_details(paper_id: str, fields: list[str]) -> dict

2. ArxivRLMonitor:
   - RL_SEARCH_QUERIES: list of search terms:
     ["reinforcement learning", "RLHF", "reinforcement learning from human feedback",
      "GRPO", "group relative policy optimization", "reward modeling",
      "RL environments", "policy optimization PPO", "direct preference optimization DPO",
      "multi-agent reinforcement learning", "offline reinforcement learning",
      "sim-to-real transfer"]

   - scan(self, lookback_days: int = 7) -> ScanResult:
     a. For each search query, hit Semantic Scholar paper search
     b. Filter papers published within lookback_days
     c. Extract author affiliations from each paper
     d. Normalize company names (see _normalize_affiliation)
     e. Group papers by company
     f. Score: 1 paper = WEAK, 2-3 = MODERATE, 4+ = STRONG
     g. Create Signal objects with metadata including paper titles and authors
     h. Deduplicate across queries (same company)
     i. Return ScanResult

   - _normalize_affiliation(self, affiliation: str) -> str | None:
     Normalize messy affiliation strings to company names:
     - "Google DeepMind" → "Google"
     - "Meta AI Research" → "Meta"
     - "Microsoft Research" → "Microsoft"
     - "University of X" → None (filter out pure academia)
     - "Stanford University" → None

     Logic: We maintain a mapping dict for known companies. For unknown affiliations,
     we strip common suffixes ("Inc", "Ltd", "Corp", "Research", "AI Lab") and return
     the cleaned name. University affiliations return None (we only want companies).

     This is intentionally imperfect — some affiliations won't normalize correctly.
     That's OK; we'd rather miss a few than include false positives.

   - _create_signal(self, company: str, papers: list[dict], score: SignalStrength) -> Signal:
     metadata includes:
     - paper_titles: list of titles
     - paper_ids: list of Semantic Scholar IDs
     - author_names: list of authors affiliated with this company
     - research_areas: extracted from paper abstracts (simple keyword matching)

3. CLI interface:
   - --lookback-days, --output, --min-strength
   - Print: "Found N companies publishing RL research"

### Tests (write FIRST):
- test_scan_returns_scan_result
- test_filters_university_affiliations: Papers from "MIT" are excluded
- test_normalizes_known_companies: "Google DeepMind" → "Google"
- test_scoring_by_paper_count
- test_deduplicates_across_queries
- test_handles_missing_affiliations: Papers with no affiliation → skipped
- test_metadata_contains_paper_titles
- test_works_without_api_key: Falls back to unauthenticated

Commit:
git add scripts/arxiv_monitor.py tests/unit/test_arxiv_monitor.py tests/fixtures/semantic_scholar_responses.json
git commit -m "feat: add ArXiv RL paper tracker with affiliation extraction and normalization"

VERIFICATION:
- Run: pytest tests/unit/test_arxiv_monitor.py -v
- All tests pass, coverage >80%
```

---

### Task 2.3: Build Hugging Face Model Upload Monitor

**Files:**
- Create: `scripts/hf_model_monitor.py`
- Create: `tests/unit/test_hf_model_monitor.py`
- Create: `tests/fixtures/huggingface_responses.json`

**Why this scanner matters:** Hugging Face Hub uploads are the most specific signal. When an organization uploads a model trained with PPO, DPO, or GRPO, they're not just researching RL — they're actively using RL for model post-training. This is Collinear's core ICP: organizations that need environments for RL-based training.

**Logic:**
- Hugging Face Hub API is public (no auth required), making this the easiest scanner to build.
- We search for recently uploaded models and filter by training method tags (PPO, DPO, GRPO, RLHF).
- We also check model cards for RL-related keywords in the training description.
- We only keep models from organizations (not personal accounts like `user123/my-ppo-test`).

**Prompt:**
```
You are building the Hugging Face Model Upload Monitor for rl-gtm-engine.

SKILLS TO USE:
- superpowers:test-driven-development — Write ALL tests first
- coding-standards — Follow project conventions

CONTEXT:
- Read CLAUDE.md, scripts/models.py, scripts/api_client.py
- Read the previous scanner (scripts/github_rl_scanner.py) for patterns to follow
- Hugging Face Hub API docs: https://huggingface.co/docs/hub/api

WHAT TO BUILD:

### scripts/hf_model_monitor.py

1. HuggingFaceClient(BaseAPIClient):
   - base_url = "https://huggingface.co/api"
   - No auth required (public API)
   - list_models(search: str, sort: str = "lastModified", direction: int = -1, limit: int = 100) -> list[dict]
   - get_model_info(model_id: str) -> dict

2. HuggingFaceRLMonitor:
   - RL_TRAINING_TAGS: ["ppo", "dpo", "grpo", "rlhf", "reinforcement-learning", "reward-model", "orpo", "kto"]
   - RL_KEYWORDS_IN_CARD: ["reinforcement learning", "RLHF", "reward model", "PPO training", "DPO training", "GRPO"]

   - scan(self, lookback_days: int = 7) -> ScanResult:
     a. Search HF Hub for models with RL training tags
     b. Filter by lastModified within lookback_days
     c. Filter: only organization accounts (check if model_id contains org prefix like "meta-llama/")
     d. Group by organization
     e. Score: 1 model = WEAK, 2-3 = MODERATE, 4+ = STRONG
     f. Create signals with metadata: model names, training methods, model sizes
     g. Return ScanResult

   - _is_org_model(self, model_id: str) -> bool:
     Heuristic: org models have a namespace prefix that looks like a company name,
     not a personal username. Check against known org patterns.

   - _extract_training_method(self, model_info: dict) -> str | None:
     Look at tags, model card, and config for RL training method indicators.

3. CLI interface: same pattern as other scanners

### Tests (write FIRST):
- test_scan_finds_rl_models
- test_filters_personal_models
- test_scoring_by_model_count
- test_extracts_training_method_from_tags
- test_handles_no_results
- test_deduplicates_same_org
- test_metadata_includes_model_names

Commit:
git add scripts/hf_model_monitor.py tests/unit/test_hf_model_monitor.py tests/fixtures/huggingface_responses.json
git commit -m "feat: add Hugging Face model upload monitor for RL training detection"

VERIFICATION:
- pytest tests/unit/test_hf_model_monitor.py -v — all pass, >80% coverage
```

---

### Task 2.4: Build Signal Stacking and Composite Scoring Engine

**Files:**
- Create: `scripts/signal_stacker.py`
- Create: `tests/unit/test_signal_stacker.py`

**Why this matters:** Individual signals are good. Stacked signals are gold. A company that appears across multiple signal sources simultaneously (GitHub repos + ArXiv papers + hiring) is far more likely to be a real buyer than a company with a single weak signal. The stacking engine is what turns raw signals into prioritized, actionable accounts.

**Logic for composite scoring:**
- Each signal has a strength score (1-3).
- When signals stack (same company across multiple sources), the composite score increases multiplicatively, not additively. Two MODERATE signals (2+2=4 additive) become 2×2=4 but three MODERATE signals become 2×2×2=8. This rewards breadth of signal coverage.
- Actually, we'll use a weighted sum with a multiplier bonus for stacking:
  - Base: sum of all signal strengths
  - Multiplier: 1.0 for 1 signal, 1.5 for 2 signals, 2.0 for 3 signals, 3.0 for 4+ signals
  - Composite = base × multiplier
- Companies are tiered: A (composite ≥ 9), B (composite ≥ 5), C (composite ≥ 2), D (composite < 2)

**Company name matching challenge:**
- "DeepMind" from GitHub, "Google DeepMind" from ArXiv, "Google" from a job posting — are these the same company?
- We use domain-based matching as primary (if available) and fuzzy name matching as fallback.
- The `_match_company` function uses a simple approach: lowercase, strip common suffixes, check if one name is a substring of the other. This catches "DeepMind" matching "Google DeepMind" but won't catch completely different names.

**Prompt:**
```
You are building the Signal Stacking and Composite Scoring Engine for rl-gtm-engine.

SKILLS TO USE:
- superpowers:test-driven-development — Write ALL tests first
- coding-standards — Follow project conventions

CONTEXT:
- Read scripts/models.py — you work with Signal, ScanResult, ICPScore objects
- Read all five scanners to understand what signals look like (github_rl_scanner.py, arxiv_monitor.py, hf_model_monitor.py, job_posting_scanner.py, funding_tracker.py)
- Read .agents/gtm-context.md — understand ICP tier definitions

WHAT TO BUILD:

### scripts/signal_stacker.py

1. SignalStacker:
   - __init__(self, known_domains: dict[str, str] | None = None)
     Optional mapping of company_name → domain for better matching.
     E.g., {"deepmind": "deepmind.com", "google deepmind": "deepmind.com"}

   - stack_signals(self, scan_results: list[ScanResult]) -> list[CompanyProfile]:
     Main entry point:
     a. Flatten all signals from all ScanResults into one list
     b. Group signals by company (using _match_company for fuzzy matching)
     c. For each company group:
        - Calculate composite score using the multiplier formula
        - Determine ICP score (A/B/C/D) from composite
        - Create a CompanyProfile with all grouped signals attached
     d. Sort by composite score descending
     e. Return list of CompanyProfiles

   - _match_company(self, signal1: Signal, signal2: Signal) -> bool:
     Determine if two signals refer to the same company:
     Priority 1: If both have company_domain and domains match → True
     Priority 2: Normalize names (lowercase, strip suffixes) and check:
       - Exact match after normalization
       - One is a substring of the other (catches "DeepMind" ⊂ "Google DeepMind")
       - Levenshtein distance < 3 for short names (catches typos)
     Return False if no match.

   - _calculate_composite_score(self, signals: list[Signal]) -> float:
     base = sum(signal.signal_strength.value for signal in signals)
     source_types = len(set(s.signal_type for s in signals))  # unique signal sources
     multiplier = {1: 1.0, 2: 1.5, 3: 2.0}.get(source_types, 3.0)  # 4+ = 3.0
     return base * multiplier

   - _determine_icp_score(self, composite: float) -> ICPScore:
     if composite >= 9: return ICPScore.A
     if composite >= 5: return ICPScore.B
     if composite >= 2: return ICPScore.C
     return ICPScore.D

   - _group_signals_by_company(self, signals: list[Signal]) -> dict[str, list[Signal]]:
     Group using _match_company. Use the first-seen company name as the canonical name.
     If domain is available on any signal, use it as the grouping key instead of name.

2. Standalone function:
   stack_from_files(file_paths: list[str]) -> list[CompanyProfile]:
   Load ScanResult JSON files, run stacking, return results.
   This is for CLI and n8n usage.

3. CLI interface:
   python -m scripts.signal_stacker --inputs scan1.json scan2.json scan3.json --output stacked.json
   Reads scan result files, stacks signals, outputs ranked company list.

### Tests (write FIRST):
- test_single_signal_no_multiplier: 1 signal → composite = strength × 1.0
- test_two_sources_multiplier: 2 different source types → ×1.5
- test_three_sources_multiplier: 3 sources → ×2.0
- test_four_sources_multiplier: 4+ sources → ×3.0
- test_same_source_no_multiplier_bonus: 2 GitHub signals = 2 sources? No, same source type = ×1.0
- test_icp_score_a: composite ≥ 9 → A
- test_icp_score_b: composite 5-8 → B
- test_icp_score_c: composite 2-4 → C
- test_icp_score_d: composite < 2 → D
- test_matches_by_domain: Same domain, different name → grouped
- test_matches_by_name_substring: "DeepMind" and "Google DeepMind" → grouped
- test_no_match_different_companies: "OpenAI" and "Anthropic" → separate
- test_output_sorted_by_score: Highest score first
- test_deduplication_preserves_all_signals: Grouped company has all original signals

Commit:
git add scripts/signal_stacker.py tests/unit/test_signal_stacker.py
git commit -m "feat: add signal stacking engine with composite scoring and company matching"

VERIFICATION:
- pytest tests/unit/test_signal_stacker.py -v — all pass
- Coverage >80%
```

---

### Task 2.5: Build Job Posting Signal Scanner

**Files:**
- Create: `scripts/job_posting_scanner.py`
- Create: `tests/unit/test_job_posting_scanner.py`
- Create: `tests/fixtures/job_posting_responses.json`

**Why this scanner matters:** Job postings are a direct intent signal. When a company posts an "RL Engineer" or "Simulation Engineer" role, they're actively building an RL team. This is the most time-sensitive signal — the hiring process is a window of opportunity where the company is actively investing in new capabilities and open to tools that accelerate their new hires.

**Logic for the approach:**
- We don't scrape job boards directly (legal and technical issues). Instead, we use available APIs and structured sources.
- Primary approach: Use Google Custom Search API (or SerpAPI) to search for RL-related job postings across major job boards (LinkedIn, Lever, Greenhouse, Ashby).
- Search queries target specific titles and keywords: "reinforcement learning engineer", "RL researcher", "simulation engineer", "RLHF", "reward modeling", combined with site filters for job board domains.
- We extract: company name, job title, posting URL, posting date, required skills (to gauge RL maturity).
- Signal strength: 1 RL role = WEAK, 2-3 roles = MODERATE, 4+ roles (building a team) = STRONG.

**Prompt:**
```
You are building the Job Posting Signal Scanner for rl-gtm-engine.

SKILLS TO USE:
- superpowers:test-driven-development — Write ALL tests first
- coding-standards — Follow project conventions

CONTEXT:
- Read CLAUDE.md, scripts/models.py, scripts/api_client.py
- Read scripts/github_rl_scanner.py — follow the same patterns (scan() → ScanResult)
- This scanner detects companies actively hiring for RL roles

WHAT TO BUILD:

### scripts/job_posting_scanner.py

1. JobPostingClient(BaseAPIClient):
   - Uses SerpAPI or Google Custom Search API to find job postings
   - base_url depends on chosen API
   - search_jobs(query: str, date_restrict: str) -> list[dict]

2. JobPostingScanner:
   - JOB_TITLES: ["reinforcement learning engineer", "RL researcher",
     "simulation engineer", "RLHF engineer", "reward modeling",
     "RL environments", "policy optimization engineer",
     "ML engineer reinforcement learning"]
   - JOB_BOARD_SITES: ["linkedin.com/jobs", "lever.co", "greenhouse.io",
     "ashbyhq.com", "jobs.lever.co"]

   - scan(self, lookback_days: int = 7) -> ScanResult:
     a. For each job title query, search across job board sites
     b. Extract company name from each posting
     c. Group by company
     d. Score: 1 posting = WEAK, 2-3 = MODERATE, 4+ = STRONG
     e. Capture metadata: job titles, posting URLs, required skills
     f. Deduplicate across queries
     g. Return ScanResult

   - _extract_company_from_posting(self, result: dict) -> str | None:
     Parse the job board URL or search result snippet to extract company name.
     Different job boards have different URL patterns:
     - Lever: jobs.lever.co/{company-name}/...
     - Greenhouse: boards.greenhouse.io/{company-name}/...
     - LinkedIn: company name in the search result title

   - _extract_skills(self, posting_text: str) -> list[str]:
     Look for RL-related skills in the posting description:
     Gymnasium, PyTorch, TensorFlow, simulation, reward design, etc.

3. CLI interface: same pattern as other scanners

### Tests (write FIRST):
- test_scan_returns_scan_result
- test_extracts_company_from_lever_url
- test_extracts_company_from_greenhouse_url
- test_scoring_by_posting_count
- test_deduplicates_same_company_different_titles
- test_handles_empty_results
- test_metadata_includes_job_titles_and_urls
- test_extracts_rl_skills_from_description

Commit:
git add scripts/job_posting_scanner.py tests/unit/test_job_posting_scanner.py tests/fixtures/job_posting_responses.json
git commit -m "feat: add job posting signal scanner for RL hiring detection"

VERIFICATION:
- pytest tests/unit/test_job_posting_scanner.py -v — all pass, >80% coverage
```

---

### Task 2.6: Build Funding Event Tracker

**Files:**
- Create: `scripts/funding_tracker.py`
- Create: `tests/unit/test_funding_tracker.py`
- Create: `tests/fixtures/funding_responses.json`

**Why this scanner matters:** Funding events signal budget availability. When an AI/ML company raises a Series A-C, they're about to invest in infrastructure. The post-funding window (first 3-6 months) is when companies are most open to new tools — they have money to spend and roadmap to execute.

**Logic for the approach:**
- We use Crunchbase's free API tier or TechCrunch's RSS feed for funding data.
- Alternatively, we can use web search for recent funding announcements.
- Filter: AI/ML companies raising Series A-C with stated goals around agents, model training, or AI infrastructure.
- Cross-reference with other signals: a funded company that ALSO has RL repos is much higher priority.
- Signal strength: Seed round = WEAK, Series A = MODERATE, Series B+ = STRONG.

**Prompt:**
```
You are building the Funding Event Tracker for rl-gtm-engine.

SKILLS TO USE:
- superpowers:test-driven-development — Write ALL tests first
- coding-standards — Follow project conventions

CONTEXT:
- Read CLAUDE.md, scripts/models.py, scripts/api_client.py
- Read scripts/github_rl_scanner.py — follow the same patterns
- This scanner detects AI/ML companies that recently raised funding

WHAT TO BUILD:

### scripts/funding_tracker.py

1. FundingClient(BaseAPIClient):
   - Uses Crunchbase Basic API (free tier) or web search as fallback
   - search_funding_rounds(query: str, min_date: str) -> list[dict]

2. FundingTracker:
   - AI_KEYWORDS: ["artificial intelligence", "machine learning", "AI agents",
     "reinforcement learning", "LLM", "foundation model", "AI infrastructure",
     "model training", "autonomous systems"]

   - scan(self, lookback_days: int = 30) -> ScanResult:
     Note: Funding events use a LONGER lookback (30 days) because funding rounds
     are less frequent than code commits or paper publications.
     a. Search for AI/ML funding announcements in the last 30 days
     b. Filter by AI_KEYWORDS in company description or funding announcement
     c. Extract: company name, funding amount, round type, investors, stated use of funds
     d. Score: Seed = WEAK, Series A = MODERATE, Series B+ = STRONG
     e. Create signals with metadata: funding amount, round, investors, announced_date
     f. Return ScanResult

   - _classify_round(self, round_type: str) -> SignalStrength:
     Map funding round to signal strength:
     - "pre-seed", "seed" → WEAK
     - "series_a" → MODERATE
     - "series_b", "series_c", "series_d+" → STRONG
     - "grant", "undisclosed" → WEAK

3. CLI interface: --lookback-days defaults to 30 (not 7 like other scanners)

### Tests (write FIRST):
- test_scan_returns_scan_result
- test_filters_non_ai_companies
- test_scoring_by_round_type
- test_seed_is_weak
- test_series_b_is_strong
- test_longer_default_lookback
- test_metadata_includes_funding_amount
- test_handles_undisclosed_amount

Commit:
git add scripts/funding_tracker.py tests/unit/test_funding_tracker.py tests/fixtures/funding_responses.json
git commit -m "feat: add funding event tracker for AI/ML company fundraising detection"

VERIFICATION:
- pytest tests/unit/test_funding_tracker.py -v — all pass, >80% coverage
```

---

## Phase 3: ICP Scoring and Templates

**Why this phase exists:** Before we can build the skills (Phase 4), we need the scoring rubric and email templates that the skills will reference. These are the "knowledge" that the skills apply — the criteria for evaluating accounts and the patterns for writing outreach.

---

### Task 3.1: Create ICP Scoring Rubric

**Files:**
- Create: `templates/scoring-rubrics/icp-scoring-model.md`

**Why this matters:** The scoring rubric is the decision framework that turns raw data into actionable scores. Without a documented rubric, scoring is ad hoc and inconsistent. With one, any person or agent can evaluate an account and arrive at the same conclusion.

**Prompt:**
```
You are creating the ICP scoring rubric for rl-gtm-engine.

CONTEXT:
- Read .agents/gtm-context.md — this defines the ICP tiers, target titles, and disqualification criteria
- This rubric will be referenced by the prospect-researcher skill and the signal stacker

WHAT TO BUILD:

Create templates/scoring-rubrics/icp-scoring-model.md with:

## Scoring Dimensions (weighted)

### 1. Signal Strength (30% weight)
Composite signal score from the signal stacker.
- 5 points: A-tier (composite ≥ 9, multiple signal sources)
- 4 points: B-tier (composite ≥ 5)
- 2 points: C-tier (composite ≥ 2)
- 0 points: D-tier (single weak signal)

### 2. RL Maturity (25% weight)
How far along is the company in their RL journey?
- 5 points: PRODUCTIONIZING — RL in production, publishing research, dedicated RL team
- 4 points: SCALING — multiple RL projects, hiring RL engineers
- 2 points: BUILDING — active RL repos, experimenting
- 1 point: EXPLORING — mentioned RL in blog/job posts, no active work visible

### 3. Company Fit (20% weight)
Does the company match our ICP firmographics?
- 5 points: Tier 1 AI Lab (frontier model training with RLHF)
- 4 points: Tier 2 Enterprise Agent Builder (50-500 employees, Series A-C)
- 3 points: Tier 3 Robotics (sim-to-real transfer needs)
- 2 points: Tier 4 Industry-specific RL user
- 0 points: None of the above

### 4. Budget Likelihood (15% weight)
Can they afford enterprise RL infrastructure?
- 5 points: Recently funded (Series A+) OR enterprise (500+ employees)
- 3 points: Funded startup (seed+) with 20+ employees
- 1 point: Early stage or unclear funding
- 0 points: Pre-revenue, <10 employees

### 5. Accessibility (10% weight)
Can we reach the decision maker?
- 5 points: Verified email for Head of ML or equivalent
- 3 points: Verified email for VP Eng / CTO
- 1 point: LinkedIn only, no verified email
- 0 points: No contact found

## Composite Score Calculation
weighted_score = (signal × 0.30) + (maturity × 0.25) + (fit × 0.20) + (budget × 0.15) + (access × 0.10)
Max possible: 5.0

## Final ICP Grade
- A: weighted_score ≥ 4.0 → Immediate outreach, high-priority sequence
- B: weighted_score ≥ 3.0 → Outreach within 1 week, standard sequence
- C: weighted_score ≥ 2.0 → Add to monitoring list, reassess monthly
- D: weighted_score < 2.0 → Do not pursue unless new signals emerge

## Disqualification Override
Regardless of score, DISQUALIFY if:
- No RL activity detected (all signal types empty)
- Company explicitly using a competing managed solution AND satisfied
- Company has <10 employees AND no funding
- Decision maker explicitly said "not interested" in past 6 months

## Scoring Example
Company: Acme AI (Series B, 80 employees, 3 RL repos on GitHub, published RLHF paper)
- Signal: 4 (B-tier, composite 6.0) × 0.30 = 1.20
- Maturity: 4 (SCALING, hiring RL eng) × 0.25 = 1.00
- Fit: 4 (Tier 2, agent builder) × 0.20 = 0.80
- Budget: 5 (Series B, 80 emp) × 0.15 = 0.75
- Access: 3 (VP Eng email found) × 0.10 = 0.30
- Total: 4.05 → Grade A → Immediate outreach

Commit:
git add templates/scoring-rubrics/icp-scoring-model.md
git commit -m "docs: add ICP scoring rubric with weighted dimensions and grading criteria"

VERIFICATION:
- Read the file and verify the weights sum to 1.0 (0.30 + 0.25 + 0.20 + 0.15 + 0.10 = 1.00)
- Verify the scoring example calculation is correct
- Verify disqualification criteria match .agents/gtm-context.md
```

---

### Task 3.2: Create Email Sequence Templates

**Files:**
- Create: `templates/email-sequences/arxiv-paper-signal.md`
- Create: `templates/email-sequences/github-rl-signal.md`
- Create: `templates/email-sequences/hiring-signal.md`
- Create: `templates/email-sequences/funding-signal.md`
- Create: `templates/email-sequences/huggingface-model-signal.md`

**Why this matters:** These templates are the "copy playbook" for the email writer skill. Each template is tied to a specific signal type and contains the messaging logic: what angle to lead with, what to reference, what CTA to use. The email writer skill reads these templates and personalizes them with actual signal data.

**Logic for template design:**
- Each template has 3 variants (PROBLEM_FOCUSED, OUTCOME_FOCUSED, SOCIAL_PROOF_FOCUSED) for A/B testing
- Each template has a 3-email sequence: initial → follow-up (3 days later) → break-up (7 days later)
- All emails follow the rules from gtm-context.md: 4 sentences max, no fluff, specific signal reference, low-friction CTA

**Prompt:**
```
You are creating the email sequence templates for rl-gtm-engine.

CONTEXT:
- Read .agents/gtm-context.md — especially voice/tone section and proof points
- These templates will be used by the email-writer skill to generate personalized outreach
- Each template is for a specific signal type and contains placeholders like {{paper_title}}, {{repo_name}}, {{company_name}}, {{contact_first_name}}

WHAT TO BUILD:

Create 4 template files in templates/email-sequences/. Each follows this structure:

# [Signal Type] Email Sequence

## Signal Context
What this signal means about the prospect and why it's relevant to Collinear.

## Placeholders
List of variables the email writer will fill in:
- {{contact_first_name}}, {{company_name}}, {{signal_reference}}, etc.

## Sequence

### Email 1: Initial Outreach (Day 0)

#### Variant A: Problem-Focused
Subject: ...
Body: (4 sentences max)
CTA: ...

#### Variant B: Outcome-Focused
Subject: ...
Body: ...
CTA: ...

#### Variant C: Social-Proof-Focused
Subject: ...
Body: ...
CTA: ...

### Email 2: Follow-Up (Day 3)
(2-3 sentences, add value, don't just "checking in")

### Email 3: Break-Up (Day 7)
(2 sentences, final value-add, graceful exit)

SPECIFIC TEMPLATES:

### arxiv-paper-signal.md
- Signal: Company published an RL paper
- Angle: Reference the specific paper, connect their research area to environment bottleneck
- Placeholders: {{paper_title}}, {{research_area}}, {{author_name}}
- Example subject (Variant A): "{{paper_title}} — environment complexity"
- The body should demonstrate we actually read/understood the paper's implications

### github-rl-signal.md
- Signal: Company has active RL repos on GitHub
- Angle: Reference their repo/framework, acknowledge complexity of custom environments
- Placeholders: {{repo_name}}, {{framework}}, {{contributor_count}}
- Example subject (Variant A): "{{repo_name}} — environments at scale"
- Mention Gymnasium compatibility if they use Gymnasium

### hiring-signal.md
- Signal: Company is hiring RL engineers
- Angle: New RL engineers shouldn't spend their first quarter building environments
- Placeholders: {{job_title}}, {{job_url}}
- Example subject (Variant A): "scaling your RL team"
- Frame Collinear as accelerating new hire productivity

### funding-signal.md
- Signal: Company recently raised funding for AI/ML
- Angle: Post-funding infrastructure buildout, accelerate RL roadmap
- Placeholders: {{funding_amount}}, {{funding_round}}
- Example subject (Variant A): "RL infrastructure for {{company_name}}'s next phase"
- Frame as "don't build from scratch when you can start from here"

### huggingface-model-signal.md
- Signal: Company uploaded models trained with RL methods (PPO, DPO, GRPO) to Hugging Face Hub
- Angle: Reference the specific model and training method, connect to environment quality bottleneck for RL post-training
- Placeholders: {{model_name}}, {{training_method}}, {{model_size}}
- Example subject (Variant A): "{{training_method}} training for {{model_name}} — environment quality"
- This is distinct from GitHub signal: HF uploads indicate post-training/RLHF work specifically, not general RL research

IMPORTANT RULES FOR ALL TEMPLATES:
- First sentence MUST reference the specific signal (paper title, repo name, etc.)
- NEVER use "I hope this email finds you well" or any generic opener
- NEVER feature dump. Lead with the problem, hint at the solution.
- CTA must be low-friction: share a resource, 15-min technical chat, or a specific question
- Tone: technical peer writing to a technical peer
- Follow-ups add NEW value (share a blog post, reference a new case study), never "just following up"
- Break-up emails are graceful: "Figured this might not be the right time — sharing one last resource in case it's useful down the road."

Commit:
git add templates/email-sequences/
git commit -m "docs: add signal-specific email sequence templates with A/B variants"

VERIFICATION:
- Read each template and verify:
  - First sentence of every email references a signal placeholder
  - No email exceeds 4 sentences in the initial outreach
  - All 3 variants are present (Problem, Outcome, Social Proof)
  - Sequence has 3 steps (Day 0, Day 3, Day 7)
  - No generic sales language
```

---

## Phase 4: Claude Code Skills (SKILL.md Files)

**Why this phase exists:** The skills are the primary user interface of this project. When someone installs rl-gtm-engine and runs a skill, Claude reads the SKILL.md and follows its instructions to perform GTM tasks. Each skill is a "reference skill" type per the writing-skills framework — it documents how to use the tools and templates we built in previous phases.

**Critical context from superpowers:writing-skills:**
- Skills follow TDD: write pressure scenarios FIRST (RED), then write the skill (GREEN), then refine (REFACTOR)
- SKILL.md frontmatter has only `name` and `description` fields
- Description starts with "Use when..." and NEVER summarizes the workflow
- Skills must be token-efficient (<500 words for non-frequently-loaded skills)
- Each skill is tested with a subagent before deployment

**IMPORTANT: Each skill task below includes the TDD cycle from writing-skills. Do NOT skip the baseline testing step.**

---

### Task 4.1: Build Signal Scanner Skill

**Files:**
- Create: `skills/signal-scanner/SKILL.md`

**Why this skill matters:** This is the entry point to the entire engine. A GTM engineer invokes this skill when they want to discover new accounts showing RL buying signals. The skill orchestrates the Python scanners we built in Phase 2 and the signal stacker from Task 2.4.

**Prompt:**
```
You are building the Signal Scanner skill for rl-gtm-engine.

SKILLS TO USE:
- superpowers:writing-skills — THIS IS THE PRIMARY SKILL. Follow its TDD process exactly:
  1. RED: Run a baseline test WITHOUT the skill (see below)
  2. GREEN: Write the SKILL.md
  3. REFACTOR: Test and close loopholes

CONTEXT:
- Read CLAUDE.md for project conventions
- Read scripts/github_rl_scanner.py, scripts/arxiv_monitor.py, scripts/hf_model_monitor.py — these are the tools this skill invokes
- Read scripts/signal_stacker.py — this combines results from all scanners
- Read scripts/models.py — Signal, ScanResult, CompanyProfile models
- Read .agents/gtm-context.md — ICP context
- Read templates/scoring-rubrics/icp-scoring-model.md — scoring logic

BASELINE TEST (RED PHASE):
Before writing the skill, dispatch a subagent with this scenario:
"You are a GTM engineer. You need to find companies that are actively investing in reinforcement learning. You have Python scripts available at scripts/github_rl_scanner.py, scripts/arxiv_monitor.py, and scripts/hf_model_monitor.py. Run them and combine the results to produce a ranked list of target accounts."

Document what the subagent does WITHOUT the skill:
- Does it run all three scanners?
- Does it use the signal stacker to combine results?
- Does it filter by ICP score?
- Does it output in a useful format?
- What does it miss or do wrong?

WRITE THE SKILL (GREEN PHASE):
Based on the baseline gaps, write skills/signal-scanner/SKILL.md:

Frontmatter:
---
name: signal-scanner
description: Use when looking for companies actively investing in reinforcement learning, when needing to find new target accounts, or when running periodic signal detection scans
---

The skill should instruct Claude to:

1. Check prerequisites: Verify API keys are configured (run scripts/config.py validation)
2. Run all three scanners in sequence:
   - python -m scripts.github_rl_scanner --lookback-days 7 --output /tmp/github_signals.json
   - python -m scripts.arxiv_monitor --lookback-days 7 --output /tmp/arxiv_signals.json
   - python -m scripts.hf_model_monitor --lookback-days 7 --output /tmp/hf_signals.json
3. Stack signals:
   - python -m scripts.signal_stacker --inputs /tmp/github_signals.json /tmp/arxiv_signals.json /tmp/hf_signals.json --output /tmp/stacked_results.json
4. Present results to the user:
   - Summary: "Found X signals across Y companies"
   - Table: Company | ICP Score | Signals | Composite Score
   - A-tier accounts highlighted for immediate action
   - Recommend next step: "Run prospect-researcher on A-tier accounts"

Include:
- Quick reference table of signal sources and what they detect
- Common mistakes section (e.g., "Don't run without GitHub token — halves your rate limit")
- When NOT to use: "Don't use for non-RL markets — signal sources are RL-specific"

REFINE (REFACTOR PHASE):
Test the skill by dispatching a subagent WITH the skill loaded. Verify:
- Does it run all three scanners?
- Does it use the stacker?
- Does it present results clearly?
- Close any gaps found.

Commit:
git add skills/signal-scanner/SKILL.md
git commit -m "feat: add signal-scanner skill for RL buying signal detection"

VERIFICATION:
- Word count: wc -w skills/signal-scanner/SKILL.md (should be <500 words)
- Frontmatter: name and description only, description starts with "Use when"
- Verify all three scanner scripts are referenced with correct paths
```

---

### Task 4.2: Build Prospect Researcher Skill

**Files:**
- Create: `skills/prospect-researcher/SKILL.md`

**Prompt:**
```
You are building the Prospect Researcher skill for rl-gtm-engine.

SKILLS TO USE:
- superpowers:writing-skills — Follow TDD process (RED baseline → GREEN write → REFACTOR test)

CONTEXT:
- Read .agents/gtm-context.md — ICP definitions, RL maturity stages
- Read templates/scoring-rubrics/icp-scoring-model.md — scoring dimensions and weights
- Read scripts/models.py — CompanyProfile, ICPTier, RLMaturityStage models
- This skill takes a company name/domain and produces a structured ICP fit assessment
- It uses web search and the signal data to research a company

BASELINE TEST (RED):
Dispatch subagent: "Research the company 'Cohere' to determine if they're a good fit for selling RL infrastructure. Score them against an ICP."
Document gaps in how the agent approaches this without the skill.

WRITE THE SKILL (GREEN):
Frontmatter:
---
name: prospect-researcher
description: Use when evaluating a specific company's fit for RL infrastructure sales, when needing to score an account against ICP criteria, or when preparing for outreach to a new target
---

The skill should instruct Claude to:

1. Accept input: company name or domain
2. Research the company across multiple dimensions:
   a. Firmographic: Size, funding, location, vertical (use web search)
   b. Technographic: ML frameworks, cloud provider, RL libraries (check GitHub, job posts)
   c. RL Maturity: Classify as EXPLORING/BUILDING/SCALING/PRODUCTIONIZING based on signals
   d. Team mapping: Find likely decision makers and their titles
   e. Competitive: Are they building in-house? Using a competitor?
3. Score using the ICP scoring rubric (reference templates/scoring-rubrics/icp-scoring-model.md):
   - Score each of the 5 dimensions (0-5)
   - Calculate weighted composite
   - Assign A/B/C/D grade
4. Output a structured company brief:
   - Company name, domain, employee count, funding stage
   - ICP tier, ICP score, RL maturity stage
   - Key signals found
   - Recommended outreach approach
   - Key contacts to target
   - Suggested messaging angles

Include a reference to the scoring rubric file and the maturity stage definitions.

REFACTOR:
Test with subagent, verify it follows the scoring rubric exactly.

Commit:
git add skills/prospect-researcher/SKILL.md
git commit -m "feat: add prospect-researcher skill for ICP scoring and company analysis"
```

---

### Task 4.3: Build Contact Finder Skill

**Files:**
- Create: `skills/contact-finder/SKILL.md`

**Prompt:**
```
You are building the Contact Finder skill for rl-gtm-engine.

SKILLS TO USE:
- superpowers:writing-skills — Follow TDD process

CONTEXT:
- Read .agents/gtm-context.md — target titles in priority order
- Read scripts/models.py — Contact, ContactTitle, EnrichmentSource models
- This skill performs waterfall enrichment: tries multiple data providers in sequence until it finds a verified email
- It does NOT make real API calls (Claude can't call Apollo/Hunter APIs directly) — instead it INSTRUCTS the user on how to use these tools OR integrates with n8n/Clay for automated enrichment

IMPORTANT DESIGN DECISION:
Unlike the scanners (which are Python scripts Claude invokes), contact enrichment requires API keys for paid services (Apollo, Hunter, Prospeo) that may or may not be available. The skill should support two modes:
- Automated mode: Guide the user to use the n8n enrichment pipeline (Task 6.2) which handles waterfall enrichment automatically via API calls. The skill does NOT invoke enrichment scripts directly — n8n handles that.
- Manual mode: Guide the user through a step-by-step process using each tool's web UI (Apollo search, Hunter lookup, etc.) when n8n is not set up or for ad-hoc enrichment of individual contacts.

BASELINE TEST (RED):
Dispatch subagent: "Find the verified email address for the Head of ML at Cohere. Try multiple data providers."
Document what the agent does without the skill.

WRITE THE SKILL (GREEN):
Frontmatter:
---
name: contact-finder
description: Use when needing to find verified email addresses and LinkedIn profiles for ML decision-makers at target accounts, or when performing waterfall enrichment across multiple data providers
---

The skill should instruct Claude to:

1. Accept input: company name/domain + target title(s)
2. Define the waterfall sequence:
   Step 1: Apollo.io — Search by company + title → Get email + LinkedIn
   Step 2: Hunter.io — Domain email pattern lookup + verification
   Step 3: Prospeo — LinkedIn URL-based email enrichment
   Step 4: PeopleDataLabs — API fallback
   Step 5: ZeroBounce/Debounce — Validate any email found
3. For each step:
   - Check if API key is configured
   - If yes: provide exact API call syntax
   - If no: provide web UI instructions (URL, what to search, what to copy)
   - Stop the waterfall as soon as a verified email is found
4. Output a Contact record with all found data
5. Log which enrichment source was successful (for tracking coverage rates)

Include:
- Title priority order (from gtm-context.md)
- What "verified" means (ZeroBounce status = "valid", not "catch-all" or "unknown")
- Common mistakes: "Don't skip validation — unverified emails harm sender reputation"

Commit:
git add skills/contact-finder/SKILL.md
git commit -m "feat: add contact-finder skill with waterfall enrichment logic"
```

---

### Task 4.4: Build Email Writer Skill

**Files:**
- Create: `skills/email-writer/SKILL.md`

**Prompt:**
```
You are building the Email Writer skill for rl-gtm-engine.

SKILLS TO USE:
- superpowers:writing-skills — Follow TDD process

CONTEXT:
- Read .agents/gtm-context.md — voice/tone rules, product positioning, proof points
- Read templates/email-sequences/*.md — ALL four templates. The skill uses these as the base copy.
- Read scripts/models.py — GeneratedEmail, EmailVariant, SignalType models
- This skill takes a signal + contact + company research and generates personalized outreach

BASELINE TEST (RED):
Dispatch subagent: "Write a cold outreach email to the Head of ML at a company that just published an RL paper on ArXiv titled 'Reward Shaping for Multi-Agent Navigation'. The company is Acme AI, a Series B startup with 80 employees. You're selling RL environment infrastructure."
Document: Does the agent write technically credible copy? Does it reference the paper specifically? Is it too long? Is the CTA appropriate?

WRITE THE SKILL (GREEN):
Frontmatter:
---
name: email-writer
description: Use when generating outreach emails for target accounts, when personalizing email copy based on detected signals, or when creating A/B test variants for cold email campaigns
---

The skill should instruct Claude to:

1. Accept inputs:
   - Signal type (GITHUB_RL_REPO, ARXIV_PAPER, HIRING, FUNDING)
   - Signal payload (specific paper title, repo name, job URL, funding amount)
   - Contact info (name, title, company)
   - Company research (from prospect-researcher output)

2. Select the matching template from templates/email-sequences/

3. Generate 3 variants (Problem-Focused, Outcome-Focused, Social-Proof-Focused):
   - Fill in all placeholders with actual data
   - Personalize beyond the template: reference specific details from research
   - Generate the full 3-email sequence (Day 0, Day 3, Day 7)

4. Apply quality checks:
   - First sentence references specific signal? ✓/✗
   - Under 4 sentences? ✓/✗
   - No generic openers? ✓/✗
   - Low-friction CTA? ✓/✗
   - Technical tone? ✓/✗
   - No feature dumps? ✓/✗

5. Output:
   - All 3 variants with labels
   - Recommended variant (based on signal type — e.g., ArXiv signals work best with Problem-Focused)
   - The full sequence for each variant

Include:
- Reference to each template file
- Quality checklist as a quick-reference table
- Common mistakes: "Don't add 'P.S.' lines — they scream sales email to technical buyers"

Commit:
git add skills/email-writer/SKILL.md
git commit -m "feat: add email-writer skill with signal-aware personalization and A/B variants"
```

---

### Task 4.5: Build Pipeline Tracker Skill

**Files:**
- Create: `skills/pipeline-tracker/SKILL.md`

**Prompt:**
```
You are building the Pipeline Tracker skill for rl-gtm-engine.

SKILLS TO USE:
- superpowers:writing-skills — Follow TDD process

CONTEXT:
- Read .agents/gtm-context.md — understand the full pipeline stages
- Read scripts/models.py — Deal, DealStage, CompanyProfile models
- This skill manages CRM sync, pipeline analytics, and reporting
- It interfaces with HubSpot CRM (free tier) and tracks outbound metrics

BASELINE TEST (RED):
Dispatch subagent: "I've been running outbound for 2 weeks. I need to know: how many signals were detected, how many accounts qualified, how many emails sent, reply rate, and meetings booked. Set up tracking for this."
Document how the agent approaches pipeline management without the skill.

WRITE THE SKILL (GREEN):
Frontmatter:
---
name: pipeline-tracker
description: Use when needing to sync outbound activity to CRM, generate pipeline analytics, create weekly reports, or track conversion metrics across the outbound funnel
---

The skill should instruct Claude to:

1. CRM Setup (one-time):
   - Create custom properties in HubSpot: signal_source, signal_score, icp_tier, rl_maturity, outreach_sequence, signal_detected_date
   - Create pipeline stages matching DealStage enum
   - Set up contact-to-deal associations

2. Auto-population:
   - When a prospect enters a sequence: create contact + deal in HubSpot
   - Set initial stage to SIGNAL_DETECTED
   - Tag with signal source and composite score

3. Engagement tracking:
   - Update deal stages based on events:
     - Email opened → ENGAGED
     - Positive reply → RESPONDED
     - Meeting booked → MEETING_SCHEDULED
     - Negative reply → note on deal, remove from sequence
   - Log all state changes with timestamps

4. Weekly reporting:
   Generate a report with:
   - Signals detected this week
   - Accounts qualified (A + B tier)
   - Contacts enriched (verified emails found)
   - Sequences launched
   - Reply rate (positive / total sent)
   - Meetings booked
   - Cost per meeting (total tool spend / meetings)
   - Pipeline value (sum of deal values)
   - Key ratios: signal→qualified, qualified→reply, reply→meeting
   - Week-over-week trends

5. Slack notifications (optional):
   - A-tier account detected
   - Positive reply received
   - Meeting booked

Include funnel conversion benchmarks from the spec (8-15% reply rate month 1, etc.)

Commit:
git add skills/pipeline-tracker/SKILL.md
git commit -m "feat: add pipeline-tracker skill for CRM sync and outbound analytics"
```

---

## Phase 5: Additional Skills (From Research)

**Why this phase exists:** Our research identified capabilities that the broader GTM engineering community needs but that most open-source projects lack. These three skills differentiate rl-gtm-engine from competitors and make it genuinely useful to other GTM engineers, not just for the Collinear use case.

---

### Task 5.1: Build Deliverability Manager Skill

**Files:**
- Create: `skills/deliverability-manager/SKILL.md`

**Why this skill matters:** If your emails land in spam, nothing else in the engine works. Deliverability infrastructure — domain setup, DNS configuration, warmup, volume ramping — is the unsexy foundation that 80% of failed outbound programs neglect. GTM engineers cite this as one of their top responsibilities, yet no open-source tool documents the full process.

**Prompt:**
```
You are building the Deliverability Manager skill for rl-gtm-engine.

SKILLS TO USE:
- superpowers:writing-skills — Follow TDD process

CONTEXT:
- This is a NEW skill not in the original spec. It was identified through research as a critical gap.
- It covers email sending infrastructure: domain setup, DNS records, warmup, monitoring.
- It's tool-agnostic but references Instantly.ai (the project's email tool) for specifics.

BASELINE TEST (RED):
Dispatch subagent: "I need to set up cold email sending infrastructure for a B2B outbound campaign. I want to send 50 emails/day initially and scale to 200/day. Help me set up domains, DNS, and warmup."
Document what the agent misses without the skill.

WRITE THE SKILL (GREEN):
Frontmatter:
---
name: deliverability-manager
description: Use when setting up cold email sending infrastructure, configuring DNS records for new sending domains, planning email warmup schedules, or troubleshooting deliverability issues like high bounce rates or spam folder placement
---

The skill should cover:

1. Domain Strategy:
   - Buy 3-5 secondary domains (variations of primary: collinear-ai.com, getcollinear.com, etc.)
   - NEVER send cold email from primary domain (protects main domain reputation)
   - Set up Google Workspace on each secondary domain ($6/user/mo)
   - Create 2-3 sending accounts per domain (e.g., sami@, team@, hello@)

2. DNS Configuration:
   For each domain, configure:
   - SPF record: v=spf1 include:_spf.google.com ~all
   - DKIM: Generate via Google Workspace → Authenticate email
   - DMARC: v=DMARC1; p=none; rua=mailto:dmarc@yourdomain.com
   - Custom tracking domain in Instantly.ai (CNAME record)

   Explain WHY each record matters:
   - SPF: Tells receiving servers which IPs can send from your domain
   - DKIM: Cryptographic signature proving email wasn't tampered with
   - DMARC: Policy for handling emails that fail SPF/DKIM checks

3. Warmup Protocol:
   - Week 1-2: 5 emails/day/account (warmup enabled in Instantly.ai)
   - Week 3-4: 15 emails/day/account
   - Week 5+: 25-30 emails/day/account (max recommended)
   - Total capacity at scale: 5 domains × 3 accounts × 25 emails = 375/day
   - Monitor: open rates, bounce rates, spam complaints

4. Ongoing Monitoring:
   - Check blacklists weekly (MXToolbox)
   - Monitor Google Postmaster Tools
   - Track bounce rate (<2% is healthy, >5% pause and clean list)
   - Rotate domains if reputation drops

5. Troubleshooting:
   Common issues and fixes:
   - High bounce rate → Clean email list, improve verification
   - Landing in spam → Check DNS, reduce volume, improve content
   - Low open rates → A/B test subject lines, check sending time
   - Blacklisted → Stop sending, request delisting, rotate domain

Commit:
git add skills/deliverability-manager/SKILL.md
git commit -m "feat: add deliverability-manager skill for email infrastructure setup"
```

---

### Task 5.2: Build Champion Tracker Skill

**Files:**
- Create: `skills/champion-tracker/SKILL.md`

**Why this skill matters:** When a past champion (someone who used your product, responded positively to outreach, or was a power user) changes jobs, their new company becomes a warm lead. They already know and trust the product. Champion tracking has the highest conversion rate of any outbound play — UserGems reports 3x higher pipeline generation from champion tracking vs. cold outbound.

**Prompt:**
```
You are building the Champion Tracker skill for rl-gtm-engine.

SKILLS TO USE:
- superpowers:writing-skills — Follow TDD process

CONTEXT:
- This skill monitors job changes of important contacts
- Sources: LinkedIn (manual or Sales Navigator), Apollo job change alerts, Clay job change enrichment
- When a champion moves companies, the skill triggers a research → score → outreach flow

BASELINE TEST (RED):
Dispatch subagent: "One of our best contacts, Dr. Jane Smith who was Head of ML at Acme AI, just moved to a new company. Help me figure out where she went and whether her new company is a fit for RL infrastructure."
Document how the agent handles this without the skill.

WRITE THE SKILL (GREEN):
Frontmatter:
---
name: champion-tracker
description: Use when monitoring job changes of past customers, positive responders, or engaged prospects, or when a known contact moves to a new company and you need to evaluate the new opportunity
---

The skill should cover:

1. Champion List Setup:
   - Define who counts as a "champion": past customer, positive email responder, demo attendee, open-source contributor who engaged with Collinear content
   - Store champion list: Name, LinkedIn URL, last known company, relationship context
   - Recommended tool: Clay table with job change monitoring enabled

2. Job Change Detection:
   - Clay: Set up "Job Change" enrichment on champion list (runs automatically)
   - Apollo: Enable "People Alerts" for champion contacts
   - LinkedIn Sales Nav: Set up "Lead Alerts" for saved leads
   - Manual: Periodic LinkedIn check of key champions

3. When Job Change Detected:
   a. Identify new company (from Clay/Apollo/LinkedIn)
   b. Run prospect-researcher skill on the new company
   c. If ICP score ≥ B:
      - Run contact-finder to verify new email
      - Generate outreach using a special "champion" template:
        "Congrats on the move to {{new_company}}! At {{old_company}}, we worked on...
         Curious if {{new_company}} is exploring RL environments?"
      - Priority: immediate outreach (within 48 hours of detecting the change)
   d. If ICP score < B:
      - Note in CRM, keep monitoring
      - The champion might advocate internally later

4. Champion Outreach Template:
   - Warmer tone than cold outreach (you have a relationship)
   - Reference the shared history
   - Still brief (4 sentences max)
   - CTA: "Would love to catch up on what you're building at {{new_company}}"

Commit:
git add skills/champion-tracker/SKILL.md
git commit -m "feat: add champion-tracker skill for job change monitoring and warm outbound"
```

---

### Task 5.3: Build Compliance Manager Skill

**Files:**
- Create: `skills/compliance-manager/SKILL.md`

**Why this skill matters:** As outbound scales, compliance with GDPR, CAN-SPAM, and CCPA becomes non-negotiable. Getting it wrong means legal liability, domain blacklisting, and permanent reputation damage. Most open-source GTM tools completely ignore compliance, which is both a gap and an opportunity to differentiate.

**Prompt:**
```
You are building the Compliance Manager skill for rl-gtm-engine.

SKILLS TO USE:
- superpowers:writing-skills — Follow TDD process
- security-review — Verify data handling recommendations are secure

CONTEXT:
- This skill manages opt-out lists, suppression lists, and regulatory compliance
- It applies to all outbound activity across the entire engine
- Key regulations: CAN-SPAM (US), GDPR (EU), CCPA (California), CASL (Canada)

BASELINE TEST (RED):
Dispatch subagent: "I'm sending cold emails to prospects in the US and EU. What compliance requirements do I need to follow? How do I handle opt-outs?"
Document what the agent misses without the skill.

WRITE THE SKILL (GREEN):
Frontmatter:
---
name: compliance-manager
description: Use when setting up outbound email compliance, managing opt-out and suppression lists, handling GDPR/CAN-SPAM/CCPA requirements, or when a prospect requests data deletion
---

The skill should cover:

1. Regulatory Requirements:
   - CAN-SPAM (US): Physical address required, opt-out mechanism required, honor opt-outs within 10 business days
   - GDPR (EU/UK): Legitimate interest basis for B2B cold email (document your basis), right to erasure, data processing records
   - CCPA (California): Right to know, right to delete, right to opt-out of sale
   - CASL (Canada): Implied consent for B2B (but stricter — include unsubscribe, identify yourself)

2. Suppression Lists:
   - Global opt-out list: Synced across ALL sending tools (Instantly, HubSpot, manual)
   - Current customer list: Never cold email existing customers
   - Competitor list: Optional — some teams exclude competitors
   - Past negative replies: Anyone who said "not interested" or "unsubscribe"
   - Bounced emails: Remove permanently after hard bounce
   - Format: CSV with email, reason, date_added, source
   - Storage: Google Sheet synced to Instantly.ai suppression list

3. Opt-Out Handling:
   - Every email must include unsubscribe link (Instantly.ai handles this)
   - When opt-out received:
     a. Remove from all active sequences immediately
     b. Add to global suppression list
     c. Update CRM record with opt-out date and source
     d. Never contact this email again from any tool
   - When "not interested" reply (but no explicit opt-out):
     a. Remove from current sequence
     b. Add to 6-month cooling-off list
     c. May re-approach after 6 months if new signal detected

4. Data Handling:
   - Personal data (emails, names) stored only in: HubSpot CRM, Instantly.ai, Clay
   - No personal data in git repos, logs, or scan output files
   - Scan results use company names and domains (not personal data)
   - Contact data is enrichment tool → CRM pipeline only
   - GDPR deletion request: Remove from all three systems within 30 days

5. Audit Checklist (run monthly):
   - [ ] Suppression list synced across all tools?
   - [ ] All active sequences have unsubscribe links?
   - [ ] Physical address in email footer?
   - [ ] No personal data in git repo?
   - [ ] Opt-out requests honored within 10 days?
   - [ ] GDPR legitimate interest documentation up to date?

Commit:
git add skills/compliance-manager/SKILL.md
git commit -m "feat: add compliance-manager skill for GDPR/CAN-SPAM/CCPA outbound compliance"
```

---

## Phase 6: n8n Workflow Definitions

**Why this phase exists:** The skills (Phase 4-5) are interactive — a human invokes them and Claude executes. The n8n workflows are autonomous — they run on a schedule without human intervention. Together, they form a complete system: n8n detects signals daily and routes them to enrichment, while skills handle ad-hoc research, manual review, and outreach generation.

**Logic for the n8n approach:**
- n8n is chosen over Zapier/Make because it charges per execution (not per step), making complex multi-step workflows dramatically cheaper.
- Workflows are stored as JSON files in the repo. They can be imported into any n8n instance.
- Each workflow is self-contained: it connects to the APIs it needs, processes data, and outputs results.

---

### Task 6.1: Build Daily Signal Scan Workflow

**Files:**
- Create: `n8n-workflows/daily-signal-scan.json`
- Create: `docs/n8n-setup-guide.md` (partial — signal scan section)

**Prompt:**
```
You are building the Daily Signal Scan n8n workflow for rl-gtm-engine.

CONTEXT:
- Read ALL scanner scripts: github_rl_scanner.py, arxiv_monitor.py, hf_model_monitor.py, job_posting_scanner.py, funding_tracker.py
- Read scripts/signal_stacker.py — combines results
- Read scripts/models.py — output data shapes
- n8n workflows are JSON files that define a visual workflow of nodes and connections
- This workflow runs daily at 7:00 AM PST via cron trigger

WHAT TO BUILD:

### n8n-workflows/daily-signal-scan.json

Create an n8n workflow JSON with these nodes:

1. Cron Trigger: Daily at 7:00 AM PST (14:00 UTC)

2. GitHub Scanner (Execute Command node):
   - Command: python -m scripts.github_rl_scanner --lookback-days 7 --output /tmp/github_signals.json
   - Working directory: /path/to/rl-gtm-engine

3. ArXiv Monitor (Execute Command node):
   - Command: python -m scripts.arxiv_monitor --lookback-days 7 --output /tmp/arxiv_signals.json
   - Runs in parallel with GitHub Scanner (both triggered by cron)

4. HuggingFace Monitor (Execute Command node):
   - Command: python -m scripts.hf_model_monitor --lookback-days 7 --output /tmp/hf_signals.json
   - Runs in parallel with the other scanners

5. Job Posting Scanner (Execute Command node):
   - Command: python -m scripts.job_posting_scanner --lookback-days 7 --output /tmp/job_signals.json
   - Runs in parallel with the other scanners

6. Funding Tracker (Execute Command node):
   - Command: python -m scripts.funding_tracker --lookback-days 30 --output /tmp/funding_signals.json
   - Note: Uses 30-day lookback (funding events are less frequent)
   - Runs in parallel with the other scanners

7. Wait for All (Merge node):
   - Wait for all five scanners to complete
   - Mode: "Wait for All"

8. Signal Stacker (Execute Command node):
   - Command: python -m scripts.signal_stacker --inputs /tmp/github_signals.json /tmp/arxiv_signals.json /tmp/hf_signals.json /tmp/job_signals.json /tmp/funding_signals.json --output /tmp/stacked_results.json
   - Triggered after Merge node

9. Deduplication Check (Code node):
   - Read stacked results
   - Check each company against Google Sheets "Master Signal List"
   - Filter out companies already in active sequences
   - Output: new signals only

10. Google Sheets Write (Google Sheets node):
    - Append new signals to Master Signal List
    - Columns: Company, Domain, ICP Score, Composite Score, Signal Types, Detected Date, Status

11. A-Tier Alert (IF node):
    - Condition: icp_score == "A"
    - True branch → Slack notification
    - False branch → end

12. Slack Notification (Slack node):
    - Channel: #gtm-signals
    - Message: "🎯 A-Tier Signal Detected: {{company_name}} (Score: {{composite_score}}). Signals: {{signal_types}}. Action: Run prospect-researcher immediately."

13. Trigger Enrichment (HTTP Request node):
    - For A-tier signals, fire webhook to Enrichment Pipeline workflow (Task 6.2)
    - URL: (n8n webhook URL for enrichment workflow)
    - Body: the new A-tier signal data

Also create the relevant section in docs/n8n-setup-guide.md explaining:
- How to import the workflow into n8n
- What environment variables to configure in n8n
- How to set up the Google Sheets connection
- How to configure the Slack integration
- How to verify the cron trigger is working

NOTE: The JSON structure follows n8n's workflow format. Each node has:
- id, name, type, position (x,y coordinates), parameters, credentials
- Connections between nodes defined in the "connections" object

You may not know the exact n8n JSON schema perfectly — that's OK. Create the best approximation
and document any manual adjustments needed in the setup guide.

Commit:
git add n8n-workflows/daily-signal-scan.json docs/n8n-setup-guide.md
git commit -m "feat: add daily signal scan n8n workflow with Slack alerts and enrichment trigger"
```

---

### Task 6.2: Build Enrichment Pipeline Workflow

**Files:**
- Create: `n8n-workflows/enrichment-pipeline.json`
- Update: `docs/n8n-setup-guide.md` (add enrichment section)

**Prompt:**
```
You are building the Enrichment Pipeline n8n workflow for rl-gtm-engine.

CONTEXT:
- Read n8n-workflows/daily-signal-scan.json — this workflow is triggered BY the signal scan
- Read skills/contact-finder/SKILL.md — understand the waterfall enrichment logic
- Read templates/scoring-rubrics/icp-scoring-model.md — understand scoring
- This workflow auto-enriches new signal hits through the waterfall pattern

WHAT TO BUILD:

### n8n-workflows/enrichment-pipeline.json

Nodes:

1. Webhook Trigger: Receives new signal data from daily scan workflow (or manual trigger)

2. Read Signals (Code node): Parse incoming signal data, extract company names and domains

3. Clay Enrichment (HTTP Request node):
   - POST to Clay API with company domain
   - Returns: firmographic data, funding, tech stack, team info
   - If Clay API key not configured: skip this node (use IF node to check)

4. Contact Search Loop (Loop node):
   For each company, iterate through the waterfall:

   4a. Apollo Search (HTTP Request):
       - Search by company domain + target titles
       - Extract: name, email, title, LinkedIn URL
       - If email found → skip to step 4e

   4b. Hunter Search (HTTP Request):
       - Domain email pattern lookup
       - If email found → skip to step 4e

   4c. Prospeo Search (HTTP Request):
       - LinkedIn URL-based enrichment (requires LinkedIn URL from earlier step)
       - If email found → proceed to 4e

   4d. No Contact Found (Code node):
       - Log: "No contact found for {{company_name}}"
       - Mark as "needs manual research" in Google Sheets
       - Continue to next company

   4e. Email Validation (HTTP Request):
       - Send email to ZeroBounce API
       - If status = "valid" → keep
       - If status = "catch-all" or "unknown" → flag for manual verification
       - If status = "invalid" → discard, continue waterfall

5. ICP Scoring (Code node):
   - Apply scoring rubric from templates/scoring-rubrics/icp-scoring-model.md
   - Calculate weighted score across all 5 dimensions
   - Assign A/B/C/D grade

6. HubSpot Push (HubSpot node):
   - Create contact record with enriched data
   - Create associated deal with ICP score and signal data
   - Set deal stage to RESEARCHED

7. Qualification Gate (IF node):
   - A-tier → trigger Sequence Launcher workflow (Task 6.3)
   - B-tier → add to "Review Queue" in Google Sheets for manual review
   - C/D-tier → log and close

8. Update Google Sheets (Google Sheets node):
   - Update Master Signal List with enrichment results
   - Set Status = "Enriched" with enrichment date

Add enrichment section to docs/n8n-setup-guide.md.

Commit:
git add n8n-workflows/enrichment-pipeline.json docs/n8n-setup-guide.md
git commit -m "feat: add enrichment pipeline n8n workflow with waterfall contact finding"
```

---

### Task 6.3: Build Sequence Launcher Workflow

**Files:**
- Create: `n8n-workflows/sequence-launcher.json`
- Update: `docs/n8n-setup-guide.md`

**Prompt:**
```
You are building the Sequence Launcher n8n workflow for rl-gtm-engine.

CONTEXT:
- Read n8n-workflows/enrichment-pipeline.json — this triggers the sequence launcher
- Read skills/email-writer/SKILL.md — understand email generation logic
- Read templates/email-sequences/*.md — the templates used for generation
- This workflow generates personalized email copy and pushes contacts into Instantly.ai campaigns

WHAT TO BUILD:

### n8n-workflows/sequence-launcher.json

Nodes:

1. Webhook/Manual Trigger: Receives qualified contact data from enrichment pipeline

2. Template Selection (Code node):
   - Based on primary signal type, select email template:
     - GITHUB_RL_REPO → github-rl-signal template
     - ARXIV_PAPER → arxiv-paper-signal template
     - JOB_POSTING → hiring-signal template
     - FUNDING_EVENT → funding-signal template
     - HUGGINGFACE_MODEL → huggingface-model-signal template

3. Email Generation (OpenAI/Claude API node):
   - System prompt: Load voice/tone from .agents/gtm-context.md
   - User prompt: Fill template placeholders with actual signal data + contact info
   - Generate 3 variants (Problem, Outcome, Social Proof)
   - Generate 3-email sequence for each variant
   - Output: structured JSON with all email copy

4. Variant Selection (Code node):
   - Select the variant to use for this contact
   - Default strategy: rotate through variants (1/3 each for even A/B testing)
   - Track which variant is assigned in Google Sheets

5. Instantly.ai Push (HTTP Request node):
   - POST to Instantly.ai API: Add contact to campaign
   - Set email copy from generated variant
   - Configure sequence timing: Email 1 → Day 0, Email 2 → Day 3, Email 3 → Day 7
   - Enable inbox rotation across sending accounts

6. HubSpot Update (HubSpot node):
   - Update deal stage to SEQUENCED
   - Add custom properties: campaign_id, sequence_start_date, email_variant

7. Slack Notification (Slack node):
   - Post to #gtm-outbound: "📧 Sequenced: {{contact_name}} at {{company_name}} ({{signal_type}}). Variant: {{variant}}."

8. Google Sheets Log (Google Sheets node):
   - Log: contact, company, signal, variant, campaign_id, send_date

Update docs/n8n-setup-guide.md with setup instructions.

Commit:
git add n8n-workflows/sequence-launcher.json docs/n8n-setup-guide.md
git commit -m "feat: add sequence launcher n8n workflow with email generation and Instantly.ai push"
```

---

### Task 6.4: Build CRM Sync Workflow

**Files:**
- Create: `n8n-workflows/crm-sync.json`
- Update: `docs/n8n-setup-guide.md`

**Prompt:**
```
You are building the CRM Sync n8n workflow for rl-gtm-engine.

CONTEXT:
- Read all other n8n workflows for patterns
- Read skills/pipeline-tracker/SKILL.md — understand deal stages and tracking
- This workflow handles bidirectional sync: Instantly.ai events → HubSpot, and daily analytics

WHAT TO BUILD:

### n8n-workflows/crm-sync.json

This workflow has TWO triggers (create as two separate workflow branches):

Branch 1: Engagement Event Handler (Webhook trigger)
- Receives Instantly.ai webhooks for: email_opened, email_replied, email_bounced
- For email_opened: Update HubSpot deal stage → ENGAGED
- For email_replied:
  a. Classify reply using OpenAI/Claude API: positive / neutral / negative
  b. If positive: Update deal → RESPONDED, Slack alert "🎉 Positive reply from {{name}}"
  c. If neutral: Update deal → RESPONDED, no alert
  d. If negative: Update deal → DISQUALIFIED, remove from sequence, add to suppression list
- For email_bounced: Remove contact, mark email as invalid, log for enrichment review

Branch 2: Daily Analytics (Cron trigger, daily at 6 PM PST)
- Pull all deals from HubSpot
- Calculate metrics:
  - Total signals detected (deals created this week)
  - Accounts qualified (A + B tier)
  - Sequences active
  - Emails sent (from Instantly.ai API)
  - Reply rate (replies / emails sent)
  - Positive reply rate (positive / total replies)
  - Meetings booked (deals at MEETING_SCHEDULED stage)
  - Cost per meeting (configurable monthly spend / meetings)
  - Conversion: signal→qualified, qualified→reply, reply→meeting
- Write to Google Sheets "Analytics Dashboard" tab
- Post Slack digest: "📊 Daily GTM Report: X signals, Y replies, Z meetings"

Update docs/n8n-setup-guide.md with:
- How to set up Instantly.ai webhooks
- How to configure the analytics dashboard Google Sheet
- How to set the monthly spend variable for cost-per-meeting calculation

Commit:
git add n8n-workflows/crm-sync.json docs/n8n-setup-guide.md
git commit -m "feat: add CRM sync n8n workflow with engagement tracking and daily analytics"
```

---

## Phase 7: Documentation

**Why this phase exists:** For an open-source project, documentation IS the product. Without clear docs, nobody can install or use the system, and it dies on GitHub with 3 stars.

---

### Task 7.1: Write Architecture Documentation

**Files:**
- Create: `docs/architecture.md`

**Prompt:**
```
You are writing the architecture documentation for rl-gtm-engine.

CONTEXT:
- Read CLAUDE.md for project overview
- Read ALL skills in skills/ directory
- Read ALL scripts in scripts/ directory
- Read ALL n8n workflows in n8n-workflows/
- Read .agents/gtm-context.md

WHAT TO BUILD:

Create docs/architecture.md covering:

1. System Overview: High-level description of the three layers (Skills → Scripts → n8n)

2. Data Flow Diagram (text-based):
   Signal Sources (GitHub, ArXiv, HF Hub)
   → Python Scanners (scan() → ScanResult)
   → Signal Stacker (ScanResult[] → CompanyProfile[])
   → Enrichment Pipeline (CompanyProfile → Contact)
   → Email Generation (Signal + Contact → GeneratedEmail)
   → Sequence Launcher (GeneratedEmail → Instantly.ai campaign)
   → CRM Sync (Instantly.ai events → HubSpot)
   → Analytics (HubSpot → Google Sheets dashboard)

3. Component Reference:
   Table listing every component (script, skill, workflow, template) with:
   - Name, Type (script/skill/workflow/template), Purpose, Inputs, Outputs, Dependencies

4. Data Model Relationships:
   Signal → CompanyProfile → Contact → GeneratedEmail → Deal
   Show how models connect and flow through the pipeline.

5. Integration Points:
   - Which external APIs are used and where
   - Which tools talk to each other (n8n → scripts, skills → scripts, n8n → Instantly → HubSpot)
   - Authentication flow for each API

6. Design Decisions:
   - Why skills-first architecture (modularity, reusability, open-source friendliness)
   - Why Pydantic models (runtime validation, serialization, documentation)
   - Why separate scanners per source (Unix philosophy, independent testing, easy to add new sources)
   - Why waterfall enrichment (no single provider has complete coverage)
   - Why n8n over Zapier (cost at scale, self-hosting option, JSON-based workflows)

Commit:
git add docs/architecture.md
git commit -m "docs: add architecture documentation with data flow and design decisions"
```

---

### Task 7.2: Write Setup Guide

**Files:**
- Create: `docs/setup-guide.md` (comprehensive, consolidating from n8n-setup-guide.md)

**Prompt:**
```
You are writing the comprehensive setup guide for rl-gtm-engine.

CONTEXT:
- Read docs/n8n-setup-guide.md — consolidate n8n setup info
- Read .env.example — all required environment variables
- Read pyproject.toml — Python dependencies
- Read CLAUDE.md — project conventions

WHAT TO BUILD:

Create docs/setup-guide.md with step-by-step instructions:

1. Prerequisites:
   - Python 3.11+
   - Claude Code CLI installed
   - n8n Cloud account (or self-hosted)
   - API accounts: GitHub, Apollo.io (free), Instantly.ai, HubSpot (free)
   - Optional: Semantic Scholar API key, Hunter.io, Prospeo, Clay

2. Installation:
   - Clone the repo
   - Create virtual environment: python -m venv .venv && source .venv/bin/activate
   - Install dependencies: pip install -e ".[dev]"
   - Copy .env.example to .env and fill in API keys
   - Run tests: pytest (verify everything works)

3. Skills Installation:
   - How to make skills available in Claude Code
   - Verify: list available skills

4. API Key Setup:
   For EACH API (GitHub, Semantic Scholar, Apollo, Hunter, Prospeo, Instantly, HubSpot, ZeroBounce):
   - Where to sign up
   - Free tier limitations
   - How to get the API key
   - What to name the env variable

5. n8n Setup:
   - Import each workflow JSON
   - Configure credentials for each service
   - Set up webhook URLs
   - Test each workflow manually before enabling cron
   - Consolidate info from docs/n8n-setup-guide.md

6. HubSpot Setup:
   - Create custom properties
   - Set up pipeline stages
   - Configure private app for API access

7. Instantly.ai Setup:
   - Create campaigns
   - Add sending accounts
   - Configure webhook endpoints
   - Set up warmup

8. First Run:
   - Walk through running the signal scanner manually
   - Review results
   - Research one A-tier account
   - Enrich contacts
   - Generate and review email copy
   - Launch first sequence

Commit:
git add docs/setup-guide.md
git commit -m "docs: add comprehensive setup guide with step-by-step API configuration"
```

---

### Task 7.3: Write Cost Analysis and Results Framework

**Files:**
- Create: `docs/cost-analysis.md`
- Create: `docs/results-framework.md`

**Prompt:**
```
You are writing the cost analysis and results framework docs for rl-gtm-engine.

CONTEXT:
- Read the cost table from the project spec (included in the repo README or reference it)
- Read skills/pipeline-tracker/SKILL.md for metrics definitions
- These docs serve two purposes: (1) help users budget, (2) help users measure ROI

WHAT TO BUILD:

### docs/cost-analysis.md

1. Tool-by-Tool Cost Breakdown:
   For each tool: name, purpose, monthly cost, free tier details, when to upgrade
   - n8n Cloud Starter: $24/mo (5K executions)
   - Clay Explorer: $314/mo (or skip if budget-tight — use manual research)
   - Apollo.io Free: $0 (275M contacts, 250 emails/mo)
   - Instantly.ai Growth: $37/mo (unlimited accounts, 5K leads)
   - HubSpot CRM Free: $0 (unlimited contacts)
   - OpenAI API: $30-50/mo (for email generation)
   - LinkedIn Sales Nav: $100/mo (optional but recommended)
   - Total: ~$505-525/mo

2. Budget Tiers:
   - Minimal ($61/mo): n8n + Instantly.ai + free tools only. Manual research.
   - Standard ($505/mo): Full stack as designed.
   - Premium ($800/mo): Add Clay Pro + Sales Nav + ZeroBounce

3. Comparison vs. Alternatives:
   - vs. AI SDR platforms (11x, Artisan): $40-60K/year
   - vs. Full-time SDR hire: $80-120K/year + benefits
   - vs. This project: ~$6K/year

4. Cost Per Meeting Analysis:
   At different activity levels and conversion rates.

### docs/results-framework.md

1. Metrics Definitions:
   Every metric, how it's calculated, what tools provide the data

2. Targets:
   Month 1, Month 3, Month 6 targets (from spec)

3. Benchmarks:
   Industry averages for cold outbound to technical buyers

4. Reporting Cadence:
   Daily (Slack digest), Weekly (Google Sheets report), Monthly (trend analysis)

5. How to Diagnose Problems:
   - Low signal count → Expand search queries, add new sources
   - Low qualification rate → Revisit ICP scoring rubric
   - Low reply rate → A/B test messaging, check deliverability
   - Low meeting rate → Improve CTA, check follow-up timing

Commit:
git add docs/cost-analysis.md docs/results-framework.md
git commit -m "docs: add cost analysis and results measurement framework"
```

---

## Phase 8: README and Polish

**Why this phase exists:** The README is the front door. It determines whether someone stars the repo, installs it, or bounces. It needs to be compelling, clear, and demonstrate the full system in under 2 minutes of reading.

---

### Task 8.1: Write Comprehensive README

**Files:**
- Update: `README.md` (replace skeleton with full README)

**Prompt:**
```
You are writing the comprehensive README for rl-gtm-engine.

SKILLS TO USE:
- coding-standards — Follow documentation best practices

CONTEXT:
- Read ALL files in the project — you need to accurately describe what exists
- Read docs/architecture.md for the system overview
- Read docs/cost-analysis.md for the cost comparison
- Read .agents/gtm-context.md for the ICP context
- This README needs to work for TWO audiences:
  1. GTM engineers who want to install and use the tool
  2. Hiring managers evaluating this as a portfolio project

WHAT TO BUILD:

Update README.md with:

1. Header:
   # rl-gtm-engine
   > A Signal-Based Outbound Engine for RL Infrastructure

   Built with Claude Code Skills, n8n, and Clay.

2. The Problem (3-4 sentences):
   Why traditional outbound fails for technical products sold to tiny markets.

3. The Solution (3-4 sentences):
   Signal-based detection + technically credible outreach.

4. Architecture Diagram:
   Text-based (ASCII or Mermaid) showing the three layers and data flow.

5. What's Included:
   Table of all skills, scripts, and workflows with one-line descriptions.

6. Quick Start:
   5-step installation (clone, install, configure, test, run first scan)

7. Skills Reference:
   Brief description of each skill with example invocation.

8. Cost:
   Summary table + comparison to alternatives.

9. Results:
   Target metrics and benchmarks.

10. Contributing:
    How to add new signal sources or skills.

11. License: MIT

Do NOT include anything about Collinear AI specifically in the README — keep it generic
so any GTM engineer can use it. The Collinear-specific content lives in .agents/gtm-context.md
which users swap for their own company context.

Commit:
git add README.md
git commit -m "docs: write comprehensive README with architecture, quick start, and skills reference"
```

---

### Task 8.2: Run Tests, Lint, and Security Check

**Files:**
- Review: All Python files in `scripts/` and `tests/`

**Prompt:**
```
You are performing the test, lint, and security verification pass for rl-gtm-engine.

SKILLS TO USE:
- superpowers:verification-before-completion — Verify everything works before claiming done
- security-review — Check for security issues

WHAT TO DO:

1. Run full test suite:
   pytest --cov=scripts --cov-report=term-missing -v
   Verify: All tests pass, coverage ≥80% on all script modules.
   If any tests fail: fix them and re-run.

2. Run linter:
   ruff check . --fix
   ruff format .
   Verify: No errors.

3. Security check:
   - Grep for any hardcoded API keys, tokens, or secrets in all files
   - Verify .env is in .gitignore
   - Verify .env.example has no real values (only placeholder names)
   - Verify no personal data (real emails, real names) in test fixtures
   - Check scripts for command injection vulnerabilities (user input → shell commands)

4. Commit fixes:
   git add -A
   git commit -m "chore: fix lint errors and security issues from final review"
   (Only commit if changes were made)

VERIFICATION:
- pytest passes with >80% coverage on every script module
- ruff check shows 0 errors
- No secrets found in any tracked file
```

---

### Task 8.3: Review Skills, Templates, Documentation, and Final Cleanup

**Files:**
- Review: All files in `skills/`, `templates/`, `docs/`, `n8n-workflows/`

**Prompt:**
```
You are performing the documentation and skills review pass for rl-gtm-engine.

SKILLS TO USE:
- superpowers:requesting-code-review — Run a full review of all non-Python content

WHAT TO DO:

1. Check all skills (8 total):
   For each SKILL.md in skills/:
   - Verify frontmatter has name and description only (no extra fields)
   - Verify description starts with "Use when"
   - Verify word count <500: wc -w skills/*/SKILL.md
   - Verify all referenced file paths actually exist in the repo
   - Flag any skills that reference non-existent scripts or templates

2. Check all templates (6 total):
   For each template in templates/:
   - Verify all placeholders ({{variable}}) are documented in the template header
   - Verify email copy follows voice/tone rules from .agents/gtm-context.md
   - Verify no email exceeds 4 sentences in initial outreach

3. Check all n8n workflows (4 total):
   For each JSON in n8n-workflows/:
   - Verify it's valid JSON: python -c "import json; json.load(open('file.json'))"
   - Verify node connections reference valid node IDs

4. Check documentation:
   - README.md links point to files that actually exist
   - docs/setup-guide.md steps are in correct order (no step references a later step)
   - docs/architecture.md component table matches actual project structure
   - docs/cost-analysis.md numbers are internally consistent

5. Clean up:
   - Remove any .gitkeep files in directories that now have real files
   - Remove any leftover TODO comments that were addressed
   - Ensure consistent markdown formatting (headers, lists, code blocks)

6. Final commit:
   git add -A
   git commit -m "chore: final documentation review and cleanup"

7. Tag the release:
   git tag -a v0.1.0 -m "Initial release: 8 skills, 5 scanners, 4 n8n workflows"

VERIFICATION:
- git log --oneline shows clean commit history
- All skills have valid frontmatter
- All template placeholders are documented
- All n8n workflow JSONs parse successfully
- No broken links in documentation
```

---

## Appendix: Skill Usage Summary

Quick reference for which skills and agents to use during execution:

| Phase | Primary Skill | Supporting Skills/Agents |
|-------|--------------|------------------------|
| 0: Foundation | — | — |
| 1: Data Models | superpowers:test-driven-development | coding-standards |
| 2: Scanners | superpowers:test-driven-development | coding-standards, security-review |
| 3: Templates | — | — |
| 4: Skills | superpowers:writing-skills | superpowers:test-driven-development |
| 5: Additional Skills | superpowers:writing-skills | security-review |
| 6: n8n Workflows | — | — |
| 7: Documentation | — | — |
| 8: Polish | superpowers:verification-before-completion | superpowers:requesting-code-review, security-review |

**Execution method:** Use superpowers:subagent-driven-development to dispatch each task to a fresh subagent. The subagent gets the exact prompt from the task above plus any context files referenced.

## Appendix: Task Index

| Task | Name | Files Created | Dependencies |
|------|------|--------------|-------------|
| 0.1 | Initialize Repository | repo structure, .gitignore, pyproject.toml, LICENSE | — |
| 0.2 | CLAUDE.md | CLAUDE.md | 0.1 |
| 0.3 | GTM Context | .agents/gtm-context.md | 0.1 |
| 1.1 | Data Models | scripts/models.py, tests | 0.1 |
| 1.2 | API Client | scripts/config.py, scripts/api_client.py, tests | 1.1 |
| 2.1 | GitHub Scanner | scripts/github_rl_scanner.py, tests | 1.2 |
| 2.2 | ArXiv Monitor | scripts/arxiv_monitor.py, tests | 1.2 |
| 2.3 | HuggingFace Monitor | scripts/hf_model_monitor.py, tests | 1.2 |
| 2.4 | Signal Stacker | scripts/signal_stacker.py, tests | 2.1-2.3 |
| 2.5 | Job Posting Scanner | scripts/job_posting_scanner.py, tests | 1.2 |
| 2.6 | Funding Tracker | scripts/funding_tracker.py, tests | 1.2 |
| 3.1 | ICP Scoring Rubric | templates/scoring-rubrics/ | 0.3 |
| 3.2 | Email Templates | templates/email-sequences/ (6 files) | 0.3 |
| 4.1 | Signal Scanner Skill | skills/signal-scanner/SKILL.md | 2.1-2.6 |
| 4.2 | Prospect Researcher Skill | skills/prospect-researcher/SKILL.md | 3.1 |
| 4.3 | Contact Finder Skill | skills/contact-finder/SKILL.md | 0.3 |
| 4.4 | Email Writer Skill | skills/email-writer/SKILL.md | 3.2 |
| 4.5 | Pipeline Tracker Skill | skills/pipeline-tracker/SKILL.md | 0.3 |
| 5.1 | Deliverability Manager Skill | skills/deliverability-manager/SKILL.md | — |
| 5.2 | Champion Tracker Skill | skills/champion-tracker/SKILL.md | 4.2 |
| 5.3 | Compliance Manager Skill | skills/compliance-manager/SKILL.md | — |
| 6.1 | Daily Signal Scan Workflow | n8n-workflows/daily-signal-scan.json | 2.1-2.6 |
| 6.2 | Enrichment Pipeline Workflow | n8n-workflows/enrichment-pipeline.json | 6.1, 4.3 |
| 6.3 | Sequence Launcher Workflow | n8n-workflows/sequence-launcher.json | 6.2, 4.4 |
| 6.4 | CRM Sync Workflow | n8n-workflows/crm-sync.json | 4.5 |
| 7.1 | Architecture Docs | docs/architecture.md | all above |
| 7.2 | Setup Guide | docs/setup-guide.md | all above |
| 7.3 | Cost & Results Docs | docs/cost-analysis.md, docs/results-framework.md | — |
| 8.1 | README | README.md | all above |
| 8.2 | Tests, Lint, Security | — (review only) | all above |
| 8.3 | Skills, Docs, Cleanup | — (review only) | 8.2 |

## Appendix: Dependency Graph

```
Phase 0 (Foundation: Tasks 0.1-0.3)
  └── Phase 1 (Data Models: Tasks 1.1-1.2)
       ├── Phase 2 (Scanners: Tasks 2.1-2.6) ────┐
       │                                          │
       └── Phase 3 (Templates: Tasks 3.1-3.2) ──┐│
                                                 ││
                                                 ▼▼
                              Phase 4 (Core Skills: Tasks 4.1-4.5)
                                   │
                                   ▼
                          Phase 5 (Additional Skills: Tasks 5.1-5.3)
                                   │
                                   ▼
                          Phase 6 (n8n Workflows: Tasks 6.1-6.4)
                                   │
                                   ▼
                          Phase 7 (Documentation: Tasks 7.1-7.3)
                                   │
                                   ▼
                          Phase 8 (Polish & Ship: Tasks 8.1-8.3)
```

**Parallelizable work:**
- Phases 2 and 3 can run in parallel (no dependencies between them)
- Tasks 2.1, 2.2, 2.3, 2.5, 2.6 can run in parallel (all depend only on 1.2)
- Tasks 5.1 and 5.3 can run in parallel (no dependencies on each other)
- Phase 4 depends on both Phases 2 and 3
- Everything else is sequential
