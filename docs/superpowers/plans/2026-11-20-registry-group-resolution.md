# Registry Group Resolution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show which operator is behind each one-venue licence company, using the New York State company registry, and put a ranked hospitality-group view at the top of the report's prospect section.

**Architecture:** A cached, budgeted registry lookup for the licence companies behind the top cold prospects. A pure clustering step drops law-firm and registered-agent records and groups companies by a shared person or office. A display-only report subsection ranks named groups and clusters by their strongest member. Scoring and stored groups are not touched.

**Tech Stack:** Python 3.11, frozen Pydantic models, the existing `SocrataClient`, `DocStore`, `CallBudget`, pytest with mocked HTTP.

**Spec:** `docs/superpowers/specs/2026-11-20-registry-group-resolution-design.md`

## Global Constraints

- **Dataset:** `n9v6-gdp6` on `data.ny.gov`.
- **Evidence link:** `https://data.ny.gov/resource/n9v6-gdp6.json?dos_id=<dos_id>`.
- **Request budget:** `budgets.registry`, default 600 requests, spent BEFORE each request.
- **Agent filter config:**
  - `registry.agent_markers` defaults: corporation service, ct corporation, registered agent, incorp, legalinc, northwest registered, united states corporation agents, national registered, cogency, llp, l.l.p., esq, law office, law firm, attorneys, pllc, p.c.
  - `registry.max_companies_per_address`: 25.
- **CLI:** `registry --top 300`, which needs no key.
- **Name matching:** exact after normalisation, never fuzzy.
- **Display-only:** no change to scores, to stored `groups`, or to the existing top-25 output.
- **Customers:** a cluster containing a customer under `labels.current_customers` is excluded from the ranking.
- **Links:** every registry name or address shown carries its registry link.
- **Tests:** mock all HTTP.
- **Style:** ruff only on touched files; commits end with the repo's trailer lines.

## Review Focus

1. **One law firm behind many unrelated companies.** It must never form a cluster, whether caught by the keyword list or by the per-address count (Task 2 test).
2. **A company whose process name is its own name.** This must cluster by office address, not by "person" (Task 2 test).
3. **The registry returns several records for one name.** Take the most recent `initial_dos_filing_date` and keep a note (Task 1 test).
4. **A Socrata outage or 429 mid-run.** Lookups already made are saved, and the run reports `stopped` instead of crashing (Task 3 test).
5. **Addresses that differ only in punctuation or suite formatting** ("16 East 40th Street" vs "16 E 40TH ST"). They must normalise to one office key (Task 2 test).

---

### Task 1: Registry lookup with cache and budget

**Files:**
- Create: `scripts/hospitality/sources/registry.py`
- Modify:
  - `scripts/hospitality/models.py`: add `RegistryRecord`.
  - `scripts/hospitality/config.py`: add `RegistryConfig` with `agent_markers` and `max_companies_per_address`, plus a `registry` field on `HospitalityConfig`.
  - `examples/magic-loyalist/hospitality.yaml`: add a `registry:` block and `budgets.registry: 600`.
- Test: `tests/hospitality/test_registry.py`

**Interfaces:**
- Consumes:
  - `SocrataClient(domain).rows(dataset_id, *, where=..., select=...)`;
  - `CallBudget.spend()`;
  - `DocStore.save/load`.
- Produces:
  - `RegistryRecord(name_key: str, legal_name: str, found: bool, dos_id: str | None, entity_name: str | None, filed: date | None, process_name: str | None, process_address: str | None, process_zip: str | None, note: str = "")`
  - `normalize_company(name: str) -> str`
  - `lookup_companies(names: Sequence[str], client, budget: CallBudget, store: DocStore) -> list[RegistryRecord]`. It skips names already cached in kind `registry_records`, saves each new lookup as it goes, and lets `BudgetExceeded` propagate after saving.
  - `count_companies_at(address: str, zip_code: str, client, budget, store) -> int`, cached in kind `registry_address_counts`.
  - `registry_link(dos_id: str) -> str`

