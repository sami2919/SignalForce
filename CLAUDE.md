# SignalForce

## Project Overview

SignalForce is an open-source collection of Claude Code agent skills and n8n workflows for signal-based outbound sales targeting reinforcement learning infrastructure buyers.

**Three-layer architecture:**
- **Skills** (`skills/*/SKILL.md`) — Claude Code instruction files. The primary user interface. Each skill tells Claude how to perform a GTM task.
- **Scripts** (`scripts/*.py`) — Python modules that hit external APIs (GitHub, Semantic Scholar, HF Hub, etc.). Skills invoke these as tools.
- **n8n Workflows** (`n8n-workflows/*.json`) — Scheduled automation that runs autonomously (daily signal scans, enrichment pipelines, CRM sync).

## Directory Structure

```
.agents/          — Shared context files loaded by all skills (ICP, voice, positioning)
skills/           — Claude Code SKILL.md files (8 skills)
scripts/          — Python modules for API interactions and data processing
n8n-workflows/    — JSON workflow definitions for n8n automation
templates/        — Reusable email sequences and scoring rubrics
docs/             — Architecture, setup guide, cost analysis, results framework
tests/            — pytest test suite (unit + integration)
tasks/            — Current work tracking (todo.md, lessons.md)
```

## Conventions

### Python
- **Pydantic models** for all data structures (`scripts/models.py`). Never use raw dicts for structured data.
- **Type hints** required on all function signatures.
- **Ruff** for formatting and linting (line-length 100, target Python 3.11).
- **Immutability**: All Pydantic models use `frozen=True`. Never mutate data — return new objects.
- Every script must be importable as a module AND runnable as CLI (`if __name__ == "__main__"`).

### Error Handling
- All API calls must handle rate limits (429/403), timeouts, and auth failures.
- Log errors with full context (URL, status code, response body).
- Never silently swallow errors.
- Fail fast: validate API keys at scan start, not mid-scan.

### Environment Variables
- All API keys loaded via `python-dotenv` from `.env`. Never hardcode secrets.
- `.env.example` documents all variables (no real values).
- `scripts/config.py` centralizes all config loading and validation.

### Skills
- Follow `superpowers:writing-skills` format. YAML frontmatter with `name` and `description` only.
- Description starts with "Use when..." and never summarizes the workflow.
- Under 500 words. Token-efficient.

### Testing
- **TDD required**: Write tests first (RED), implement (GREEN), refactor (IMPROVE).
- **pytest** with 80% minimum coverage.
- Mock all HTTP calls in tests — never hit real APIs.
- Test fixtures live in `tests/fixtures/`.

## Commands

```bash
# Run tests
pytest --cov=scripts --cov-report=term-missing -v

# Format
ruff format .

# Lint
ruff check . --fix

# Run a scanner
python -m scripts.github_rl_scanner --lookback-days 7 --output /tmp/signals.json

# Run signal stacker
python -m scripts.signal_stacker --inputs scan1.json scan2.json --output stacked.json
```

## Key Files

- `.agents/gtm-context.md` — ICP definitions, product positioning, voice/tone rules. Loaded by all skills.
- `scripts/models.py` — Pydantic data models (Signal, CompanyProfile, Contact, Deal, etc.)
- `scripts/config.py` — Environment variable loading and validation
- `scripts/api_client.py` — Base API client with retry/rate-limit handling
- `templates/scoring-rubrics/icp-scoring-model.md` — Weighted ICP scoring criteria

## External APIs

| API | Purpose | Key Required |
|-----|---------|-------------|
| GitHub API | RL repo detection | Yes (GITHUB_TOKEN) |
| Semantic Scholar | RL paper tracking | Optional (rate limited without) |
| Hugging Face Hub | RL model uploads | No (public API) |
| Apollo.io | Contact enrichment | Yes |
| Hunter.io | Email pattern lookup | Yes |
| Prospeo | LinkedIn email enrichment | Yes |
| Instantly.ai | Cold email sequencing | Yes |
| HubSpot | CRM pipeline | Yes |
| ZeroBounce | Email validation | Yes |

---

# Bookkeeping

## Workflow Orchestration

### 1. Plan Mode Default
- Enter plan mode for ANY non-trivial task (3+ steps or architectural decisions)
- If something goes sideways, STOP and re-plan immediately -- don't keep pushing
- Use plan mode for verification steps, not just building
- Write detailed specs upfront to reduce ambiguity

### 2. Subagent Strategy
- Use subagents liberally to keep main context window clean
- Offload research, exploration, and parallel analysis to subagents
- For complex problems, throw more compute at it via subagents
- One task per subagent for focused execution

### 3. Self-Improvement Loop
- After ANY correction from the user: update `tasks/lessons.md` with the pattern
- Write rules for yourself that prevent the same mistake
- Ruthlessly iterate on these lessons until mistake rate drops
- Review lessons at session start for relevant project

### 4. Verification Before Done
- Never mark a task complete without proving it works
- Diff behavior between main and your changes when relevant
- Ask yourself: "Would a staff engineer approve this?"
- Run tests, check logs, demonstrate correctness

### 5. Demand Elegance (Balanced)
- For non-trivial changes: pause and ask "is there a more elegant way?"
- If a fix feels hacky: "Knowing everything I know now, implement the elegant solution"
- Skip this for simple, obvious fixes -- don't over-engineer
- Challenge your own work before presenting it

### 6. Autonomous Bug Fixing
- When given a bug report: just fix it. Don't ask for hand-holding
- Point at logs, errors, failing tests -- then resolve them
- Zero context switching required from the user
- Go fix failing CI tests without being told how

## Task Management

1. **Plan First**: Write plan to `tasks/todo.md` with checkable items
2. **Verify Plan**: Check in before starting implementation
3. **Track Progress**: Mark items complete as you go
4. **Explain Changes**: High-level summary at each step
5. **Document Results**: Add review section to `tasks/todo.md`
6. **Capture Lessons**: Update `tasks/lessons.md` after corrections

## Core Principles

- **Simplicity First**: Make every change as simple as possible. Impact minimal code.
- **No Laziness**: Find root causes. No temporary fixes. Senior developer standards.
- **Minimal Impact**: Changes should only touch what's necessary. Avoid introducing bugs.
