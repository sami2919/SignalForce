# Who is behind each licence company: state registry lookup and a group view

Date: 2026-11-20. Status: design for approval. Builds tonight (option B); the full resolver (option C) follows after the interview.

## Intent

Magic sells Loyalist to hospitality groups, not to single restaurants. The pipeline's accounts are mostly one-venue licence companies ("Rip Raf LLC", "Wonderworth LLC") because each venue usually holds its liquor licence through its own company. A rep can't sell to "Rip Raf LLC"; they sell to the operator behind it.

For the interview tomorrow, the ranked list must show hospitality groups first. Each group must show its licence companies and who is behind each one, with evidence a person can click.

## What exists today

- Groups are formed from a shared legal name, a shared website domain, Culinary Agents "Part of" lines and press (`scripts/hospitality/resolve/groups.py`). About 47 named groups exist; almost everything else is a single licence company.
- Scoring works per group (`scoring.py`), and the report lists the top 25 scored groups with traces (`report.py`, section 7).
- New York State publishes its company registry on the same open-data site as the licences: dataset `n9v6-gdp6` on data.ny.gov ("Active Corporations"). Each record has `current_entity_name`, `dos_id`, `initial_dos_filing_date`, `dos_process_name` and `dos_process_address_1`, `_2`, `_city`, `_state`, `_zip`. The process name and address are who receives legal papers for the company.
- Tested by hand tonight:

  | Licence company | Registry says | Meaning |
  |---|---|---|
  | Rip Raf LLC | Matthew Maddy, 716 Marcy Ave | A person: the operator |
  | 65th Street Restaurant LLC | itself, 16 East 40th Street | An office address |
  | Wonderworth LLC | a law firm | Nothing on its own |
  | Cosme NY LLC | Corporation Service Company | A registered agent: nothing |
  | HTNY 1 Inc | no match | Not found |

## Goals

1. Look up the registry record for the licence companies behind the top cold-prospect groups (default the top 300), free, cached and budgeted.
2. Discard records that only point at a law firm or registered-agent service.
3. Cluster licence companies that share a real person, or a real office address, into one operator group.
4. Add a ranked group view to the report: the hospitality groups first, each with its licence companies, who is behind each one (person or office, with a link to the registry record), its venues, and what's new (its strongest signals).
5. Keep the existing top-25 section, unchanged, as the venue-level evidence.

## Non-goals (tonight)

- No change to scoring or to the stored groups. The clustering is a display layer: a group's rank is its strongest member's priority. Merging into the real groups, so scoring works at group level, is option C.
- No website footers, press, community-board agendas or Claude. Those are option C.
- No lookups beyond the top-N prospects, and no inactive-company dataset.

## Anti-goals (failures even if it runs)

- A law firm or agent service shown as a "group". One firm can represent hundreds of unrelated companies, so this would merge strangers.
- An existing Loyalist customer appearing in the group ranking as a prospect.
- A registry name or address shown without a link to its record.
- Any change to the existing scores or top-25 section.

## Approaches considered

- **A. Show only the ~47 groups already known.** No new data, about an hour, but a short list that doesn't show who is behind the one-venue companies. Rejected: it misses half the ask.
- **B. State registry lookup plus a display-only group view (chosen for tonight).** Free public data that already names operators for part of the list, and low risk because scoring is untouched. The cost is partial coverage, and some groups are named after a person rather than a brand.
- **C. Full resolver (after the interview).** B plus website footers, press and community-board agendas, feeding the real group merge. Best coverage; too big for one night.

## Design

### Lookup

- New module `scripts/hospitality/sources/registry.py`, using the existing Socrata client (`sources/socrata.py`) and a `CallBudget` (config key `budgets.registry`, default 600 requests, spent before each request).
- Match a licence company by exact normalised name: uppercase, collapse punctuation and spaces, and equate `L.L.C.`, `LLC`, `INC.` and `INC`. No fuzzy matching: a near-miss name is a different company.
  - Zero matches: "not found".
  - Several matches: take the most recent filing and note it.
- Cache every lookup, found or not, in a new DocStore kind `registry_records` keyed by the normalised name, so a rerun makes no repeat request.
- The evidence link for a record is `https://data.ny.gov/resource/n9v6-gdp6.json?dos_id=<dos_id>`.

### Filtering out agents and law firms

A record is not operator evidence when any of these is true:

- **Agent or law-firm words:** its process name or address contains a word from a config list, `registry.agent_markers`. Defaults: corporation service, ct corporation, registered agent, incorp, legalinc, northwest registered, united states corporation agents, national registered, cogency, llp, l.l.p., esq, law office, law firm, attorneys, pllc, p.c.
- **Too many companies at one address:** its process address is shared by more than `registry.max_companies_per_address` companies in the whole registry (default 25). The count is one count query per distinct address, cached in `registry_address_counts`.

### Clustering

For each kept record:

- **A person:** if the process name differs from the company's own name and isn't the company, the key is the normalised person name.
- **An office:** otherwise the key is the normalised address line plus ZIP.

Licence companies with the same key form an operator cluster, and a cluster may span several existing groups. Its label is chosen in this order:

1. An existing named group among its members, from the job board, website domain or seed list.
2. "<Person> (operator)" for a person key.
3. "Office at <address>" for an office key.

If any member group is a customer under `labels.current_customers`, the whole cluster is treated as a customer and excluded from the ranking.

### The group view in the report

A new section, "Hospitality groups (ranked)", is placed before the venue-level top 25.

- It lists clusters and named groups together, ranked by the highest member priority. Ties break the same way as the top 25.
- **Each entry shows:**
  - the group label;
  - how it was identified: named group, shared person, or shared office;
  - each licence company, with the person or office behind it and its registry link;
  - the venues and addresses;
  - the 3 strongest signals with evidence.
- **Groups of one:** licence companies with no usable record are listed after the clusters, marked "operator unresolved (agent or law firm)" or "operator unresolved (not found)".
- **Coverage line:** companies looked up, found, discarded as agent or law firm, not found, and the clusters formed.

### CLI

- `registry --top 300`: look up, cache and print the counts. Then `report` shows the view. It needs no key.

## Tests (written first)

- **Name matching:** normalisation equates `L.L.C.` with `LLC`, and a near-miss name doesn't match.
- **Filtering:** an agent-marker record and an over-shared address are both discarded, and the count query is cached.
- **Clustering:** two companies with the same person cluster, two with the same office cluster, and two sharing only a law firm do not.
- **Labels:** a named group wins over a person label.
- **Customers:** a cluster containing a customer is excluded.
- **Budget:** the request over the budget is never sent.
- **Cache:** a rerun makes no requests.
- **Report:** the section ranks by the strongest member, every name and address has a registry link, the scores and top-25 section are unchanged, and the coverage line adds up.

## Left to the builder

The exact normalisation code, the record-shape fields stored, and the report layout details, within the rules above.

## After the interview (option C, outline)

1. Website footers and "our restaurants" pages.
2. Press about the opening.
3. Community-board liquor-licence agendas.
4. Feed the clusters into `merge_groups` so scoring, contacts and drafts work at group level.
5. Contacts at group level: founder, operations, guest experience.