- [ ] **Step 1: Write failing tests.**
  - `test_normalize_company_equates_llc_and_inc_forms`: `normalize_company("Rip Raf, L.L.C.") == normalize_company("RIP RAF LLC")`, `normalize_company("HTNY 1 Inc.") == normalize_company("HTNY 1 INC")`, and `normalize_company("Rip Raff LLC") != normalize_company("Rip Raf LLC")`.
  - `test_lookup_returns_found_and_not_found`: a fake client returns one row for RIP RAF LLC (process name "Matthew Maddy", address "716 Marcy Avenue", zip "11206") and none for HTNY 1 INC. Both come back, with `found` True and False.
  - `test_several_matches_take_newest_filing_and_note_it`.
  - `test_cached_names_make_no_request`: a second call with the same names makes 0 client calls.
  - `test_budget_stops_before_the_request_over_the_limit`: with budget 1 and 2 names, there is 1 client call, the first record is saved, and `BudgetExceeded` is raised.
  - `test_count_companies_at_is_cached`.
  - `test_registry_link_format`.
- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/hospitality/test_registry.py -q --no-cov`. Expected: FAIL, the import fails.
- [ ] **Step 3: Implement** the interfaces above.
  - Query with `where="current_entity_name = '<UPPER EXACT>'"`, escaping single quotes. Then compare `normalize_company` on the results, because the registry stores punctuation variants.
  - `count_companies_at` uses `select="count(*)"` with a `where` on `dos_process_address_1` and `dos_process_zip`.
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Commit** `feat(hospitality): cached, budgeted NY company registry lookup`.

### Task 2: Agent filter and operator clustering

**Files:**
- Create: `scripts/hospitality/resolve/operators.py`
- Modify: `scripts/hospitality/models.py`: add `OperatorCluster`.
- Test: `tests/hospitality/test_operators.py`

**Interfaces:**
- Consumes:
  - `RegistryRecord`;
  - `RegistryConfig`;
  - a `counts: Mapping[str, int]` keyed by `office_key(...)`.
- Produces:
  - `office_key(address: str, zip_code: str) -> str`. Uses `resolve/normalize.py`'s address normaliser, so "16 East 40th Street" and "16 E 40TH ST" give one key.
  - `is_agent(record: RegistryRecord, cfg: RegistryConfig, counts: Mapping[str, int]) -> bool`
  - `operator_key(record: RegistryRecord) -> tuple[Literal["person", "office"], str] | None`. It returns "person" when the process name differs from the entity's own name (compared by `normalize_company`), otherwise "office". It returns None when the record is not found or has no process data.
  - `OperatorCluster(cluster_id: str, kind: Literal["named_group", "person", "office"], label: str, group_ids: tuple[str, ...], members: tuple[RegistryRecord, ...])`
  - `cluster_operators(records_by_group: Mapping[str, Sequence[RegistryRecord]], group_names: Mapping[str, str], named_group_ids: frozenset[str], cfg: RegistryConfig, counts: Mapping[str, int]) -> list[OperatorCluster]`. Only clusters with 2 or more distinct groups, or a named group, are returned.
  - Label order: a member group's name if its id is in `named_group_ids`; else "<Process Name> (operator)"; else "Office at <address>".

- [ ] **Step 1: Write failing tests.**
  - `test_agent_markers_are_dropped`: "CORPORATION SERVICE COMPANY" and "c/o golenbock eiseman assor bell & peskoe llp" are both agents.
  - `test_over_shared_address_is_dropped`: counts of 26 against a max of 25 gives an agent.
  - `test_same_person_clusters_across_groups`: two groups, each with a "Matthew Maddy" record, give one cluster of kind person with 2 group_ids.
  - `test_same_office_clusters`: a record whose process name is its own entity name gives an office key. "16 East 40th Street 10016" and "16 E 40TH ST 10016" share a key and cluster.
  - `test_law_firm_never_clusters`: 3 groups sharing only a law-firm record give no cluster.
  - `test_named_group_label_wins`.
  - `test_single_unnamed_group_is_not_a_cluster`.
- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/hospitality/test_operators.py -q --no-cov`. Expected: FAIL.
- [ ] **Step 3: Implement** the interfaces above.
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Commit** `feat(hospitality): cluster licence companies by the operator behind them`.

### Task 3: `registry` CLI command

