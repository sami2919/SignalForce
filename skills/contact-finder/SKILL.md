---
name: contact-finder
description: Use when needing to find verified email addresses and LinkedIn profiles for decision-makers at target accounts, or when performing waterfall enrichment across multiple data providers
---

# Contact Finder

## Input

Company name + domain. Target title(s) — default to priority order from `config/gtm-context.md`:
1. Head of ML / Director of ML / VP ML
2. Head of AI / VP AI
3. Principal / Staff ML Engineer
4. VP Engineering / CTO (companies ≤100 employees)
5. Domain-specific senior IC roles (see `config/gtm-context.md` for ICP-specific titles)

## Waterfall Enrichment

Work top-to-bottom. Stop at first verified result per contact.

### Step 1: Apollo.io
- API: `POST https://api.apollo.io/v1/people/search` with `person_titles` + `organization_domains`
- Manual: apollo.io → Search → People → filter by domain + title

### Step 2: Hunter.io
- API: `GET https://api.hunter.io/v2/domain-search?domain={domain}&type=personal`
- Manual: hunter.io → Domain Search

### Step 3: Prospeo
- API: `POST https://api.prospeo.io/linkedin-email-finder` with LinkedIn URL
- Manual: prospeo.io → LinkedIn Email Finder → paste profile URL

### Step 4: PeopleDataLabs
- API: `GET https://api.peopledatalabs.com/v5/person/enrich?work_email={email}`
- Manual: pdl.com → Enrichment

### Step 5: ZeroBounce Validation (always run on final email)
- API: `GET https://api.zerobounce.net/v2/validate?email={email}`
- Statuses to accept: `valid`. Reject: `invalid`, `catch-all`, `unknown`.

## Output

```
## Contacts — [Company Name]

| Name | Title | Email | Source | Status |
|------|-------|-------|--------|--------|
| ...  | ...   | ...   | Apollo | valid  |

**LinkedIn Profiles:**
- [Name]: [URL]

**Enrichment gaps:** [any titles not found, note for manual outreach via LinkedIn]
```

If no verified email found after full waterfall: output LinkedIn URL and flag for manual connection request.
