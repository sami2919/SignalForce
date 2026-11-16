# Magic / Loyalist GTM Demo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build, on SignalForce and public data only, a working NYC demo for Magic. It must find
restaurant groups in a buying window, score them with explainable traces, prove recall and
beat plain Claude in a head-to-head, then produce contacts, grounded drafts and an event
meeting list.

**Architecture:** A new package `scripts/hospitality/` holds frozen Pydantic domain models
persisted in a small SQLite document store. Pipeline: deterministic ingest (NY SLA + NYC DOHMH
via Socrata) → entity resolution (rules + fuzzy names + distance) → buying-window survival
curve → stack crawl with fingerprints (reusing `scripts/watch/fetcher.fetch_all`) → noisy-OR
scoring with traces → measurement (recall audit, case-replay backtest, head-to-head vs plain
Claude). Paid tools (Google Places, Firecrawl, Exa, Hunter, Clay, Claude) sit behind small
clients with hard per-run budgets.

**Tech Stack:** Python 3.11, Pydantic v2, SQLAlchemy (SQLite), httpx/requests (existing clients),
selectolax (already a dependency), rapidfuzz (new), anthropic SDK, pytest.

**Spec:** `docs/superpowers/specs/2026-11-16-magic-loyalist-gtm-system-design.md`. Research
backing the signal priors: `docs/research/magic/01–04`.

---

## Concerns and better ways (read first)

These are the places where I think the spec, the timebox or the data push against each other.
Each has my recommendation. The plan follows the recommendation unless you say otherwise.

1. **The timebox is tight for this scope.** 30 tasks with TDD don't fit in 2–3 days.
   **Recommendation:** build P0 (Tasks 1–17) with full rigor. Build P1 (Tasks 18–26) as time
   allows. Defer P2 (Tasks 27–30, simulated outbound and learning-loop modules) until after the
   meeting. In the meeting those are better shown as the design doc's diagrams. A simulation
   running on fake outcomes proves little, and building it costs P0 time.
2. **Storage deviates from the spec's "extend `scripts/storage`".** The spec also says "an
   isolated database". Adding ~12 Postgres tables and Alembic migrations to the shared
   multi-tenant schema for a demo is slow and risky.
   **Recommendation (used here):** a separate SQLite document store inside
   `scripts/hospitality/`. Each kind of record is a table of `(id, json)` rows validated through
   frozen Pydantic models. It swaps to Postgres later by changing the URL, and typed tables can
   come once the model settles.
3. **Venue websites aren't in the public datasets.** SLA and DOHMH have no URLs, and the stack
   crawl, embed detection, contacts and lookalikes all need one.
   **Recommendation:** Google Places Text Search with a field mask, limited to the top ~400
   ranked venues plus all seed customers. `websiteUri` bills at a higher Places tier with a
   small free monthly allowance, and the budget guard enforces it. Exa or Firecrawl search is the
   fallback for misses.
4. **Restaurant groups are mostly invisible in public records.** Each venue usually has its own
   LLC, so the SLA legal name rarely reveals the group. Exact legal-name and shared-domain rules
   catch only part of it.
   **Recommendation:** group-of-one by default. Merge from website "locations"/footer pages
   (Firecrawl extract) and press for the top accounts, and say plainly in the demo that group
   counts are a lower bound. This is the "wrong location counts" problem Magic names, so it's a
   good talking point, not a weakness to hide.
5. **History only has license *issue* dates.** Pending applications vanish once licensed. The
   timing curve therefore measures issue → first inspection. For pending applications the plan
   needs a prior for application → issue (`pending_to_issue_prior_days: 75`, an assumption). The
   daily pending snapshot (Task 4) replaces that prior with measured data over the following
   weeks. Start it on day one.