**Files:**
- Modify: `scripts/hospitality/cli.py`: add the `registry` subcommand and a function `registry(top: int = 300) -> dict[str, int | str]`.
- Test: `tests/hospitality/test_registry_cli.py`

**Interfaces:**
- Consumes:
  - `rank_prospects`;
  - `current_customers`;
  - the stored `scores`, `venues`, `groups`, `licenses`;
  - Task 1 and Task 2.
- Produces:
  - Stored kinds `registry_records` and `registry_address_counts`.
  - The summary keys: `prospect_groups`, `companies`, `looked_up`, `found`, `not_found`, `agents`, `clusters`, `requests`, `stopped`.

- [ ] **Step 1: Write failing tests.** Use a temp store with 3 prospect groups whose venues' licences have legal names, and a fake client.
  - `test_registry_looks_up_licence_companies_of_top_prospects_only`: `top=2` looks up only the companies of the first 2 ranked groups.
  - `test_registry_skips_customers`.
  - `test_registry_reports_stopped_on_budget_and_keeps_lookups`.
  - `test_registry_reports_stopped_on_api_error_and_keeps_lookups`: a fake client raising `APIError` on the second name.
- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/hospitality/test_registry_cli.py -q --no-cov`. Expected: FAIL.
- [ ] **Step 3: Implement** it.
  - Take the venue `license_ids` → `LicenseRecord.legal_name` for every venue of each top group, de-duplicated by `normalize_company`.
  - Count addresses only for found records not already caught by a marker.
  - Print the summary in the CLI's established style.
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Commit** `feat(hospitality): registry command for the top prospects`.

### Task 4: Hospitality group view in the report

**Files:**
- Modify: `scripts/hospitality/report.py`. Add `_groups_view(...) -> list[str]` and call it at the top of section 7, ahead of `_prospects`'s output, as `### Hospitality groups (ranked)`. Section numbering stays at 12, so existing section tests keep their numbers.
- Test: `tests/hospitality/test_report.py`, adding tests.

**Interfaces:**
- Consumes:
  - `cluster_operators`, `is_agent`, `operator_key`, `registry_link`;
  - the stored `registry_records` and `registry_address_counts`;
  - the scored `accounts`, `names` and `signals` `build_report` already loads.
- Produces: report text only.

**Content of the view:**
- **Ranking:** named groups and clusters together, ranked by the highest member `priority`, with the same tie-break as the top 25. Show the top 15.
- **Each entry shows:**
  - its label and kind ("named group", "same person", "same office");
  - its member licence companies, each with "behind it: <person or office> ([registry](link))";
  - its venues with addresses;
  - its 3 strongest contributing signals with evidence.
- **Unresolved companies:** after the clusters, a line listing licence companies among the top prospects marked "operator unresolved (agent or law firm)" or "operator unresolved (not found)", with counts.
- **Coverage line:** looked up, found, agents, not found, clusters.
- **No registry data stored:** the view says "Not run: registry" with the command to run, and section 7 is otherwise unchanged.

- [ ] **Step 1: Write failing tests.**
  - `test_groups_view_ranks_by_strongest_member_and_links_every_registry_name`.
  - `test_groups_view_excludes_customer_clusters`.
  - `test_groups_view_lists_unresolved_companies_with_reason`.
  - `test_groups_view_not_run_without_registry_data`.
  - `test_top25_unchanged_with_groups_view`: section 7's text after the view equals the text produced without registry data.
- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/hospitality/test_report.py -q --no-cov`. Expected: the new tests FAIL.
- [ ] **Step 3: Implement** `_groups_view`.
- [ ] **Step 4: Run** the same command. Expected: PASS. Then run the full suite: `.venv/bin/python -m pytest --ignore=tests/web -q`, which must be all green.
- [ ] **Step 5: Commit** `feat(hospitality): ranked hospitality-group view in the report`.

### Task 5: Supervised live run

- [ ] **Step 1:** In the session holding the full store, run `registry --top 300` and read the summary. Expected: `requests` at or under 600, and no crash.
- [ ] **Step 2:** Run `report`. Read the group view. List the top 15 and every "same office" and "same person" cluster, so a human can check none is a law firm or a coincidence.
- [ ] **Step 3:** Commit no data. Push the branch.