6. **The backtest has to be honest.** Scoring today's existing customers on today's opening
   signals is meaningless; they bought long ago. **Recommendation (used here):** two tests.
   - **Case replay:** for dated customers whose new venue appears in the license data (Oriana,
     Massara, Bar Kabawa, La Tête d'Or, etc.), did a license signal fire before their Loyalist
     date, and how early?
   - **Fit-only static AUC:** do customers rank above the universe on Fit?

   Neither is a lift claim, and the report labels both as indicative.
7. **The head-to-head can't compare lead time.** At a fixed cutoff both lists are dated the
   same day. It can compare hits, precision@k, duplicates, non-venues and run-to-run variance.
   Lead time belongs to the recall audit. The hindsight leak favors Claude, so state that a win
   is conservative.
8. **Model choice and cost.** The Claude API guidance defaults every call to `claude-opus-5-5`
   ($4/$20 per M tokens), and the plan uses that everywhere. Bulk extraction (press, team pages,
   event lineups) on `claude-haiku-5-5` ($0.10/$0.50) would cost ~40× less. That trade is yours
   to make; it's a one-line config change (`models.extract`). The plan also turns on server-side
   refusal fallbacks (`fallbacks: "default"`) on Opus 5.5 calls, per the API guidance.
9. **Clay round-trip.** Pushing rows into a Clay table by webhook is simple. Getting results
   back automatically needs a Clay HTTP action calling an endpoint we'd have to host.
   **Recommendation:** for the demo, push by webhook and pull back by CSV export plus an import
   command. Automate it after the meeting.
10. **Sensitive output.** The demo produces a list of Magic's customers detected from their own
    embeds. Showing it *to Magic* is fine. Never publish it, commit it, or share it elsewhere.
    The report goes under `out/` (gitignored), not `docs/`.

---

## Global Constraints

- Python 3.11; ruff line length 100; type hints on every signature.
- Every data structure is a Pydantic model with `frozen=True`; never mutate, return new objects.
- Every module is importable; every pipeline step is runnable via `python -m scripts.hospitality.cli <command>`.
- Tests mock all HTTP (no real network in tests); fixtures in `tests/fixtures/hospitality/`; overall coverage stays ≥ 80%.
- API keys come from env vars only: `ANTHROPIC_API_KEY`, `GOOGLE_PLACES_API_KEY`, `FIRECRAWL_API_KEY`, `EXA_API_KEY`, `HUNTER_API_KEY`, `CLAY_WEBHOOK_URL`, optional `SOCRATA_APP_TOKEN`. Validate the keys a command needs at its start (fail fast).
- Every paid client enforces a hard per-run call budget from config and stops (raises `BudgetExceeded`) when it is spent.
- Respect robots.txt (existing fetcher does). Never fetch `loyalist.com/for/`. No LinkedIn scraping. No gated event apps.
- No real outbound email. Drafts only.
- Data files and reports go under `data/magic/` and `out/magic/`. Both are gitignored, and the Loyalist-customer outputs never leave them.
- Claude model: `claude-opus-5-5` for all calls (configurable per role in `models.*`), adaptive thinking, structured outputs via `messages.parse`.
- Datasets: SLA pending `f8i8-k2gm`, SLA active `9s3h-dpkz`, SLA inactive `6dg3-2z7i` on `data.ny.gov`; DOHMH inspections `43nn-pn8j` on `data.cityofnewyork.us`.
- NYC counties: `New York`, `Kings`, `Queens`, `Bronx`, `Richmond`.

## Review Focus

1. **Schema drift between Socrata datasets.** Pending uses `premises_county`/`received_date`; active uses `premisescounty`/`originalissuedate`. One parser must handle both, and an unknown row must be skipped and logged, never crash. Pinned in Task 3.
2. **DOHMH sentinel and re-opened sites.** `1900-01-01` means "not yet inspected", not a date. A license issued *after* a site's first inspection is a transfer or renewal, not a new opening, and must be excluded from the timing curve and the recall truth set. Pinned in Tasks 5 and 9.
3. **Widget false positives.** A page that merely *says* "Resy" or "Tock" in text, or a theme-demo snippet, must not count as a platform. Detection reads only link/script/form attributes and script bodies. Pinned in Task 11.
4. **Existing customers leaking into prospect lists.** A group with a detected Loyalist embed or a seed label must never appear in the prospect ranking, drafts or meeting targets as a cold target. It appears only as a customer (expansion / warm intro). Pinned in Tasks 13 and 25.
5. **Paid API overspend and fabricated LLM output.** Budgets must hard-stop. LLM outputs that cite unknown evidence IDs, or name venues that don't exist, must be caught deterministically, not just by an LLM judge. Pinned in Tasks 10, 16 and 23.

---

## File structure

```
scripts/hospitality/
  __init__.py
  models.py              # all frozen domain models (single source of types)
  config.py              # HospitalityConfig loader (YAML → frozen model)
  store.py               # SQLite document store
  budget.py              # BudgetExceeded + CallBudget
  llm.py                 # one structured-output helper for every Claude call
  sources/socrata.py     # paging Socrata client
  sources/sla.py         # SLA pending/active/inactive → LicenseRecord
  sources/dohmh.py       # DOHMH → InspectionVenue (aggregated server-side)
  sources/snapshot.py    # daily pending snapshots → first-seen dates
  resolve/normalize.py   # names, addresses, haversine
  resolve/match.py       # license ↔ inspection matching, possibly-same links
  resolve/venues.py      # build Venue records from matches
  resolve/groups.py      # group formation + merging from evidence
  window/survival.py     # Kaplan–Meier
  window/estimate.py     # opening curves + per-venue window estimate
  stack/websites.py      # Google Places website lookup
  stack/fingerprints.py  # platform fingerprints + detection
  stack/crawl.py         # crawl + Firecrawl fallback → StackObservation
  stack/signals.py       # stack observations → signals, disqualifiers
  labels.py              # customer labels (seed + embed)
  signals.py             # license/inspection → signals
  scoring.py             # priors, window weight, noisy-OR, fit, priority, trace
  measure/recall.py      # recall audit
  measure/backtest.py    # case replay + fit AUC
  benchmark/baseline.py  # plain-Claude baseline runs
  benchmark/compare.py   # head-to-head metrics
  discover/exa.py        # Exa client
  discover/press.py      # press search + extraction → signals, new venues, group evidence
  discover/lookalikes.py # findSimilar from customer seeds
  contacts/waterfall.py  # team page → Hunter
  contacts/clay.py       # Clay webhook push + CSV import
  messages/drafter.py    # evidence-linked drafts
  messages/judge.py      # grounding check + LLM judge
  events/registry.py     # Event registry loader
  events/extract.py      # lineup/speaker pages → appearances
  events/rank.py         # event ranking + meeting lists
  report.py              # demo report (markdown)
  cli.py                 # all commands
  outbound/sequencer.py  # P2
  outbound/replies.py    # P2
  loop/updates.py        # P2
examples/magic-loyalist/
  hospitality.yaml       # priors, thresholds, budgets, models
  customers_seed.yaml    # public customer list with dates + sources
  events.yaml            # NYC-relevant event registry
tests/hospitality/       # mirrors the package; fixtures in tests/fixtures/hospitality/
```

*Why this shape:* one file per responsibility, grouped by pipeline stage, so each task touches
one folder. `models.py` is the single type source, so every later task's Interfaces block
points at it instead of redefining shapes.

---

# P0: Day 1. Foundation, ingest, resolution, timing

### Task 1: Domain models

**Files:**
- Create: `scripts/hospitality/__init__.py`, `scripts/hospitality/models.py`
- Test: `tests/hospitality/__init__.py`, `tests/hospitality/test_models.py`

**Rationale.**
- *Purpose:* define every shape the pipeline passes around, in one place.
- *Why it matters:* 30 tasks share these types. A mismatch (e.g. `venue_id` vs `id`) is the most
  likely integration bug.
- *Why this way:* frozen Pydantic matches the repo convention and makes records hashable and
  safe to share. Alternatives: dataclasses (no validation) or SQLAlchemy models as the domain
  (ties logic to storage, harder to test).

**Interfaces:**
- Produces (all `BaseModel, frozen=True`):
  - `LicenseSource = Literal["sla_pending","sla_active","sla_inactive"]`
  - `LicenseRecord(source: LicenseSource, record_id: str, legal_name: str, dba: str, address: str, city: str, zip_code: str, county: str, license_class: str, description: str, received_date: date | None, original_issue_date: date | None, lat: float | None, lon: float | None)`
  - `InspectionVenue(camis: str, dba: str, boro: str, address: str, zip_code: str, cuisine: str, phone: str, lat: float | None, lon: float | None, first_inspection_date: date | None, first_inspection_type: str | None)`
  - `Venue(venue_id: str, name: str, address: str, zip_code: str, lat: float | None, lon: float | None, camis: str | None, license_ids: tuple[str, ...], license_class: str | None, license_description: str | None, first_inspection_date: date | None, website: str | None, group_id: str)`
  - `GroupResolution = Literal["singleton","shared_legal_name","shared_domain","website_locations","press","agent","manual"]`
  - `Group(group_id: str, name: str, venue_ids: tuple[str, ...], resolution: GroupResolution)`
  - `EntityLink(left_id: str, right_id: str, kind: Literal["possibly_same"], probability: float, method: str)`
  - `SignalType = Literal["license_pending","license_issued","not_yet_inspected","press_opening","stack_fragmented","private_events","tripleseat_resy","hotel_partnership","role_hire","new_gm","platform_switch","alumni_edge","lookalike"]`
  - `Signal(signal_id: str, signal_type: SignalType, entity_id: str, observed_at: datetime, occurred_at: datetime | None, source: str, evidence_ref: str, detail: str)`. `entity_id` is a `venue_id` or `group_id`; `detail` is a short human-readable string.
  - `StackObservation(venue_id: str, url: str, observed_at: datetime, platforms: tuple[str, ...], evidence: tuple[str, ...], fetched_via: Literal["fetcher","firecrawl"])`
  - `WindowEstimate(venue_id: str, estimated_open: date, p_open_90d: float, p_open_180d: float, basis: str)`
  - `CustomerLabel(name: str, website_domain: str | None, first_public_date: date | None, source: Literal["public_list","embed"], evidence_ref: str)`
  - `Contribution(signal_id: str, signal_type: str, precision: float, weight: float, contribution: float)`
  - `ScoredAccount(group_id: str, p_window: float, fit: float, relationship: float, priority: float, contributions: tuple[Contribution, ...], disqualified_reason: str | None, is_customer: bool)`
  - `Contact(contact_id: str, group_id: str, name: str, role: str, email: str | None, email_confidence: float | None, instagram: str | None, phone: str | None, source: str, evidence_ref: str)`

- [ ] **Step 1: Write failing tests.** *Why: pin immutability and the one non-obvious rule (probabilities in [0,1]) before anything depends on them.*

```python
def test_signal_is_frozen():
    s = Signal(signal_id="s1", signal_type="license_pending", entity_id="v:1",
               observed_at=datetime(2026, 11, 1, tzinfo=UTC), occurred_at=None,
               source="sla_pending", evidence_ref="sla:123", detail="pending")
    with pytest.raises(ValidationError):
        s.detail = "x"

def test_entity_link_probability_bounds():
    with pytest.raises(ValidationError):
        EntityLink(left_id="a", right_id="b", kind="possibly_same", probability=1.2, method="m")

def test_scored_account_roundtrips_json():
    acc = ScoredAccount(group_id="g:1", p_window=0.5, fit=0.4, relationship=1.0, priority=0.35,
                        contributions=(), disqualified_reason=None, is_customer=False)
    assert ScoredAccount.model_validate_json(acc.model_dump_json()) == acc
```

- [ ] **Step 2: Run, expect FAIL.** `pytest tests/hospitality/test_models.py -v` → ImportError.
- [ ] **Step 3: Implement the models above in `models.py`.** Probability fields (`probability`, `p_window`, `p_open_90d`, `p_open_180d`, `fit`) use `Field(ge=0, le=1)`. *Why: bounds are cheap to enforce here and catch scoring bugs immediately.*
- [ ] **Step 4: Run, expect PASS.**
- [ ] **Step 5: Commit.** `git commit -m "feat(hospitality): add frozen domain models"`

---

### Task 2: Config, document store, budgets, LLM helper

**Files:**
- Create: `scripts/hospitality/config.py`, `store.py`, `budget.py`, `llm.py`, `examples/magic-loyalist/hospitality.yaml`
- Modify: `.gitignore` (add `data/magic/`, `out/magic/`)
- Test: `tests/hospitality/test_config.py`, `test_store.py`, `test_budget.py`, `test_llm.py`

**Rationale.**
- *Purpose:* shared plumbing every later task uses.
- *Why it matters:* priors, thresholds and budgets must be data, not code. The learning loop
  updates numbers, and you want to tune them live in the meeting.
- *Why this way:*
  - YAML + a frozen model mirrors the existing `config_loader` pattern.
  - SQLite document store (Concern 2).
  - One LLM helper, so model choice, thinking, fallbacks and cost logging live in one place
    instead of in eight call sites.

**Interfaces:**
- Produces:
  - `SignalPrior(precision: float, half_life_days: float | None, family: Literal["opening","stack","people","relationship","events","discovery"])`
  - `HospitalityConfig` fields:
    - `datasets: dict[str, str]`, `nyc_counties: tuple[str, ...]`
    - `on_premise_descriptions: tuple[str, ...]`
    - `priors: dict[str, SignalPrior]`
    - `window_pre_days: int`, `window_post_days: int`, `window_outside_half_life_days: float`
    - `pending_to_issue_prior_days: int`
    - `fit_weights: dict[str, float]`, `relationship_boost: float`
    - `budgets: dict[str, int]`, `models: dict[str, str]`
    - `match_max_distance_m: float`, `match_auto_threshold: float`, `match_link_threshold: float`
  - `load_config(path: Path = DEFAULT_CONFIG_PATH) -> HospitalityConfig`
  - `DocStore(url: str = "sqlite:///data/magic/magic.db")`:
    - `.save(kind: str, items: Sequence[BaseModel], key: Callable[[BaseModel], str]) -> int` (upsert)
    - `.load(kind: str, model: type[T]) -> list[T]`
    - `.clear(kind: str) -> None`
  - `class BudgetExceeded(RuntimeError)`
  - `CallBudget(name: str, limit: int)` with `.spend(n: int = 1) -> None` (raises `BudgetExceeded` once the limit is passed) and `.used: int`
  - `structured(model_cls: type[T], *, system: str, user: str, role: str = "extract", effort: str = "low", client: Anthropic | None = None) -> T`

- [ ] **Step 1: Write `hospitality.yaml` with these exact values.** *Why: these are the evidence-derived priors from spec §6.3; writing them first makes every later test reference real numbers.*

```yaml
datasets: {sla_pending: f8i8-k2gm, sla_active: 9s3h-dpkz, sla_inactive: 6dg3-2z7i, dohmh: 43nn-pn8j}
nyc_counties: [New York, Kings, Queens, Bronx, Richmond]
on_premise_descriptions: [Restaurant, Food & Beverage Business, Hotel, Catering Establishment, Summer Restaurant]
priors:   # precision = P(group in a buying window | signal); starting guesses the loop updates
  license_pending:   {precision: 0.30, half_life_days: null, family: opening}
  license_issued:    {precision: 0.30, half_life_days: null, family: opening}
  not_yet_inspected: {precision: 0.15, half_life_days: null, family: opening}
  press_opening:     {precision: 0.35, half_life_days: null, family: opening}
  stack_fragmented:  {precision: 0.25, half_life_days: null, family: stack}
  tripleseat_resy:   {precision: 0.25, half_life_days: null, family: stack}
  private_events:    {precision: 0.15, half_life_days: 120, family: events}
  hotel_partnership: {precision: 0.20, half_life_days: 180, family: opening}
  role_hire:         {precision: 0.15, half_life_days: 90, family: people}
  new_gm:            {precision: 0.15, half_life_days: 90, family: people}
  platform_switch:   {precision: 0.05, half_life_days: 90, family: stack}
  lookalike:         {precision: 0.10, half_life_days: null, family: discovery}
  alumni_edge:       {precision: 0.0, half_life_days: null, family: relationship}
window_pre_days: 183
window_post_days: 365
window_outside_half_life_days: 60
pending_to_issue_prior_days: 75
fit_weights: {multi_venue: 0.30, reservation_platform: 0.30, events_program: 0.15, accolade: 0.15, full_service_class: 0.10}
relationship_boost: 0.5
budgets: {places: 400, firecrawl: 300, exa: 120, hunter: 40, clay: 25, claude_calls: 600}
models: {extract: claude-opus-5-5, draft: claude-opus-5-5, judge: claude-opus-5-5, baseline: claude-opus-5-5}
match_max_distance_m: 40.0
match_auto_threshold: 0.90
match_link_threshold: 0.60
```

- [ ] **Step 2: Write failing tests.** *Why: these three behaviors (config loads, upsert is idempotent, budget hard-stops) are what every later task assumes.*

```python
def test_load_config_reads_priors():
    cfg = load_config(Path("examples/magic-loyalist/hospitality.yaml"))
    assert cfg.priors["license_pending"].precision == 0.30
    assert cfg.window_pre_days == 183

def test_docstore_upsert_is_idempotent(tmp_path):
    store = DocStore(f"sqlite:///{tmp_path}/t.db")
    rec = make_license("sla:1")  # helper in tests/hospitality/factories.py
    store.save("licenses", [rec, rec], key=lambda r: r.record_id)
    assert store.load("licenses", LicenseRecord) == [rec]

def test_budget_hard_stops():
    b = CallBudget("places", limit=2)
    b.spend(); b.spend()
    with pytest.raises(BudgetExceeded):
        b.spend()

def test_structured_calls_parse_with_configured_model(mocker):
    fake = mocker.Mock()
    fake.beta.messages.parse.return_value.parsed_output = Probe(ok=True)
    out = structured(Probe, system="s", user="u", client=fake)
    kwargs = fake.beta.messages.parse.call_args.kwargs
    assert out == Probe(ok=True)
    assert kwargs["model"] == "claude-opus-5-5"
    assert kwargs["fallbacks"] == "default"
```

- [ ] **Step 3: Run, expect FAIL.** `pytest tests/hospitality/test_config.py tests/hospitality/test_store.py tests/hospitality/test_budget.py tests/hospitality/test_llm.py -v`
- [ ] **Step 4: Implement.**
  - `DocStore` uses SQLAlchemy Core with one table per kind: `(id TEXT PRIMARY KEY, json TEXT, updated_at TEXT)`. Upsert via `INSERT … ON CONFLICT(id) DO UPDATE`.
  - `structured` calls `client.beta.messages.parse(model=cfg.models[role], max_tokens=16000, thinking={"type": "adaptive"}, output_config={"effort": effort}, betas=["server-side-fallback-2026-07-01"], fallbacks="default", system=..., messages=[...], output_format=model_cls)`.
    - It checks `stop_reason == "refusal"` and raises `LLMRefusal`.
    - It logs `usage`, including `cache_read_input_tokens`.
    - It spends the `claude_calls` budget.
    - **Verification sub-step:** confirm that `beta.messages.parse` accepts `fallbacks` in the installed SDK. If it doesn't, use `client.messages.parse` without fallbacks and record that in the module docstring. *Why: the API guidance mandates fallbacks on Opus 5.5, but SDK surfaces drift; a guess here breaks every LLM task.*
- [ ] **Step 5: Run, expect PASS.**
- [ ] **Step 6: Commit.** `git commit -m "feat(hospitality): config, sqlite doc store, budgets, structured LLM helper"`

---

### Task 3: Socrata client + SLA license ingest

**Files:**
- Create: `scripts/hospitality/sources/__init__.py`, `sources/socrata.py`, `sources/sla.py`
- Test: `tests/hospitality/test_sla.py`; fixtures `tests/fixtures/hospitality/sla_pending_rows.json`, `sla_active_rows.json`

**Rationale.**
- *Purpose:* pull the earliest public evidence of an opening, the liquor license.
- *Why it matters:* the "one venue → several" transition (5/9 and 6/10 customers) is first
  visible here, weeks to months before press.
- *Why this way:* Socrata's SoQL lets us filter to NYC counties server-side, which is free,
  fast and deterministic. Alternatives: bulk CSV downloads (the statewide files are large and
  need local filtering) or scraping the SLA website (fragile, and pointless when an API exists).

**Interfaces:**
- Consumes: `LicenseRecord`, `HospitalityConfig`, `scripts.api_client.BaseAPIClient`
- Produces:
  - `SocrataClient(domain: str, app_token: str | None = None)` with `.rows(dataset_id: str, *, where: str | None = None, select: str | None = None, group: str | None = None, page_size: int = 50000) -> Iterator[dict]`. It pages with `$limit`/`$offset` and `$order=:id`.
  - `parse_license_row(row: dict, source: LicenseSource) -> LicenseRecord | None`
  - `fetch_licenses(client: SocrataClient, cfg: HospitalityConfig, source: LicenseSource) -> list[LicenseRecord]`

- [ ] **Step 1: Save two real-shaped fixture rows per dataset** (copied from the live API; one pending row, one active row). *Why: tests must exercise the real field names, which differ between datasets (Review Focus 1).*
- [ ] **Step 2: Write failing tests.**

```python
def test_parse_pending_row_uses_snake_case_fields():
    rec = parse_license_row(load_fixture("sla_pending_rows.json")[0], "sla_pending")
    assert rec.source == "sla_pending"
    assert rec.received_date is not None and rec.original_issue_date is None
    assert rec.county == "New York"

def test_parse_active_row_uses_squashed_fields():
    rec = parse_license_row(load_fixture("sla_active_rows.json")[0], "sla_active")
    assert rec.original_issue_date is not None
    assert rec.record_id.startswith("sla_active:")

def test_parse_unknown_row_returns_none_and_logs(caplog):
    assert parse_license_row({"foo": "bar"}, "sla_active") is None
    assert "unparseable SLA row" in caplog.text

def test_fetch_licenses_filters_to_nyc(mocker):
    client = mocker.Mock(rows=mocker.Mock(return_value=iter(load_fixture("sla_active_rows.json"))))
    fetch_licenses(client, load_config(), "sla_active")
    where = client.rows.call_args.kwargs["where"]
    assert "premisescounty in(" in where and "'Kings'" in where
```

- [ ] **Step 3: Run, expect FAIL.**
- [ ] **Step 4: Implement.**
  - `record_id = f"{source}:{application_id or license_permit_id}"`.
  - Dates are parsed from ISO strings to `date`.
  - `lat`/`lon` come from `georeference.coordinates`, which is `[lon, lat]`. Note the order.
  - The county field name is chosen per source.
  - `SocrataClient` subclasses `BaseAPIClient` for retry and 429 handling. If `BaseAPIClient.get` assumes a dict response, add `get_list` there rather than in Socrata. *Why: Socrata returns JSON arrays; fix the base once, don't fork the retry logic.*
- [ ] **Step 5: Run, expect PASS.**
- [ ] **Step 6: Add CLI `ingest-sla`** (fetches all three sources and saves them to the `licenses` kind). Run it live once: `python -m scripts.hospitality.cli ingest-sla`. Expect a printed count per source; the pending NYC count should be in the hundreds. *Why: real data early exposes schema surprises while there's time to fix them.*
- [ ] **Step 7: Commit.** `git commit -m "feat(hospitality): ingest NY SLA licenses via Socrata"`

---

### Task 4: Daily pending snapshots

**Files:**
- Create: `scripts/hospitality/sources/snapshot.py`
- Test: `tests/hospitality/test_snapshot.py`

**Rationale.**
- *Purpose:* record each pending application on the day we first see it.
- *Why it matters:* this is the only way to measure true application → opening lead time
  (Concern 5), and every day not snapshotting is lost history.
- *Why this way:* append-only rows keyed `(date, application_id)` are trivial and auditable.
  Alternative: diffing full dumps later, which needs the dumps we aren't keeping.

**Interfaces:**
- Consumes: `LicenseRecord`, `DocStore`
- Produces:
  - `PendingSnapshot(taken_on: date, record_id: str)`, frozen; add it to `models.py`.
  - `take_snapshot(store: DocStore, pending: Sequence[LicenseRecord], taken_on: date) -> int`
  - `first_seen_pending(store: DocStore) -> dict[str, date]`

- [ ] **Step 1: Failing test.**

```python
def test_first_seen_is_earliest_snapshot(tmp_store):
    a = make_license("sla_pending:1", source="sla_pending")
    take_snapshot(tmp_store, [a], date(2026, 11, 16))
    take_snapshot(tmp_store, [a], date(2026, 11, 17))
    assert first_seen_pending(tmp_store) == {"sla_pending:1": date(2026, 11, 16)}
```

- [ ] **Step 2: Run, expect FAIL. Step 3: Implement** with key `f"{taken_on}:{record_id}"`. **Step 4: PASS.**
- [ ] **Step 5: CLI `snapshot-pending`, run it today.** Document in the module docstring: "Schedule daily (Fly worker or cron) after the demo." *Why: start the clock now; automating the schedule can wait.*
- [ ] **Step 6: Commit.** `git commit -m "feat(hospitality): daily SLA pending snapshots"`

---

### Task 5: DOHMH ingest (server-side aggregated)

**Files:**
- Create: `scripts/hospitality/sources/dohmh.py`
- Test: `tests/hospitality/test_dohmh.py`; fixtures `dohmh_first_inspections.json`, `dohmh_never_inspected.json`

**Rationale.**
- *Purpose:* get, for every NYC food venue, a stable ID (CAMIS) and its *first* inspection
  date, which stands in for "opened".
- *Why it matters:* this is the ground truth for the recall audit and the timing curve.
- *Why this way:* two aggregated SoQL queries return about one row per venue instead of
  hundreds of thousands of inspection rows:
  - `min(inspection_date)` grouped by venue, excluding the sentinel date;
  - venues whose only date is the sentinel.

  Alternative: pull everything and group locally (slow, memory-heavy, no benefit).

**Interfaces:**
- Consumes: `SocrataClient`, `InspectionVenue`
- Produces:
  - `fetch_first_inspections(client: SocrataClient) -> list[InspectionVenue]`. Query: `$select=camis,dba,boro,building,street,zipcode,cuisine_description,phone,latitude,longitude,min(inspection_date) as first_date`, `$where=inspection_date > '1900-01-02'`, `$group=camis,dba,boro,building,street,zipcode,cuisine_description,phone,latitude,longitude`.
  - `fetch_never_inspected(client: SocrataClient) -> list[InspectionVenue]`. These have `first_inspection_date=None`.
  - `parse_inspection_row(row: dict) -> InspectionVenue | None`
  - `merge_inspection_venues(first: Sequence[InspectionVenue], never: Sequence[InspectionVenue]) -> list[InspectionVenue]`. CAMIS is unique; a dated record wins over a never-inspected one.

- [ ] **Step 1: Failing tests.**

```python
def test_sentinel_date_becomes_none():
    v = parse_inspection_row({"camis": "1", "dba": "X", "boro": "Manhattan", "building": "1",
                              "street": "BLEECKER ST", "zipcode": "10012",
                              "first_date": "1900-01-01T00:00:00.000"})
    assert v.first_inspection_date is None

def test_dated_record_wins_on_merge():
    dated = make_inspection("1", first=date(2026, 9, 1))
    never = make_inspection("1", first=None)
    assert merge_inspection_venues([dated], [never]) == [dated]

def test_address_is_building_plus_street():
    v = parse_inspection_row({"camis": "2", "dba": "Y", "boro": "Brooklyn", "building": "289",
                              "street": "BLEECKER STREET", "zipcode": "10014",
                              "first_date": "2026-01-05T00:00:00.000"})
    assert v.address == "289 BLEECKER STREET"
```

- [ ] **Step 2: FAIL. Step 3: Implement. Step 4: PASS.**
- [ ] **Step 5: CLI `ingest-dohmh`, run it live.** Expect roughly 25–30k venues, ~4k of them never inspected (we measured 4,059 on 2026-11-16).
- [ ] **Step 6: Commit.** `git commit -m "feat(hospitality): ingest DOHMH first-inspection venues"`

---

### Task 6: Normalization primitives

**Files:**
- Create: `scripts/hospitality/resolve/__init__.py`, `resolve/normalize.py`
- Test: `tests/hospitality/test_normalize.py`
- Modify: `pyproject.toml` (add `rapidfuzz>=3`)

**Rationale.**
- *Purpose:* make "289 Bleecker Street" equal "289 BLEECKER ST", and "Carbone LLC" comparable
  to "Carbone".
- *Why it matters:* every match, de-duplication and location count rests on this. It's the
  root of "duplicates and wrong location counts".
- *Why this way:* deterministic rules first (exact, explainable). rapidfuzz handles fuzzy
  similarity because it's fast C and has a standard API. Alternatives: `difflib` (fine but
  ~10× slower at this scale), address APIs (cost, rate limits), an LLM (non-deterministic,
  slow).

**Interfaces:**
- Produces:
  - `normalize_name(raw: str) -> str`
  - `normalize_address(raw: str) -> str`
  - `name_similarity(a: str, b: str) -> float` (0–1; `rapidfuzz.fuzz.token_set_ratio` on normalized names / 100)
  - `haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float`
  - `registrable_domain(url: str) -> str | None`

- [ ] **Step 1: Failing tests (the spec's exact values).**

```python
@pytest.mark.parametrize("raw,expected", [
    ("Carbone LLC", "carbone"),
    ("The Noortwyck, Inc.", "noortwyck"),
    ("Joe & Pat's Pizzeria Corp", "joe and pats pizzeria"),
])
def test_normalize_name(raw, expected):
    assert normalize_name(raw) == expected

@pytest.mark.parametrize("raw,expected", [
    ("289 Bleecker Street", "289 bleecker st"),
    ("289 BLEECKER ST #2", "289 bleecker st"),
    ("10 West 21st Street, Floor 3", "10 w 21 st"),
    ("1 Fifth Avenue", "1 5 ave"),
])
def test_normalize_address(raw, expected):
    assert normalize_address(raw) == expected

def test_haversine_known_distance():
    assert haversine_m(40.7308, -74.0018, 40.7317, -74.0018) == pytest.approx(100, rel=0.05)

def test_registrable_domain():
    assert registrable_domain("https://www.oriananewyork.com/reserve") == "oriananewyork.com"
```

- [ ] **Step 2: FAIL. Step 3: Implement.**
  - Name rules: drop corporate suffixes `llc|inc|corp|co|ltd|lp`, the leading `the`, punctuation; `&`→`and`.
  - Address rules: lowercase; ordinal suffixes `21st`→`21`; spelled ordinals `fifth`→`5` (first through twelfth); directionals `west`→`w` (and e/n/s); types `street`→`st`, `avenue`→`ave`, `place`→`pl`, `boulevard`→`blvd`, `road`→`rd`; drop unit tails `#…`, `suite …`, `ste …`, `floor …`, `fl …`, `apt …`.
- [ ] **Step 4: PASS. Step 5: Commit.** `git commit -m "feat(hospitality): name/address normalization and distance"`

---

### Task 7: License ↔ inspection matching

**Files:**
- Create: `scripts/hospitality/resolve/match.py`
- Test: `tests/hospitality/test_match.py`

**Rationale.**
- *Purpose:* connect a liquor license to the health-department record of the same physical
  venue.
- *Why it matters:* timing (issue → first inspection), recall truth, and attaching later
  signals all depend on this join.
- *Why this way:*
  - Block by ZIP code, then score each pair on location and name.
  - Matches above the auto threshold become the same venue.
  - The middle band becomes a "possibly same" link (recall-first: never silently merge or drop).
  - Splink is deferred (spec §5a); this rule-based scorer is explainable and good enough for
    one city.

**Interfaces:**
- Consumes: `LicenseRecord`, `InspectionVenue`, `EntityLink`, normalize functions, `HospitalityConfig`
- Produces:
  - `MatchPair(license_id: str, camis: str, probability: float, method: str)`, frozen; in `models.py`.
  - `MatchResult(pairs: tuple[MatchPair, ...], links: tuple[EntityLink, ...], unmatched_licenses: tuple[str, ...], unmatched_camis: tuple[str, ...])`, frozen; in `models.py`.
  - `pair_probability(lic: LicenseRecord, ins: InspectionVenue, max_distance_m: float) -> tuple[float, str]`
  - `match_licenses(licenses: Sequence[LicenseRecord], inspections: Sequence[InspectionVenue], cfg: HospitalityConfig) -> MatchResult`

**Scoring logic (this is the decision the implementer can't infer):**
```
location = 1.0                              if normalize_address equal
         = max(0, 1 - d / max_distance_m)   if both have coordinates
         = 0.0                              otherwise
name     = max(name_similarity(lic.dba, ins.dba), name_similarity(lic.legal_name, ins.dba))
p        = 0.6 * location + 0.4 * name
method   = "address+name" | "geo+name" | "name_only"
```
Each license takes its single best pair:
- `p ≥ match_auto_threshold` (0.90) → a `MatchPair`.
- `match_link_threshold` (0.60) ≤ `p` < 0.90 → an `EntityLink`.
- Otherwise the license is unmatched.

A CAMIS may match several licenses (e.g. a restaurant license and a catering license). That's
expected; keep all of them.

- [ ] **Step 1: Failing tests.**

```python
def test_same_address_same_name_auto_matches(cfg):
    lic = make_license("l1", dba="The Noortwyck", address="289 Bleecker Street", zip_code="10014")
    ins = make_inspection("c1", dba="NOORTWYCK", address="289 BLEECKER ST", zip_code="10014")
    res = match_licenses([lic], [ins], cfg)
    assert res.pairs[0].camis == "c1" and res.pairs[0].probability >= 0.9

def test_near_but_different_name_becomes_link_not_merge(cfg):
    lic = make_license("l2", dba="Oriana", address="1 Main St", lat=40.0, lon=-74.0, zip_code="10012")
    ins = make_inspection("c2", dba="Oriana Wine Bar", address="3 Main St", lat=40.0001, lon=-74.0, zip_code="10012")
    res = match_licenses([lic], [ins], cfg)
    assert res.pairs == () and res.links[0].kind == "possibly_same"

def test_different_zip_never_compared(cfg):
    lic = make_license("l3", dba="X", address="1 A St", zip_code="10001")
    ins = make_inspection("c3", dba="X", address="1 A St", zip_code="11201")
    assert match_licenses([lic], [ins], cfg).unmatched_licenses == ("l3",)
```

- [ ] **Step 2: FAIL. Step 3: Implement. Step 4: PASS. Step 5: Commit.** `git commit -m "feat(hospitality): license-inspection matching with possibly-same links"`

---

### Task 8: Venues and groups

**Files:**
- Create: `scripts/hospitality/resolve/venues.py`, `resolve/groups.py`
- Test: `tests/hospitality/test_venues.py`, `test_groups.py`

**Rationale.**
- *Purpose:* produce the canonical Venue list and a first-pass Group for each venue.
- *Why it matters:* the Group is the unit of account (spec §5a), and location counts come from
  here.
- *Why this way:*
  - Group-of-one by default, merging only on strong deterministic evidence: identical
    normalized legal name across venues, or a shared website domain.
  - Merges from websites and press come later through `merge_groups` (Concern 4).
  - Alternative: guess groups with an LLM. That's unverifiable at universe scale and produces
    exactly the wrong location counts Magic complains about.

**Interfaces:**
- Consumes: `MatchResult`, `LicenseRecord`, `InspectionVenue`, `Venue`, `Group`
- Produces:
  - `build_venues(licenses: Sequence[LicenseRecord], inspections: Sequence[InspectionVenue], match: MatchResult) -> list[Venue]`. `venue_id` is `f"v:{camis}"` or `f"v:lic:{record_id}"`. `license_class` and `license_description` come from the most recent license. `group_id` is initially `f"g:{venue_id}"`.
  - `GroupEvidence(venue_ids: tuple[str, ...], name: str, resolution: GroupResolution, evidence_ref: str)`, frozen; in `models.py`.
  - `form_groups(venues: Sequence[Venue], licenses: Sequence[LicenseRecord]) -> tuple[list[Venue], list[Group]]`
  - `merge_groups(venues: Sequence[Venue], groups: Sequence[Group], evidence: Sequence[GroupEvidence]) -> tuple[list[Venue], list[Group]]`. Union-find over `venue_ids`. The merged group keeps the strongest resolution, in the order `manual > website_locations > press > shared_domain > shared_legal_name > agent > singleton`.

- [ ] **Step 1: Failing tests.**

```python
def test_unmatched_license_becomes_its_own_venue():
    venues = build_venues([make_license("l9")], [], MatchResult(pairs=(), links=(), unmatched_licenses=("l9",), unmatched_camis=()))
    assert venues[0].venue_id == "v:lic:l9" and venues[0].camis is None

def test_shared_legal_name_forms_group():
    lics = [make_license("a", legal_name="HAPPY COOKING LLC"), make_license("b", legal_name="Happy Cooking, LLC")]
    venues, groups = form_groups([make_venue("v:a", license_ids=("a",)), make_venue("v:b", license_ids=("b",))], lics)
    assert len(groups) == 1 and groups[0].resolution == "shared_legal_name"

def test_merge_is_transitive():
    vs = [make_venue(f"v:{i}") for i in "abc"]
    _, gs = form_groups(vs, [])
    ev = [GroupEvidence(venue_ids=("v:a", "v:b"), name="G", resolution="press", evidence_ref="x"),
          GroupEvidence(venue_ids=("v:b", "v:c"), name="G", resolution="website_locations", evidence_ref="y")]
    venues, groups = merge_groups(vs, gs, ev)
    assert len(groups) == 1 and groups[0].resolution == "website_locations"
    assert {v.group_id for v in venues} == {groups[0].group_id}
```

- [ ] **Step 2: FAIL. Step 3: Implement.**
  - Exclude generic legal names from the shared-name rule (a config list, starting with `"restaurant"`, `"hospitality"`, `"management"` when the whole normalized name is only these words).
  - Group ID: `"g:" + sorted(venue_ids)[0]`.
  - *Why deterministic IDs: reruns don't churn the IDs that scores and drafts reference.*
- [ ] **Step 4: PASS.**
- [ ] **Step 5: CLI `resolve`** (runs match → build → form, saves the `venues`, `groups` and `links` kinds, prints counts and the number of possibly-same links). Run it live.
- [ ] **Step 6: Commit.** `git commit -m "feat(hospitality): build venues and deterministic groups"`

---

### Task 9: Opening-timing survival curve and window estimates

**Files:**
- Create: `scripts/hospitality/window/__init__.py`, `window/survival.py`, `window/estimate.py`
- Test: `tests/hospitality/test_survival.py`, `test_estimate.py`

**Rationale.**
- *Purpose:* learn, from thousands of real license → first-inspection pairs, how long venues
  take to open after licensing, then estimate each pending/new venue's opening date.
- *Why it matters:* this turns "a filing exists" into "this group is ~4 months from opening",
  which is what makes outreach timely. It's also a finding Magic doesn't have.
- *Why this way:* Kaplan–Meier handles venues that haven't opened yet (censoring) without
  pretending they never will. Alternatives: a plain median of the opened ones (biased short,
  because it drops slow openers) or a regression model (overkill for one variable and harder to
  explain).

**Interfaces:**
- Consumes: `Venue`, `LicenseRecord`, `HospitalityConfig`, `WindowEstimate`
- Produces:
  - `Curve = tuple[tuple[float, float], ...]`, i.e. `(t_days, survival)` steps starting at `(0.0, 1.0)`
  - `kaplan_meier(durations: Sequence[float], observed: Sequence[bool]) -> Curve`
  - `survival_at(curve: Curve, t: float) -> float`
  - `quantile_time(curve: Curve, q: float) -> float | None`, the first `t` where `S(t) ≤ 1 - q`
  - `opening_durations(venues: Sequence[Venue], licenses: Sequence[LicenseRecord], today: date) -> list[tuple[str, float, bool]]`, i.e. `(stratum, days, observed)`
  - `build_curves(durations: Sequence[tuple[str, float, bool]], min_n: int = 30) -> dict[str, Curve]` (always includes key `"all"`; strata below `min_n` are dropped)
  - `estimate_window(venue: Venue, license: LicenseRecord, curves: dict[str, Curve], cfg: HospitalityConfig, today: date) -> WindowEstimate | None`

**Logic the implementer can't infer:**
- *Duration rules:*
  - For each venue with an active/inactive license, `days = first_inspection_date - original_issue_date`.
  - Exclude it if `days < 0`: the venue was inspected before this license, so it's a renewal,
    transfer or class change, not a new opening (Review Focus 2).
  - Exclude it if `days > 730` (data noise).
  - A licensed venue with no inspection yet is censored at `today - original_issue_date`.
- *Stratum:* `f"{license_description}|{county}"`, falling back to `"all"`.
- *Estimate for an issued license with no inspection yet:*
  - `age = today - issue`
  - `estimated_open = issue + median`, where `median = quantile_time(curve, 0.5)`; if that date is already past, use `today + (median of the conditional remaining time)`
  - `p_open_90d = 1 - S(age + 90) / S(age)`; `p_open_180d` similarly.
- *Estimate for a pending application:* shift by `pending_to_issue_prior_days` (Concern 5),
  then apply the issued-license logic with `age = 0`. `basis` must say `"prior:pending_to_issue=75d"`
  so the assumption shows up in the report.

- [ ] **Step 1: Failing tests (hand-computed Kaplan–Meier).**

```python
def test_kaplan_meier_hand_computed():
    curve = kaplan_meier([10, 20, 20, 30], [True, True, False, True])
    assert survival_at(curve, 9) == 1.0
    assert survival_at(curve, 10) == pytest.approx(0.75)
    assert survival_at(curve, 20) == pytest.approx(0.50)
    assert survival_at(curve, 30) == pytest.approx(0.0)

def test_quantile_time_median():
    curve = kaplan_meier([10, 20, 20, 30], [True, True, False, True])
    assert quantile_time(curve, 0.5) == 20

def test_negative_duration_excluded_as_not_new_opening():
    v = make_venue("v:1", first_inspection_date=date(2025, 1, 1), license_ids=("a",))
    lic = make_license("a", source="sla_active", original_issue_date=date(2026, 1, 1))
    assert opening_durations([v], [lic], date(2026, 11, 16)) == []

def test_pending_estimate_records_prior_in_basis(cfg):
    curves = {"all": kaplan_meier([60] * 40, [True] * 40)}
    v = make_venue("v:lic:p", first_inspection_date=None)
    lic = make_license("p", source="sla_pending", received_date=date(2026, 11, 1))
    est = estimate_window(v, lic, curves, cfg, today=date(2026, 11, 16))
    assert est.estimated_open == date(2026, 11, 1) + timedelta(days=75 + 60)
    assert "prior:pending_to_issue=75d" in est.basis
```

- [ ] **Step 2: FAIL. Step 3: Implement** (standard product-limit estimator; events counted before censorings at tied times, matching the test). **Step 4: PASS.**
- [ ] **Step 5: CLI `window`.** It builds the curves, saves `curves` and the per-venue `estimates`, and prints the median and IQR for `"all"` and the top 3 strata. Run it live and **record the numbers in `out/magic/notes.md`**. *Why: the median and spread are a headline slide; write them down while fresh.*
- [ ] **Step 6: Commit.** `git commit -m "feat(hospitality): Kaplan-Meier opening curves and window estimates"`

---

# P0: Day 2. Signals, stack, scoring, measurement

### Task 10: Website lookup (Google Places) for prioritized venues

**Files:**
- Create: `scripts/hospitality/stack/__init__.py`, `stack/websites.py`
- Test: `tests/hospitality/test_websites.py`

**Rationale.**
- *Purpose:* find each venue's website so we can crawl its stack (Concern 3).
- *Why it matters:* without URLs there's no platform detection, no Loyalist-embed labels and no
  contacts.
- *Why this way:*
  - Places Text Search with a minimal field mask, called only for prioritized venues: everything
    with an opening signal or estimate, plus seed customers, capped by budget.
  - Accept a result only if its location is within 75 m and the name similarity is ≥ 0.6;
    otherwise there's no website. *Why: a wrong website poisons every downstream signal.*
  - Alternative: crawl search engines (ToS risk) or ask an LLM (fabricates URLs).

**Interfaces:**
- Consumes: `Venue`, `CallBudget`, `haversine_m`, `name_similarity`
- Produces:
  - `PlaceMatch(place_id: str, display_name: str, address: str, website: str | None, lat: float, lon: float)`, frozen; in `models.py`.
  - `PlacesClient(api_key: str, budget: CallBudget)` with `.search(text_query: str) -> list[PlaceMatch]`. It POSTs `https://places.googleapis.com/v1/places:searchText` with header `X-Goog-FieldMask: places.id,places.displayName,places.formattedAddress,places.websiteUri,places.location`.
  - `pick_place(venue: Venue, candidates: Sequence[PlaceMatch]) -> PlaceMatch | None`
  - `attach_websites(venues: Sequence[Venue], client: PlacesClient, priority_ids: Sequence[str]) -> list[Venue]`. Returns new Venue objects with `website` set; venues outside `priority_ids` are returned unchanged.

- [ ] **Step 1: Failing tests.**

```python
def test_pick_place_rejects_far_result():
    v = make_venue("v:1", name="Oriana", lat=40.7, lon=-74.0)
    far = PlaceMatch(place_id="p", display_name="Oriana", address="x", website="https://o.com", lat=40.8, lon=-74.0)
    assert pick_place(v, [far]) is None

def test_budget_stops_lookups(mocker):
    client = PlacesClient("k", CallBudget("places", limit=1))
    mocker.patch.object(client, "_post", return_value={"places": []})
    client.search("a")
    with pytest.raises(BudgetExceeded):
        client.search("b")
```

- [ ] **Step 2: FAIL. Step 3: Implement** (query `f"{venue.name} {venue.address} New York"`). **Step 4: PASS.**
- [ ] **Step 5: Verify the Places field tier and free allowance on Google's pricing page; record it in the docstring.** *Why: `websiteUri` may bill at a higher tier than the basic fields; the budget must reflect the true cost.*
- [ ] **Step 6: CLI `websites --limit 400`. Run live. Commit.** `git commit -m "feat(hospitality): Google Places website lookup with budget"`

---

### Task 11: Platform fingerprints

**Files:**
- Create: `scripts/hospitality/stack/fingerprints.py`
- Test: `tests/hospitality/test_fingerprints.py`; fixtures `site_resy_tripleseat.html`, `site_text_only.html`, `site_loyalist_embed.html`, `site_punchh.html`

**Rationale.**
- *Purpose:* recognize reservation, POS, events, email and loyalty tools, plus Loyalist's own
  embed, from a page's HTML.
- *Why it matters:* it feeds four signals (fragmented stack, Tripleseat+Resy, private events,
  platform switch), the disqualifier, and the customer labels.
- *Why this way:* match only inside `href`, `src`, `action` and `data-*` attributes and inside
  `<script>` bodies, parsed with selectolax (already a dependency). That avoids text and theme
  false positives (Review Focus 3). Alternatives: regex over raw HTML (matches marketing copy)
  or BuiltWith (monthly and inaccurate, spec §6.3).

**Interfaces:**
- Produces:
  - `FINGERPRINTS: dict[str, tuple[str, ...]]`, exactly:

```python
FINGERPRINTS = {
    "resy": ("resy.com",),
    "opentable": ("opentable.com", "otstatic.com"),
    "sevenrooms": ("sevenrooms.com",),
    "tock": ("exploretock.com",),
    "toast": ("toasttab.com",),
    "square": ("squareup.com", "square.site"),
    "tripleseat": ("tripleseat.com",),
    "perfect_venue": ("perfectvenue.com",),
    "loyalist": ("eatloyalist.com", "loyalist-venue-id"),
    "bentobox": ("getbento.com",),
    "mailchimp": ("list-manage.com",),
    "punchh": ("punchh.com",),
    "thanx": ("thanx.com",),
    "olo": ("olo.com",),
    "incentivio": ("incentivio.com",),
}
RESERVATION = frozenset({"resy", "opentable", "sevenrooms", "tock"})
EVENTS = frozenset({"tripleseat", "perfect_venue"})
QSR_LOYALTY = frozenset({"punchh", "thanx", "olo", "incentivio"})
```

  - `detect_platforms(html: str) -> tuple[tuple[str, str], ...]`, i.e. `(platform, evidence)` sorted by platform, one entry per platform. Evidence is the matched attribute value truncated to 120 chars.

- [ ] **Step 1: Failing tests.**

```python
def test_widget_links_detected():
    found = dict(detect_platforms(fixture_text("site_resy_tripleseat.html")))
    assert {"resy", "tripleseat"} <= found.keys()

def test_text_mention_is_not_detection():
    assert detect_platforms('<p>Find us on Resy and Tock!</p>') == ()

def test_loyalist_schema_property_detected():
    html = '<script type="application/ld+json">{"propertyID":"loyalist-venue-id"}</script>'
    assert dict(detect_platforms(html))["loyalist"]

def test_olo_does_not_match_unrelated_domains():
    assert detect_platforms('<a href="https://polo.com/x">x</a>') == ()
```

- [ ] **Step 2: FAIL. Step 3: Implement.** Domain patterns must match on a host boundary: the matched host equals the pattern or ends with `"." + pattern`. That's why `polo.com` doesn't match `olo.com`. The non-domain pattern `loyalist-venue-id` matches as a substring of script bodies only.
- [ ] **Step 4: PASS. Step 5: Commit.** `git commit -m "feat(hospitality): platform fingerprint detection"`

---

### Task 12: Stack crawl with Firecrawl fallback, and stack signals

**Files:**
- Create: `scripts/hospitality/stack/crawl.py`, `stack/signals.py`
- Test: `tests/hospitality/test_crawl.py`, `test_stack_signals.py`

**Rationale.**
- *Purpose:* fetch each venue website cheaply, detect its stack, and turn observations into
  signals.
- *Why it matters:* the stack-based Tier 1 signals and the Loyalist embed labels come from
  here.
- *Why this way:*
  - The existing `fetch_all` respects robots, caps bodies, guards SSRF and limits per-host
    concurrency, so it's reused rather than rewritten.
  - Firecrawl runs only when no reservation platform was found, because widgets are often
    JavaScript-injected. That spends credits only where needed (spec §6.13).
  - Alternative: Firecrawl for everything (burns free credits in minutes).

**Interfaces:**
- Consumes: `fetch_all`, `SourceRef`, `guarded_client` (existing), `FirecrawlClient.scrape` (existing), `detect_platforms`, `RESERVATION`, `EVENTS`, `QSR_LOYALTY`, `CallBudget`
- Produces:
  - `async crawl_stacks(venues: Sequence[Venue], now: datetime, *, firecrawl: FirecrawlClient | None, firecrawl_budget: CallBudget) -> list[StackObservation]` (only venues with `website`)
  - `stack_signals(observations: Sequence[StackObservation], venues: Sequence[Venue], previous: Sequence[StackObservation], now: datetime) -> list[Signal]`, which emits:
    - `stack_fragmented`: a group whose venues together show ≥ 2 distinct `RESERVATION` platforms. Entity is the group.
    - `tripleseat_resy`: a venue showing both `tripleseat` and `resy`. Entity is the venue.
    - `private_events`: any `EVENTS` platform. Entity is the venue.
    - `platform_switch`: a venue's `RESERVATION` set differs from its most recent previous observation. `detail` reads `"opentable→resy"`.
  - `disqualified_venues(observations: Sequence[StackObservation]) -> dict[str, str]`, i.e. venue_id → reason (`"qsr_loyalty:punchh"`)
  - `loyalist_venues(observations: Sequence[StackObservation]) -> dict[str, str]`, i.e. venue_id → evidence

- [ ] **Step 1: Failing tests.**

```python
async def test_firecrawl_only_when_no_reservation(mocker):
    venues = [make_venue("v:1", website="https://a.com"), make_venue("v:2", website="https://b.com")]
    mocker.patch("scripts.hospitality.stack.crawl.fetch_all", return_value=[
        ProbeResult(source_id=0, status_code=200, body='<a href="https://resy.com/x">'),
        ProbeResult(source_id=1, status_code=200, body="<div id=app></div>")])
    fc = mocker.Mock(); fc.scrape.return_value = {"data": {"html": '<a href="https://exploretock.com/b">'}}
    obs = await crawl_stacks(venues, NOW, firecrawl=fc, firecrawl_budget=CallBudget("fc", 5))
    assert fc.scrape.call_count == 1
    assert dict((o.venue_id, o.platforms) for o in obs)["v:2"] == ("tock",)

def test_fragmented_stack_is_group_level():
    venues = [make_venue("v:1", group_id="g:1"), make_venue("v:2", group_id="g:1")]
    obs = [make_obs("v:1", ("resy",)), make_obs("v:2", ("sevenrooms",))]
    sigs = stack_signals(obs, venues, previous=[], now=NOW)
    assert any(s.signal_type == "stack_fragmented" and s.entity_id == "g:1" for s in sigs)

def test_platform_switch_from_previous():
    prev = [make_obs("v:1", ("opentable",), at=NOW - timedelta(days=7))]
    sigs = stack_signals([make_obs("v:1", ("resy",))], [make_venue("v:1")], prev, NOW)
    assert [s.detail for s in sigs if s.signal_type == "platform_switch"] == ["opentable→resy"]
```

- [ ] **Step 2: FAIL. Step 3: Implement.**
  - Firecrawl result: read `["data"]["html"]` or `["data"]["rawHtml"]`; check the existing client's return shape and use what it returns.
  - A failed fetch yields no observation (logged), never a crash.
  - Signal IDs: `f"{signal_type}:{entity_id}:{now.date()}"`. *Why: deterministic IDs make reruns idempotent in the store and keep drafts' evidence references stable.*
- [ ] **Step 4: PASS.**
- [ ] **Step 5: CLI `crawl`.** It saves `stack_observations` (appending, so history accumulates) and `signals`, and prints the platform distribution, the Loyalist-embed count and the disqualified count. Run it live.
- [ ] **Step 6: Commit.** `git commit -m "feat(hospitality): stack crawl with firecrawl fallback and stack signals"`

---

### Task 13: Customer labels (seed + embed)

**Files:**
- Create: `scripts/hospitality/labels.py`, `examples/magic-loyalist/customers_seed.yaml`
- Test: `tests/hospitality/test_labels.py`

**Rationale.**
- *Purpose:* know which groups are already Loyalist customers.
- *Why it matters:* it's needed to exclude them from prospecting (Review Focus 4), to seed
  lookalikes, and to run the backtests.
- *Why this way:*
  - Public list with dates, from the research, plus embed detection (spec §6.3a).
  - Matching is by website domain first (exact), then normalized name with similarity ≥ 0.9
    (strict, to avoid labelling a namesake).
  - Alternative: names only (too many false labels, e.g. "Bluebird").

**Interfaces:**
- Consumes: `CustomerLabel`, `Venue`, `Group`, `loyalist_venues`, `registrable_domain`, `name_similarity`
- Produces:
  - `load_seed_labels(path: Path) -> list[CustomerLabel]`
  - `labels_from_embeds(embeds: dict[str, str], venues: Sequence[Venue], first_seen: dict[str, date]) -> list[CustomerLabel]`
  - `customer_groups(labels: Sequence[CustomerLabel], venues: Sequence[Venue], groups: Sequence[Group]) -> dict[str, CustomerLabel]`, i.e. group_id → earliest-dated label

- [ ] **Step 1: Write `customers_seed.yaml`** from `docs/research/magic/02–04`. Each entry has `name`, `website_domain` (when known), `first_public_date` (the upper-bound date, e.g. `2024-11-02` for The Noortwyck, `2025-10-20` for Le Bernardin/COTE/Dinex/Momofuku/Cosme, `2025-10-29` for Rezdôra), and `evidence_ref` (the source URL). Undated entries get `first_public_date: null`. *Why: dated labels drive the case replay; undated ones still exclude customers from prospecting.*
- [ ] **Step 2: Failing tests.**

```python
def test_domain_match_beats_name():
    venues = [make_venue("v:1", name="Bluebird", website="https://bluebirdchapelhill.com", group_id="g:1"),
              make_venue("v:2", name="Bluebird", website="https://bluebird-nyc.com", group_id="g:2")]
    labels = [CustomerLabel(name="Bluebird", website_domain="bluebirdchapelhill.com",
                            first_public_date=None, source="public_list", evidence_ref="x")]
    assert set(customer_groups(labels, venues, groups_for(venues))) == {"g:1"}

def test_earliest_label_wins():
    ...  # two labels for one group (seed dated 2025-10-20, embed first-seen 2026-11-16) → seed kept
```

- [ ] **Step 3: FAIL. Step 4: Implement. Step 5: PASS.**
- [ ] **Step 6: CLI `labels`.** Prints the number of customer groups by source. **Commit.** `git commit -m "feat(hospitality): customer labels from public list and embeds"`

---

### Task 14: License signals and scoring

**Files:**
- Create: `scripts/hospitality/signals.py`, `scripts/hospitality/scoring.py`
- Test: `tests/hospitality/test_signals.py`, `test_scoring.py`

**Rationale.**
- *Purpose:* turn records into dated signals, then signals into a calibrated-style P(in window)
  per group, with a trace.
- *Why it matters:* this is the ranked list everything else consumes, and the explainability
  sales needs ("why is this 0.62?").
- *Why this way:* noisy-OR means any one strong signal can put a group in a window, which suits
  recall (spec §6.5). The traces mirror `scripts/scoring/engine.py` (components plus a `zero_out`
  replay). The existing engine's breadth multiplier is a precision-style heuristic that the spec
  replaced, so this is a new module rather than an edit of `engine.py`.

**Interfaces:**
- Consumes: `Venue`, `LicenseRecord`, `WindowEstimate`, `Signal`, `Group`, `HospitalityConfig`, `StackObservation`, `RESERVATION`, `EVENTS`, `customer_groups` output, `disqualified_venues` output
- Produces (in `signals.py`):
  - `license_signals(venues: Sequence[Venue], licenses: Sequence[LicenseRecord], first_seen_pending: dict[str, date], today: date) -> list[Signal]`:
    - `license_pending` for each pending record. `observed_at` = first-seen snapshot date if known, else `received_date`.
    - `license_issued` for each active license issued within the last 365 days whose venue has no first inspection or a first inspection after the issue date. `observed_at` = `original_issue_date`.
    - `not_yet_inspected` for each never-inspected venue with any license. `observed_at` = the license date.
- Produces (in `scoring.py`):
  - `window_weight(signal: Signal, prior: SignalPrior, estimate: WindowEstimate | None, now: datetime, cfg: HospitalityConfig) -> float`
  - `noisy_or(ps: Sequence[float]) -> float`
  - `fit_score(group: Group, venues: Sequence[Venue], observations: Sequence[StackObservation], cfg: HospitalityConfig) -> float`
  - `score_group(group: Group, signals: Sequence[Signal], estimates: dict[str, WindowEstimate], venues: Sequence[Venue], observations: Sequence[StackObservation], cfg: HospitalityConfig, now: datetime, *, is_customer: bool, disqualified_reason: str | None) -> ScoredAccount`
  - `zero_out(account_inputs: ScoreInputs, signal_type: str) -> ScoredAccount`, where `ScoreInputs` is a frozen bundle of `score_group`'s arguments, so replay uses identical inputs.
  - `rank_prospects(accounts: Sequence[ScoredAccount]) -> list[ScoredAccount]`: excludes `is_customer` and disqualified accounts; sorts by `priority` descending, then `group_id`.

**Logic the implementer can't infer:**
```
window_weight:
  family == "opening" and estimate is not None:
      rel = (now.date() - estimate.estimated_open).days        # negative = before opening
      inside = -cfg.window_pre_days <= rel <= cfg.window_post_days
      w = 1.0 if inside else 0.5 ** (dist_outside / cfg.window_outside_half_life_days)
  half_life_days is None:   w = 1.0   (state signals, valid while last observed)
  otherwise:                w = 0.5 ** (age_days / half_life_days)
contribution_i = prior.precision * w
p_window   = noisy_or(contribution_i for signals of family != "relationship")
fit        = Σ fit_weights[k] for satisfied k   (0..1):
    multi_venue          → group has ≥ 2 venues
    reservation_platform → any venue shows a RESERVATION platform
    events_program       → any EVENTS platform
    accolade             → group flagged in config `accolades` list (Michelin/JBF; manual for demo)
    full_service_class   → any venue license_description == "Restaurant"
relationship = 1 + cfg.relationship_boost if any alumni_edge signal else 1.0
priority   = p_window * (0.5 + 0.5 * fit) * relationship
disqualified → priority 0.0 and reason kept
```
*Why `0.5 + 0.5 * fit` instead of `× fit`:* recall-first. An unknown fit (no website yet) should
halve priority, not zero it. This is my call; the spec wrote `P × Fit × Relationship`.

- [ ] **Step 1: Failing tests (exact numbers).**

```python
def test_noisy_or():
    assert noisy_or([0.5, 0.5]) == pytest.approx(0.75)
    assert noisy_or([]) == 0.0

def test_window_weight_inside_is_one(cfg):
    est = make_estimate("v:1", estimated_open=date(2027, 2, 1))
    sig = make_signal("license_pending", "v:1")
    assert window_weight(sig, cfg.priors["license_pending"], est, datetime(2026, 11, 16, tzinfo=UTC), cfg) == 1.0

def test_window_weight_decays_outside(cfg):
    est = make_estimate("v:1", estimated_open=date(2027, 11, 16))  # 365 days ahead → 182 days outside
    w = window_weight(make_signal("license_pending", "v:1"), cfg.priors["license_pending"], est, NOW, cfg)
    assert w == pytest.approx(0.5 ** (182 / 60), rel=1e-3)

def test_customer_excluded_from_prospects():
    a = make_scored("g:1", priority=0.9, is_customer=True)
    b = make_scored("g:2", priority=0.1)
    assert [x.group_id for x in rank_prospects([a, b])] == ["g:2"]

def test_zero_out_removes_contribution(cfg):
    inputs = make_score_inputs(signals=[make_signal("license_pending", "v:1"), make_signal("private_events", "v:1")])
    full = score_group(**inputs.model_dump()); without = zero_out(inputs, "license_pending")
    assert without.p_window < full.p_window
```

- [ ] **Step 2: FAIL. Step 3: Implement both modules. Step 4: PASS.**
- [ ] **Step 5: CLI `score`.** It saves `scores` and prints the top 25 prospects with their top 3 contributions each. Run it live and **sanity-read the top 25 by hand**. *Why: a 5-minute human read catches matching or class-filter bugs that tests on fixtures can't.*
- [ ] **Step 6: Commit.** `git commit -m "feat(hospitality): license signals, noisy-OR window scoring with traces"`

---

### Task 15: Recall audit

**Files:**
- Create: `scripts/hospitality/measure/__init__.py`, `measure/recall.py`
- Test: `tests/hospitality/test_recall.py`

**Rationale.**
- *Purpose:* measure what share of real openings the system flagged *before* they opened, and
  how early.
- *Why it matters:* this is the headline number for "find as many as possible" and the core of
  the "beats plain Claude" story (spec §7a).
- *Why this way:* ground truth is public (DOHMH first inspection) and the rule is
  deterministic. It's a historical replay, valid because license-issued signals carry their
  issue date. Alternative: precision-only metrics, which say nothing about missed openings.

**Interfaces:**
- Consumes: `Venue`, `Signal`, `HospitalityConfig`
- Produces:
  - `RecallReport(start: date, end: date, total: int, caught: int, recall: float, median_lead_days: float | None, lead_days: tuple[int, ...], misses: tuple[str, ...])`, frozen; in `models.py`.
  - `ground_truth_openings(venues: Sequence[Venue], start: date, end: date, cfg: HospitalityConfig) -> list[Venue]`: `start ≤ first_inspection_date ≤ end` and `license_description in cfg.on_premise_descriptions`.
  - `recall_audit(openings: Sequence[Venue], signals: Sequence[Signal], start: date, end: date) -> RecallReport`: a venue is caught if any `family == "opening"` signal on that venue has `observed_at.date() < first_inspection_date`. Lead = `first_inspection_date - earliest such observed_at`.

- [ ] **Step 1: Failing tests.**

```python
def test_recall_counts_only_prior_signals(cfg):
    v1 = make_venue("v:1", first_inspection_date=date(2026, 10, 1), license_description="Restaurant")
    v2 = make_venue("v:2", first_inspection_date=date(2026, 10, 5), license_description="Restaurant")
    sigs = [make_signal("license_issued", "v:1", observed=date(2026, 7, 1)),
            make_signal("license_issued", "v:2", observed=date(2026, 10, 6))]  # after opening → miss
    r = recall_audit([v1, v2], sigs, date(2026, 9, 1), date(2026, 10, 31))
    assert (r.total, r.caught, r.recall) == (2, 1, 0.5)
    assert r.lead_days == (92,) and r.misses == ("v:2",)

def test_ground_truth_excludes_grocery(cfg):
    g = make_venue("v:3", first_inspection_date=date(2026, 10, 1), license_description="Grocery Store")
    assert ground_truth_openings([g], date(2026, 9, 1), date(2026, 10, 31), cfg) == []
```

- [ ] **Step 2: FAIL. Step 3: Implement. Step 4: PASS.**
- [ ] **Step 5: CLI `recall --weeks 12`. Run live; record recall and median lead in `out/magic/notes.md`.**
- [ ] **Step 6: Commit.** `git commit -m "feat(hospitality): recall audit against DOHMH first inspections"`

---

### Task 16: Head-to-head vs plain Claude

**Files:**
- Create: `scripts/hospitality/benchmark/__init__.py`, `benchmark/baseline.py`, `benchmark/compare.py`
- Test: `tests/hospitality/test_benchmark.py`

**Rationale.**
- *Purpose:* answer "why not just ask Claude?" with numbers (spec §7a).
- *Why it matters:* it's Sami's stated differentiation concern and the strongest meeting
  artifact.
- *Why this way:*
  - The same model (Opus 5.5) with the current web-search tool (`web_search_20260209`), run 3
    times to show variance.
  - Two steps: first search and write the list, then structure it with `messages.parse`.
    *Why two steps: structured outputs and web-search citations don't combine cleanly, so
    splitting avoids fighting the API.*
  - The SignalForce list is computed as of the cutoff using only data dated on or before it.
  - Alternative: compare against an LLM without search (unfair to Claude, and Magic would see
    through it).

**Interfaces:**
- Consumes: `llm.structured`, an Anthropic client, `ScoredAccount`, `Venue`, `ground_truth_openings`, `normalize_name`, `name_similarity`
- Produces:
  - `BaselineItem(name: str, location: str, group: str | None, expected_opening: str | None)` and `BaselineRun(run_index: int, items: tuple[BaselineItem, ...], searches_used: int)`, frozen; in `models.py`.
  - `BASELINE_PROMPT: str`. The exact text: *"Today is {cutoff}. List as many New York City full-service restaurants, bars or hospitality venues as you can that are expected to open in the next 8 weeks, especially new locations from existing restaurant groups. For each give the venue name, neighborhood or address, the group that owns it if known, and the expected opening timing. Use web search."*
  - `run_baseline(client: Anthropic, cutoff: date, runs: int = 3, max_searches: int = 20) -> list[BaselineRun]`. Uses tools `[{"type": "web_search_20260209", "name": "web_search", "max_uses": max_searches}]` and handles `pause_turn` by continuing.
  - `match_items(items: Sequence[BaselineItem], universe: Sequence[Venue]) -> dict[int, str | None]`, i.e. item index → venue_id. Similarity ≥ 0.85 on name; when the item carries a location, the venue's ZIP or borough must agree.
  - `BenchmarkResult(k: int, sf_hits: int, sf_precision_at_k: float, claude_hits: tuple[int, ...], claude_precision_at_k: tuple[float, ...], claude_duplicates: tuple[int, ...], claude_unmatched: tuple[int, ...], claude_run_jaccard: float, truth_total: int, notes: tuple[str, ...])`, frozen; in `models.py`.
  - `compare(sf_top: Sequence[ScoredAccount], sf_venues_by_group: dict[str, tuple[str, ...]], runs: Sequence[BaselineRun], truth: Sequence[Venue], universe: Sequence[Venue], k: int = 50) -> BenchmarkResult`. `notes` always includes the fixed text *"Hindsight leak favors the Claude baseline (it can read press published after the cutoff); a SignalForce win is conservative."*

- [ ] **Step 1: Failing tests (mocked client).**

```python
def test_compare_counts_hits_dupes_and_unmatched():
    truth = [make_venue("v:1", name="Oriana"), make_venue("v:2", name="Massara")]
    universe = truth + [make_venue("v:3", name="Other")]
    runs = [BaselineRun(run_index=0, searches_used=5, items=(
        BaselineItem(name="Oriana", location="", group=None, expected_opening=None),
        BaselineItem(name="Oriana NYC", location="", group=None, expected_opening=None),
        BaselineItem(name="Made Up Place", location="", group=None, expected_opening=None)))]
    sf_top = [make_scored("g:v:1"), make_scored("g:v:2")]
    r = compare(sf_top, {"g:v:1": ("v:1",), "g:v:2": ("v:2",)}, runs, truth, universe, k=50)
    assert r.sf_hits == 2 and r.claude_hits == (1,)
    assert r.claude_duplicates == (1,) and r.claude_unmatched == (1,)

def test_run_baseline_uses_current_web_search_tool(mocker):
    client = fake_client_returning_text_then_parsed(mocker)
    run_baseline(client, date(2026, 9, 21), runs=1)
    tools = client.messages.create.call_args.kwargs["tools"]
    assert tools[0]["type"] == "web_search_20260209"
```

- [ ] **Step 2: FAIL. Step 3: Implement. Step 4: PASS.**
- [ ] **Step 5: CLI `benchmark --cutoff-weeks 8`.** It runs the baseline (3 runs), rebuilds the SF ranking as of the cutoff (signals with `observed_at ≤ cutoff`, estimates computed with `today=cutoff`), compares, and saves `benchmark`. **Cost check before running:** print the estimated maximum spend (3 runs × 20 searches + tokens) and require `--yes`. *Why: this is the first command that spends real money on Claude; make it explicit.*
- [ ] **Step 6: Commit.** `git commit -m "feat(hospitality): head-to-head benchmark vs plain Claude with web search"`

---

### Task 17: Backtests (case replay + fit AUC)

**Files:**
- Create: `scripts/hospitality/measure/backtest.py`
- Test: `tests/hospitality/test_backtest.py`

**Rationale.**
- *Purpose:* check the targeting against Magic's actual customers, honestly (Concern 6).
- *Why it matters:* this is the "work backwards from customers" proof, and Magic's own logos
  are the most persuasive evidence in the room.
- *Why this way:*
  - Case replay asks the real question (would we have seen them coming?) on the few cases that
    can answer it.
  - The fit AUC asks only what static data can answer.
  - Alternative: one AUC over everything, which mixes timing with fit and misleads.

**Interfaces:**
- Consumes: `customer_groups` output, `Signal`, `Venue`, `ScoredAccount`
- Produces:
  - `auc(pos: Sequence[float], neg: Sequence[float]) -> float` (Mann–Whitney; ties count 0.5)
  - `CaseReplay(group_id: str, customer: str, anchor_date: date, new_venue_id: str | None, first_signal_date: date | None, lead_days: int | None, signal_types: tuple[str, ...])`, frozen; in `models.py`.
  - `case_replay(labels: dict[str, CustomerLabel], venues: Sequence[Venue], signals: Sequence[Signal], new_venue_hints: dict[str, str]) -> list[CaseReplay]`. `new_venue_hints` maps group_id → new venue name (from the research: Oriana, Massara, Bar Kabawa, La Tête d'Or…). The venue is found by name similarity ≥ 0.85 within the group's venues or the universe. Lead = anchor − earliest opening-family signal on that venue.
  - `fit_auc(accounts: Sequence[ScoredAccount]) -> float`. Positives are customer groups, negatives are all others.

- [ ] **Step 1: Failing tests.**

```python
def test_auc_hand_computed():
    assert auc([0.9, 0.4], [0.5, 0.1]) == pytest.approx(0.75)
    assert auc([0.5], [0.5]) == pytest.approx(0.5)

def test_case_replay_lead_days():
    labels = {"g:1": CustomerLabel(name="The Noortwyck", website_domain=None,
                                   first_public_date=date(2026, 5, 1), source="public_list", evidence_ref="x")}
    venues = [make_venue("v:o", name="Oriana", group_id="g:1")]
    sigs = [make_signal("license_issued", "v:o", observed=date(2026, 2, 1))]
    [r] = case_replay(labels, venues, sigs, {"g:1": "Oriana"})
    assert r.lead_days == 89 and r.signal_types == ("license_issued",)
```

- [ ] **Step 2: FAIL. Step 3: Implement. Step 4: PASS.**
- [ ] **Step 5: CLI `backtest`.** It prints the case table and the fit AUC. **Commit.** `git commit -m "feat(hospitality): case-replay backtest and fit AUC"`

**P0 checkpoint:** run `python -m scripts.hospitality.cli run-p0`, which chains `ingest-sla → snapshot-pending → ingest-dohmh → resolve → window → websites → crawl → labels → score → recall → backtest`. Add `run-p0` as the final step of this task. Then run `pytest --cov=scripts -q` and `ruff check . && ruff format --check .`. All must pass before starting P1.

---

# P1: Day 3. Discovery, contacts, drafts, events, report

### Task 18: Exa client

**Files:** Create `scripts/hospitality/discover/__init__.py`, `discover/exa.py`. Test `tests/hospitality/test_exa.py`.

**Rationale.**
- *Purpose:* semantic search and find-similar for press and lookalikes (spec §6.13).
- *Why this way:* a thin `BaseAPIClient` subclass gets shared retry and 429 handling plus the
  budget. Alternative: the Exa SDK (another dependency, same calls).

**Interfaces:**
- Produces:
  - `ExaResult(url: str, title: str, published_date: date | None, text: str | None)`, frozen; in `models.py`.
  - `ExaClient(api_key: str, budget: CallBudget)`:
    - `.search(query: str, *, num_results: int = 10, start_published_date: date | None = None, include_text: bool = True) -> list[ExaResult]`, which POSTs `https://api.exa.ai/search`.
    - `.find_similar(url: str, *, num_results: int = 10, exclude_source_domain: bool = True) -> list[ExaResult]`, which POSTs `/findSimilar`.
  - Header `x-api-key`.

- [ ] **Step 1: Failing tests:** request body fields (`query`, `numResults`, `startPublishedDate` in ISO format, `contents.text` when `include_text`), result parsing, and the budget hard stop.
- [ ] **Step 2: FAIL. Step 3: Implement. Verify the request field names against Exa's current API docs and note the doc date in the docstring.** *Why: written from memory; a wrong field silently returns unfiltered results.*
- [ ] **Step 4: PASS. Step 5: Commit.** `git commit -m "feat(hospitality): Exa search and findSimilar client"`

### Task 19: Press discovery → signals, new venues, group evidence

**Files:** Create `scripts/hospitality/discover/press.py`. Test `tests/hospitality/test_press.py`.

**Rationale.**
- *Purpose:* catch announced openings, second locations and people moves, including venues not
  yet in any license file.
- *Why it matters:* it raises recall and is the main source of group evidence and alumni edges.
- *Why this way:* Exa search (date-filtered), then one structured LLM extraction per article,
  then deterministic matching to the universe.
  - Unmatched announced venues become new `Venue`s with ID `v:press:{hash}`. *Why:
    recall-first, a press-only opening is still a lead.*
  - Alternative: RSS only (misses the long tail).

**Interfaces:**
- Consumes: `ExaClient`, `llm.structured`, `Venue`, `Group`, `GroupEvidence`, `name_similarity`, `normalize_address`
- Produces:
  - `PRESS_QUERIES: tuple[str, ...]`, exactly: `("New York restaurant group opening second location", "chef opening new restaurant Manhattan Brooklyn", "restaurant opening soon New York liquor license", "hospitality group new restaurant New York hotel partnership", "executive chef leaves to open New York restaurant", "new general manager New York restaurant group")`
  - `PressPerson(name: str, role: str, prior_employers: tuple[str, ...])`, `PressVenue(name: str, address_or_area: str, status: Literal["announced","opening_soon","opened"], expected_open: str | None, group_name: str | None)`, `PressFacts(venues: tuple[PressVenue, ...], people: tuple[PressPerson, ...], hotel_partner: str | None)`, all frozen; in `models.py`.
  - `extract_press(text: str, url: str) -> PressFacts` (via `structured`, role `extract`)
  - `press_to_records(facts: PressFacts, url: str, published: date | None, venues: Sequence[Venue], groups: Sequence[Group], alumni_employers: frozenset[str]) -> tuple[list[Signal], list[Venue], list[GroupEvidence]]`. It emits:
    - `press_opening` for each venue;
    - `hotel_partnership` when a hotel partner is present;
    - `role_hire` / `new_gm` for people;
    - `alumni_edge` when a person's prior employer is in `alumni_employers` (config: `Eleven Madison Park`, `Make It Nice`, `Union Square Hospitality Group`, `Major Food Group`, `Momofuku`, `The Corner Store`, `Thomas Keller Restaurant Group`);
    - `GroupEvidence(resolution="press")` linking venues that share a `group_name`.

- [ ] **Step 1: Failing tests** with a fixture article text and a mocked `structured`: a known venue matched, an unknown venue created as `v:press:*`, an alumni edge emitted, and a group evidence item linking two venues with the same `group_name`.
- [ ] **Step 2: FAIL. Step 3: Implement. Step 4: PASS.**
- [ ] **Step 5: CLI `press --days 120`.** It runs the queries (budgeted), extracts, saves signals, venues and group evidence, then re-runs `merge_groups` and `score`. **Commit.** `git commit -m "feat(hospitality): press discovery to signals, venues and group evidence"`

### Task 20: Lookalikes from customer seeds

**Files:** Create `scripts/hospitality/discover/lookalikes.py`. Test `tests/hospitality/test_lookalikes.py`.

**Rationale.**
- *Purpose:* find groups shaped like those that bought (working backwards, spec §6.13).
- *Why this way:* `find_similar` seeded with customer sites and press URLs. Results resolve to
  venues by domain, and each hit becomes a `lookalike` signal with a low prior (0.10), so it
  ranks rather than dominates. Alternative: an LLM brainstorm of "similar restaurants" (not
  grounded in anything).

**Interfaces:**
- `lookalike_signals(exa: ExaClient, seeds: Sequence[CustomerLabel], venues: Sequence[Venue], now: datetime, per_seed: int = 10) -> list[Signal]`. Seeds without a domain are skipped. Results whose domain is a known customer's are dropped. Unresolved domains are logged for manual review, and no venue is invented. *Why no invention here, unlike press: a similar website isn't evidence that a venue exists in NYC.*

- [ ] **Steps:** failing test (a customer domain is dropped, a matched domain becomes a signal with `evidence_ref` = seed URL → result URL) → FAIL → implement → PASS → CLI `lookalikes` → commit `feat(hospitality): Exa lookalikes from customer seeds`.

### Task 21: Contacts waterfall (team page → Hunter)

**Files:** Create `scripts/hospitality/contacts/__init__.py`, `contacts/waterfall.py`. Test `tests/hospitality/test_contacts.py`.

**Rationale.**
- *Purpose:* named owners/GMs and reachable channels for the top 25 groups.
- *Why this way:* cheapest first (spec §6.6).
  1. Firecrawl `map_site` finds `/team|/about|/story|/people` pages.
  2. Firecrawl `extract`, or a fetch plus `structured`, pulls `{name, role}`.
  3. Hunter email-finder `(domain, first, last)` gets the email; accept confidence ≥ 70.
  4. Also capture the Instagram handle and phone.

  Apollo is skipped, per the research (thin for independent owners).

**Interfaces:**
- `HunterClient(api_key: str, budget: CallBudget)` with `.find_email(domain: str, first: str, last: str) -> tuple[str | None, float | None]`
- `team_members(site_url: str, firecrawl: FirecrawlClient, budget: CallBudget) -> list[tuple[str, str]]`
- `find_contacts(account: ScoredAccount, venues: Sequence[Venue], *, firecrawl: FirecrawlClient, hunter: HunterClient, budgets: dict[str, CallBudget]) -> list[Contact]`. Role priority for the email lookup: owner/founder/partner > director of operations > GM > chef. At most 2 email lookups per group.

- [ ] **Steps:** failing tests (role ordering, the confidence threshold, the budget stop, no email without a domain) → FAIL → implement → PASS → CLI `contacts --top 25` → commit.

### Task 22: Clay push and CSV import

**Files:** Create `scripts/hospitality/contacts/clay.py`. Test `tests/hospitality/test_clay.py`.

**Rationale.**
- *Purpose:* show SignalForce plugging into Magic's Clay workflow (spec §6.13).
- *Why this way:* a webhook push of rows (`group_id`, name, domain, priority, top evidence)
  plus a CSV import back (Concern 9). Alternative: build a callback endpoint (needs hosting and
  auth; post-meeting).

**Interfaces:**
- `clay_rows(accounts: Sequence[ScoredAccount], venues: Sequence[Venue], contacts: Sequence[Contact]) -> list[dict[str, str]]`
- `push_to_clay(webhook_url: str, rows: Sequence[dict[str, str]], budget: CallBudget) -> int`
- `import_clay_csv(path: Path) -> list[Contact]`, with columns `group_id, name, role, email, email_confidence`

- [ ] **Steps:** failing tests (row shape includes `top_evidence`; customers never pushed; CSV round-trip) → FAIL → implement → PASS → CLI `clay-push --top 25` / `clay-import <csv>` → commit.

### Task 23: Evidence-linked drafter and judge

**Files:** Create `scripts/hospitality/messages/__init__.py`, `messages/drafter.py`, `messages/judge.py`. Test `tests/hospitality/test_drafts.py`.

**Rationale.**
- *Purpose:* produce messages Magic would be proud to receive, where every factual claim
  points at a stored evidence item.
- *Why it matters:* a wrong fact to an owner burns the account (spec §5). Verification is
  limited to what we say, and this is that check.
- *Why this way:* the grounding check is **deterministic**: a claim sentence with no evidence
  ID, or an unknown one, fails before any LLM judge runs. Then the LLM judge applies Blueprint's
  rubric. Alternative: an LLM-only judge (it can be talked into approving fabrications; Review
  Focus 5).

**Interfaces:**
- `Angle = Literal["opening","people_change","platform_switch","relationship","private_events"]`
- `DraftSentence(text: str, evidence_ids: tuple[str, ...], is_claim: bool)`, `Draft(draft_id: str, group_id: str, contact_id: str | None, angle: Angle, subject: str, sentences: tuple[DraftSentence, ...])`, `Judgement(score: float, hyper_specific: bool, factually_grounded: bool, non_obvious: bool, deletion_reason: str, what_would_make_me_reply: str, grounding_violations: tuple[str, ...], passed: bool)`, all frozen; in `models.py`.
- `choose_angles(signals: Sequence[Signal]) -> list[Angle]`:
  - opening family → `opening`
  - `role_hire`/`new_gm` → `people_change`
  - `platform_switch`/`stack_fragmented` → `platform_switch`
  - `alumni_edge` → `relationship`
  - `private_events`/`tripleseat_resy` → `private_events`
- `draft(account: ScoredAccount, evidence: Sequence[Signal], contact: Contact | None, angle: Angle) -> Draft` (via `structured`, role `draft`). The system prompt includes the voice rules: ≤ 4 sentences, no product pitch in the first sentence, end with a question about their situation, never invent numbers.
- `grounding_check(draft: Draft, evidence_ids: set[str]) -> tuple[str, ...]`
- `judge(draft: Draft, evidence: Sequence[Signal]) -> Judgement`: `passed = not violations and score >= 7.0`.

- [ ] **Step 1: Failing tests.**

```python
def test_claim_without_evidence_fails_grounding():
    d = make_draft(sentences=(DraftSentence(text="You opened Oriana in May.", evidence_ids=(), is_claim=True),))
    assert grounding_check(d, {"press_opening:v:o:2026-05-01"}) == ("sentence 0: claim without evidence",)

def test_unknown_evidence_id_fails_grounding():
    d = make_draft(sentences=(DraftSentence(text="x", evidence_ids=("made-up",), is_claim=True),))
    assert grounding_check(d, {"a"}) == ("sentence 0: unknown evidence id made-up",)

def test_judge_never_passes_with_violations(mocker):
    mocker.patch("scripts.hospitality.messages.judge.structured", return_value=fake_llm_judgement(score=9.5))
    d = make_draft(sentences=(DraftSentence(text="x", evidence_ids=(), is_claim=True),))
    assert judge(d, []).passed is False
```

- [ ] **Step 2: FAIL. Step 3: Implement. Step 4: PASS.**
- [ ] **Step 5: CLI `draft --top 10`.** Three angles where available. It saves drafts and judgements and prints pass rates. **Commit.**

### Task 24: Event registry and lineup extraction

**Files:** Create `scripts/hospitality/events/__init__.py`, `events/registry.py`, `events/extract.py`, `examples/magic-loyalist/events.yaml`. Test `tests/hospitality/test_events_extract.py`.

**Rationale.**
- *Purpose:* the next 12 months of NYC-relevant events and who appears at them (spec §6.12).
- *Why this way:*
  - A hand-curated registry seeded from research. The NRA Show (May 22–25 2027, Chicago) is
    included as the trade-show contrast.
  - Exa event discovery proposes additions, and a human approves them, per "propose everything
    else".
  - Lineups come from Firecrawl extraction plus `structured`.
  - Alternative: scraping gated event apps (forbidden).

**Interfaces:**
- `EventType = Literal["trade_show","curated_conference","festival","awards","local_meetup","magic_dinner"]`
- `Event(event_id: str, name: str, start: date, end: date, city: str, event_type: EventType, cost_usd: float, lineup_urls: tuple[str, ...])`, `Role = Literal["speaker","panelist","festival_chef","award_nominee","exhibitor_staff","sponsor","past_recap"]`, `EventAppearance(event_id: str, person: str, restaurant: str, role: Role, source_url: str)`, all frozen; in `models.py`.
- `load_events(path: Path) -> list[Event]`
- `extract_appearances(event: Event, firecrawl: FirecrawlClient, budget: CallBudget) -> list[EventAppearance]`

- [ ] **Step 1: Write `events.yaml`** with the events whose dates can be verified at build time. Unverified dates get `start: null`, plus a `verify:` note, and are excluded from ranking. *Why: a wrong event date sends a rep to an empty room.*
- [ ] **Steps:** failing tests (YAML load, unverified events excluded, extraction maps roles) → FAIL → implement → PASS → CLI `events-extract` → commit.

### Task 25: Event ranking and meeting lists

**Files:** Create `scripts/hospitality/events/rank.py`. Test `tests/hospitality/test_events_rank.py`.

**Rationale.**
- *Purpose:* answer "which rooms, and who to meet there" (spec §6.12).
- *Why this way:* expected qualified meetings per dollar, with explicit priors (role attendance,
  event-type meeting rate) that the loop later updates. Alternative: rank by attendee count
  (rewards big chain-heavy trade shows, the opposite of the hypothesis).

**Interfaces:**
- `ATTEND_PRIOR: dict[str, float]`, exactly `{"speaker": 0.95, "panelist": 0.95, "festival_chef": 0.95, "award_nominee": 0.9, "exhibitor_staff": 0.7, "sponsor": 0.6, "past_recap": 0.35}`
- `MEETING_RATE_PRIOR: dict[str, float]`, exactly `{"curated_conference": 0.15, "festival": 0.08, "awards": 0.05, "trade_show": 0.03, "local_meetup": 0.20, "magic_dinner": 0.50}`
- `EventScore(event_id: str, expected_meetings: float, score_per_dollar: float, matched_people: int)`, `MeetingTarget(event_id: str, person: str, group_id: str | None, p_attend: float, priority: float, in_window: bool, is_customer: bool, reason: str)`, both frozen; in `models.py`.
- `match_appearance(app: EventAppearance, venues: Sequence[Venue]) -> str | None`: restaurant name similarity ≥ 0.85 → the venue's `group_id`.
- `rank_events(events: Sequence[Event], appearances: Sequence[EventAppearance], accounts: dict[str, ScoredAccount], venues: Sequence[Venue]) -> list[EventScore]`:
  - `expected = Σ ATTEND_PRIOR[role] * priority(group or 0.05 if unmatched) * MEETING_RATE_PRIOR[type]`
  - `per_dollar = expected / max(cost, 1)`
- `meeting_list(event: Event, appearances: Sequence[EventAppearance], accounts: dict[str, ScoredAccount], venues: Sequence[Venue]) -> list[MeetingTarget]`: sorted by `p_attend * priority` descending. Customers are kept but flagged `is_customer=True` with reason `"warm intro / co-host"` and placed after prospects. *Why kept: a customer attending is the best intro path; Review Focus 4 forbids cold-targeting them, not knowing about them.*

- [ ] **Steps:** failing tests with exact expected values:
  - a single speaker (0.95) from a group with priority 0.4 at a curated conference (0.15) costing $500 gives expected 0.057 and per-dollar 0.000114;
  - customers sort after prospects.

  Then FAIL → implement → PASS → CLI `events-rank` → commit.

### Task 26: Demo report

**Files:** Create `scripts/hospitality/report.py`. Test `tests/hospitality/test_report.py`.

**Rationale.**
- *Purpose:* one document for the meeting, generated from the store so every number is
  reproducible.
- *Why this way:* Markdown under `out/magic/` (gitignored; Concern 10). It can become a
  published page afterwards if you want. Alternative: hand-built slides (numbers drift from
  the data).

**Interfaces:**
- `build_report(store: DocStore, cfg: HospitalityConfig, out_dir: Path) -> Path`. Sections, in order:
  1. Universe and location counts (with the possibly-same link count and the group-coverage caveat)
  2. Opening-timing curve (median, IQR, by stratum)
  3. Recall audit
  4. Head-to-head (with the fairness note)
  5. Backtests
  6. Stack distribution and Loyalist penetration
  7. Top 25 prospects with traces
  8. Contacts coverage and cost per verified contact
  9. Drafts with judge scores
  10. Event ranking and the top meeting list
  11. Limitations and assumptions (every `basis`/prior used)
  12. Questions for Magic (spec §10)

- [ ] **Steps:** failing test (a report built from a fixture store contains all 12 headers in order, and section 4 contains the hindsight note) → FAIL → implement → PASS → CLI `report` → commit `feat(hospitality): demo report`.

---

# P2: after the meeting (recommended deferral, Concern 1)

### Task 27: Sequencer state machine

`scripts/hospitality/outbound/sequencer.py`.
- `StepKind = Literal["email","call_task","instagram_dm_task","walk_in_task","dinner_invite","event_invite"]`
- `next_steps(state: SequenceState, now: datetime, cfg) -> list[Step]`

Rules:
- one active sequence per group;
- calls and walk-ins only in the 14:00–16:30 local window;
- suppression is always checked first.

*Why deferred: it has no real sends to drive it before Magic's stack is known; the spec diagram
covers it in the meeting.*

### Task 28: Reply classifier and routing

`outbound/replies.py`. `classify_reply(text: str) -> ReplyClass` (via `structured`, fixed categories from spec §6.9) and `route(reply_class) -> Action`. Unsubscribe and hard-no route to deterministic suppression.

### Task 29: Bayesian prior updates and the bandit

`loop/updates.py`.
- `beta_update(prior: SignalPrior, successes: int, trials: int, *, prior_strength: float = 20, max_step: float = 0.1, min_trials: int = 10) -> SignalPrior`
- `thompson_allocate(arms: dict[str, tuple[int, int]], n: int, rng) -> dict[str, int]`

Changes are versioned in a `prior_history` kind. *Why deferred: on simulated outcomes these
show code, not learning. They earn their place when the embed-appearance feed (spec §6.3a)
has weeks of real labels.*

### Task 30: Proposal engine (misses)

`loop/proposals.py`. `propose_from_misses(report: RecallReport, venues, sources) -> list[Proposal]`. For each missed opening, it records which available source carried evidence before opening (e.g. press, CB notice) and writes a human-approvable proposal. It never changes code or rules.

---

# Added after P1 (user request, 2026-11-16)

### Task 31: Culinary Agents source (hiring, opening-soon, group evidence)

Added by the user on 2026-11-16, after Task 26.

**Files:**
- Create: `scripts/hospitality/sources/culinary_agents.py`
- Modify: `scripts/hospitality/models.py` (new signal type + any parsed-record models), `scripts/hospitality/config.py`, `examples/magic-loyalist/hospitality.yaml`, `scripts/hospitality/cli.py`, `scripts/hospitality/scoring.py` only if a new signal type needs wiring
- Test: `tests/hospitality/test_culinary_agents.py`, fixtures in `tests/fixtures/hospitality/culinary_agents/`

**Rationale.**
- *Purpose:* culinaryagents.com is a hospitality job board with public company pages (name, description, location, sometimes a group with several locations), job postings, and "opening soon" / "hiring now" markers. It can feed three things the pipeline lacks a source for.
- *Why it matters:* `role_hire` and `new_gm` are declared signal types that almost nothing emits; the buying window is currently inferred only from liquor licenses; restaurant groups are mostly invisible in public records (plan Concern 4).
- *Why this way:* a deterministic HTML/JSON parser over a small, polite, budgeted fetch — no LLM needed for structured listing pages.

**Constraints specific to this task.**
- Terms of use: the site's user agreement appears to restrict automated data collection. So: the source is **disabled by default** (`culinary_agents.enabled: false` in config; the CLI command refuses to run unless enabled, with a message telling the operator to review culinaryagents.com/agreement first), fetches only pages robots.txt allows (the existing fetcher enforces robots), never touches `/users` or anything behind login, uses a hard per-run page budget from config (`budgets.culinary_agents`, default small, e.g. 40) via `CallBudget` spent BEFORE each fetch, and a polite delay between requests. No personal data about job seekers is collected — only employer-side facts.
- Tests never hit the network: parse saved fixtures. You MAY make a handful of polite live GETs (well under the default budget, with delays) while developing, solely to learn the page structure and save small trimmed fixtures; strip anything not needed.

**Interfaces (produce; adapt names to what the pages really contain):**
- `CAJob(company: str, company_url: str, title: str, location: str, posted: date | None, url: str)` and `CACompany(name: str, url: str, description: str, locations: tuple[str, ...], opening_soon: bool, hiring: bool, website: str | None)` — frozen models.
- `parse_job_search(html: str) -> list[CAJob]`, `parse_company(html: str, url: str) -> CACompany | None` — pure functions, tolerant of missing fields (skip and log an unparseable card, never crash).
- `fetch_nyc(cfg, budget, fetch=...) -> tuple[list[CAJob], list[CACompany]]` — NYC only.
- `to_signals(jobs, companies, venues, groups, today) -> tuple[list[Signal], list[GroupEvidence]]`:
  - match a company to a known venue/group with the existing normalization helpers (name similarity + neighbourhood/borough or website domain); a company that matches zero or several venues gets NO signal on an arbitrary venue (log it as an unmatched candidate);
  - senior/opening-team roles only: a General Manager posting → `new_gm`; Director of Operations, Events/Private Dining Manager, Opening team, Maître d'/Guest Relations/Reservations Manager and similar guest-facing leadership → `role_hire`; line-level roles (cook, server, dishwasher, barista…) emit nothing — restaurants hire constantly, so the role is the signal. The role lists live in config;
  - a company marked opening soon → new signal type `opening_soon` (add to `SignalType`, with a prior in config alongside the other priors, in the opening family so the per-venue dedupe from Task 14b folds it with license signals rather than double-counting);
  - a company page listing several locations → `GroupEvidence` for `merge_groups` (resolution kind consistent with the existing `GroupResolution` values; add one only if none fits);
  - every signal carries the Culinary Agents URL as `evidence_ref` and a human-readable `detail`.
- CLI: `culinary-agents` — refuses unless enabled; fetches, saves signals + evidence, re-runs group merge and score (follow the `press` command's pattern).

**Steps (TDD):**
- [ ] 1. Learn the real page structure with a few polite GETs; save trimmed fixtures.
- [ ] 2. Failing tests: parser on fixtures; line-level role emits nothing; GM → `new_gm`; opening-soon → `opening_soon` folded with a license signal on the same venue (no double count in `score_group`); ambiguous/unmatched company gets no signal; customer group never becomes a cold prospect because of these signals (customer gate holds); budget hard-stops before the fetch over the limit; command refuses when disabled; `/users` URLs never fetched.
- [ ] 3. Implement; run tests to green.
- [ ] 4. Wire CLI + config + yaml priors.
- [ ] 5. Full suite, ruff on touched files, commit: `feat(hospitality): Culinary Agents source for hiring and opening-soon signals`.
- Do NOT run the full live command against the site beyond the handful of structure-learning requests; the operator enables it after reviewing the terms.

---

## Self-review notes (done)

- **Spec coverage:**
  - §6.1 method split → Tasks 3–19 follow it.
  - §6.2 model → Task 1.
  - §6.3/6.3a signals and embed → Tasks 12–14.
  - §6.4 window → Task 9.
  - §6.5 scoring/backtest → Tasks 14 and 17.
  - §6.6 contacts → Task 21.
  - §6.7–6.9 outbound → P2, plus Concern 1.
  - §6.10 lifecycle → customer flag in Task 14; full lifecycle post-meeting.
  - §6.11 loop → recall audit (Task 15) is real; updates are P2.
  - §6.12 events → Tasks 24–25.
  - §6.13 tools → Tasks 10, 12, 18–22.
  - §7a benchmark → Task 16.
  - §8 demo → Task 26.
  - **Gap, accepted:** community-board notices and building permits (spec §3) have no task. They are per-board HTML and PDF scraping and don't fit the timebox. Task 30's miss analysis will show whether they're worth it.
- **Type consistency:** every model used across tasks is declared in `models.py` (Task 1, or added by the task that introduces it, noted inline).
- **Review Focus** items are each pinned by a test in Tasks 3, 5/9, 11, 13/14/25 and 16/23.
