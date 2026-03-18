# Setup Guide — rl-gtm-engine

End-to-end setup from a fresh machine to a running signal pipeline. This guide covers local Python setup, all API accounts, n8n workflow configuration, HubSpot, and Instantly.ai. Budget ~2 hours for a full first-time setup.

---

## 1. Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.11+ | 3.12 works; 3.10 does not |
| Claude Code | Latest | Install: `npm install -g @anthropic-ai/claude-code` |
| n8n | v1.30+ | Self-hosted or n8n Cloud |
| Git | Any | For cloning the repo |

---

## 2. Installation

```bash
# Clone the repository
git clone https://github.com/your-org/rl-gtm-engine.git
cd rl-gtm-engine

# Create a virtual environment
python3.11 -m venv .venv
source .venv/bin/activate          # macOS/Linux
# .venv\Scripts\activate           # Windows

# Install dependencies
pip install -r requirements.txt

# Copy the environment template
cp .env.example .env
```

Edit `.env` and fill in your API keys (see Section 3).

**Verify the install:**

```bash
# Run tests (all should pass without real API keys — HTTP is mocked)
pytest --cov=scripts --cov-report=term-missing -v

# Lint check
ruff check .
```

---

## 3. API Key Setup

### GitHub API (required)

- Sign up: https://github.com
- Create a Personal Access Token (classic): **Settings → Developer settings → Personal access tokens → Tokens (classic)**
- Required scopes: `public_repo`, `read:org`
- Free tier: 5,000 requests/hour authenticated (60/hour unauthenticated — not sufficient)
- `.env` variable: `GITHUB_TOKEN=ghp_...`

### Anthropic API (required for email generation)

- Sign up: https://console.anthropic.com
- Create an API key under **API Keys**
- Free tier: None — pay-as-you-go. Budget ~$30-50/month for this pipeline.
- `.env` variable: `ANTHROPIC_API_KEY=sk-ant-...`

### Apollo.io (required for contact enrichment)

- Sign up: https://app.apollo.io
- API key: **Settings → Integrations → API**
- Free tier: 50 export credits/month — sufficient for testing. Upgrade to Basic ($49/mo) for production volume.
- `.env` variable: `APOLLO_API_KEY=...`

### Hunter.io (waterfall enrichment step 2)

- Sign up: https://hunter.io
- API key: **Dashboard → API**
- Free tier: 25 requests/month. Starter plan ($34/mo) for production.
- `.env` variable: `HUNTER_API_KEY=...`

### Prospeo (waterfall enrichment step 3, optional)

- Sign up: https://prospeo.io
- API key: **Account → API Key**
- Free tier: 75 credits/month
- `.env` variable: `PROSPEO_API_KEY=...`

### ZeroBounce (email verification, required)

- Sign up: https://www.zerobounce.net
- API key: **Dashboard → API**
- Free tier: 100 validations/month — sufficient for testing.
- `.env` variable: `ZEROBOUNCE_API_KEY=...`

### Instantly.ai (email sequences, required)

- Sign up: https://instantly.ai
- API key: **Settings → API**
- Pricing: $37/mo (Growth plan — required for API access)
- `.env` variable: `INSTANTLY_API_KEY=inst_...`

### HubSpot CRM (required)

- Sign up: https://app.hubspot.com (free CRM tier)
- Create a Private App: **Settings → Integrations → Private Apps → Create**
- Required scopes: `crm.objects.deals.read`, `crm.objects.deals.write`, `crm.objects.contacts.read`, `crm.objects.contacts.write`
- Free tier: CRM is free; no paid plan required for this integration.
- `.env` variable: `HUBSPOT_ACCESS_TOKEN=pat-na1-...`

### Semantic Scholar (optional)

- Sign up: https://www.semanticscholar.org/product/api
- Free tier: 100 requests/5 minutes without key. With key: 1 request/second.
- `.env` variable: `SEMANTIC_SCHOLAR_KEY=...`

### Clay (optional, for advanced enrichment)

- Sign up: https://clay.com
- Explorer plan: $314/mo. Skip for minimal setup.
- `.env` variable: `CLAY_API_KEY=...`

---

## 4. n8n Setup

### 4.1 Installing n8n

**Self-hosted (recommended for production):**

```bash
# Docker Compose (easiest)
docker run -it --rm \
  --name n8n \
  -p 5678:5678 \
  -v ~/.n8n:/home/node/.n8n \
  docker.n8n.io/n8nio/n8n
```

**n8n Cloud:** Sign up at https://n8n.io/cloud — $24/mo for Starter.

### 4.2 Importing Workflows

Import in this order (dependencies flow top to bottom):

| Order | File | Purpose |
|-------|------|---------|
| 1 | `n8n-workflows/crm-sync.json` | No dependencies |
| 2 | `n8n-workflows/sequence-launcher.json` | No dependencies |
| 3 | `n8n-workflows/enrichment-pipeline.json` | Calls sequence-launcher |
| 4 | `n8n-workflows/daily-signal-scan.json` | Calls enrichment-pipeline |

**Via n8n UI:**

1. Open your n8n instance (e.g., `http://localhost:5678`)
2. Click **Workflows** in the left sidebar
3. Click **Import from file** (or **+ New → Import**)
4. Import each file and activate using the toggle in the top-right corner

**Via n8n CLI:**

```bash
n8n import:workflow --input=n8n-workflows/crm-sync.json
n8n import:workflow --input=n8n-workflows/sequence-launcher.json
n8n import:workflow --input=n8n-workflows/enrichment-pipeline.json
n8n import:workflow --input=n8n-workflows/daily-signal-scan.json
```

### 4.3 n8n Environment Variables

Configure in **Settings → Variables** (referenced as `$vars.VAR_NAME` inside workflow nodes).

**Required:**

| Variable | Description | Example |
|----------|-------------|---------|
| `N8N_WEBHOOK_BASE_URL` | Public URL of your n8n instance | `https://n8n.yourdomain.com` |
| `GITHUB_TOKEN` | GitHub personal access token | `ghp_...` |
| `ANTHROPIC_API_KEY` | Anthropic API key for email generation | `sk-ant-...` |
| `INSTANTLY_API_KEY` | Instantly.ai API key | `inst_...` |
| `HUBSPOT_ACCESS_TOKEN` | HubSpot private app token | `pat-na1-...` |
| `ZEROBOUNCE_API_KEY` | ZeroBounce API key | `abc123...` |
| `APOLLO_API_KEY` | Apollo.io API key | `abc123...` |
| `HUNTER_API_KEY` | Hunter.io API key | `abc123...` |
| `SLACK_SIGNAL_CHANNEL` | Slack channel for A-tier alerts | `#rl-signals` |
| `SLACK_HOT_LEADS_CHANNEL` | Slack channel for positive replies | `#hot-leads` |
| `SLACK_ANALYTICS_CHANNEL` | Slack channel for daily digest | `#gtm-analytics` |
| `GOOGLE_SHEETS_ANALYTICS_DOC_ID` | Google Sheets document ID for analytics | `1BxiM...` |

**Optional:**

| Variable | Description |
|----------|-------------|
| `CLAY_API_KEY` | Clay.com enrichment (skipped gracefully if absent) |
| `PROSPEO_API_KEY` | Prospeo LinkedIn email enrichment |
| `INSTANTLY_CAMPAIGN_GITHUB` | Campaign ID for GitHub signal contacts |
| `INSTANTLY_CAMPAIGN_ARXIV` | Campaign ID for ArXiv signal contacts |
| `INSTANTLY_CAMPAIGN_JOBS` | Campaign ID for job posting signal contacts |
| `INSTANTLY_CAMPAIGN_HF` | Campaign ID for HuggingFace signal contacts |
| `INSTANTLY_CAMPAIGN_FUNDING` | Campaign ID for funding event contacts |

### 4.4 n8n Credential Configuration

**Slack OAuth2:**

1. Go to **Settings → Credentials → Add Credential → Slack OAuth2 API**
2. Create a Slack app at https://api.slack.com/apps with scopes: `chat:write`, `chat:write.public`
3. Add the OAuth redirect URL from n8n
4. Name the credential `Slack OAuth2` (must match workflow reference exactly)

**HubSpot OAuth2:**

1. Go to **Settings → Credentials → Add Credential → HubSpot OAuth2 API**
2. Create a HubSpot private app at https://app.hubspot.com/private-apps
3. Required scopes: `crm.objects.deals.read`, `crm.objects.deals.write`, `crm.objects.contacts.read`, `crm.objects.contacts.write`
4. Name the credential `HubSpot OAuth2`

**Google Sheets OAuth2:**

1. Go to **Settings → Credentials → Add Credential → Google Sheets OAuth2 API**
2. Create a Google Cloud project and enable the Sheets API
3. Configure OAuth consent screen and credentials
4. Name the credential `Google Sheets OAuth2`

### 4.5 Instantly.ai Webhook Configuration

The `crm-sync` workflow listens for engagement events from Instantly.ai.

1. After activating `crm-sync`, copy the webhook URL from the **Instantly Events Webhook** node (format: `https://your-n8n-instance.com/webhook/instantly-events`)
2. In Instantly.ai: **Settings → Integrations → Webhooks → Add webhook**
3. Paste the URL and select event types: `email_opened`, `email_replied`, `email_bounced`, `email_clicked`
4. Save and verify with a test event

### 4.6 Cron Schedule Reference

| Workflow | Cron Expression | Time (PST) | Time (UTC) |
|----------|----------------|------------|------------|
| `daily-signal-scan` | `0 15 * * *` | 7:00 AM | 15:00 |
| `crm-sync` (analytics branch) | `0 2 * * *` | 6:00 PM | 02:00 +1 |

Adjust in the Schedule Trigger nodes if your n8n instance runs in a different timezone.

### 4.7 Testing Workflows Manually

**Test daily-signal-scan:**

1. Open workflow → click **Execute Workflow** (manual trigger)
2. Verify each scanner node shows a `stdout` output
3. Confirm the Merge and Stack Signals nodes produce valid JSON
4. Check that the Slack alert fires if any A-tier signals exist

**Test enrichment-pipeline:**

1. Open workflow → Webhook Trigger node → **Test step**
2. Send a test POST payload:
   ```json
   {
     "signals": [{
       "company_name": "Test Company",
       "company_domain": "testcompany.ai",
       "signal_type": "GITHUB_RL_REPO",
       "icp_score": "A",
       "signal_strength": 3
     }],
     "source": "manual-test"
   }
   ```
3. Step through each node and verify data flows correctly
4. Check HubSpot for the created deal

**Test sequence-launcher:**

1. Open workflow → Webhook Trigger → **Test step**
2. Send a test payload:
   ```json
   {
     "signal": {
       "company_name": "Test Company",
       "company_domain": "testcompany.ai",
       "signal_type": "GITHUB_RL_REPO",
       "icp_score": "A",
       "contacts": [{
         "email": "test@testcompany.ai",
         "first_name": "Jane",
         "last_name": "Doe",
         "title": "Head of ML Infrastructure"
       }]
     },
     "deal_id": "test-deal-id"
   }
   ```
3. Verify the Claude API returns email copy
4. Confirm Instantly.ai receives the lead (check campaign dashboard)

**Test crm-sync:**

```json
{
  "event_type": "replied",
  "lead_email": "test@example.com",
  "campaign_id": "test-campaign",
  "reply_text": "Yes, interested! Let's schedule a call."
}
```

Send to the Instantly Events Webhook → verify classification returns `positive` and Slack hot-lead alert fires.

---

## 5. HubSpot Setup

### Custom Properties

Create these once under **CRM → Properties → Create property**:

| Property Name | Type | Values |
|---------------|------|--------|
| `signal_source` | Enumeration | `github`, `arxiv`, `huggingface`, `hiring`, `funding` |
| `icp_tier` | Enumeration | `tier1`, `tier2`, `tier3`, `tier4` |
| `rl_maturity` | Enumeration | `productionizing`, `scaling`, `building`, `exploring`, `none` |
| `composite_score` | Number | 0–25 |
| `icp_grade` | Enumeration | `A`, `B`, `C`, `D` |
| `sequence_name` | Single-line text | e.g. `github-rl-signal-varA` |
| `signal_date` | Date picker | Date signal was detected |

### Pipeline Stages

Create a deal pipeline named **RL GTM Pipeline** with these stages (in order):

1. Signal Detected
2. Researched
3. Enriched
4. Sequenced
5. Engaged
6. Responded
7. Meeting Scheduled
8. Disqualified

---

## 6. Instantly.ai Setup

### Sending Accounts

Never send cold email from your primary domain. Set up 3–5 secondary domains (e.g., `getcollinear.ai`, `collinear-ai.com`) with Google Workspace. Create 2–3 sending accounts per domain.

Configure DNS records for each sending domain before importing accounts:

- **SPF**: `v=spf1 include:_spf.google.com ~all`
- **DKIM**: Generate in Google Workspace Admin → Gmail → Authenticate email
- **DMARC**: `v=DMARC1; p=none; rua=mailto:dmarc@yourdomain.com`

### Warmup

Enable email warmup for all new sending accounts in Instantly. Follow the 6-week schedule:

| Week | Emails/day per account |
|------|----------------------|
| 1 | 3–5 |
| 2 | 10–15 |
| 3 | 20–25 |
| 4–6 | 30 (max) |

Do not send to real prospects until at least 4 weeks of warmup are complete.

### Campaign Setup

Create one campaign per signal type for segmentation. After creating each campaign, copy the campaign ID and set the corresponding `INSTANTLY_CAMPAIGN_*` variable in n8n.

| Campaign Name | Signal Type | n8n Variable |
|---------------|-------------|-------------|
| GitHub RL | `GITHUB_RL_REPO` | `INSTANTLY_CAMPAIGN_GITHUB` |
| ArXiv Labs | `ARXIV_PAPER` | `INSTANTLY_CAMPAIGN_ARXIV` |
| Hiring Signal | `JOB_POSTING` | `INSTANTLY_CAMPAIGN_JOBS` |
| HF Models | `HUGGINGFACE_MODEL` | `INSTANTLY_CAMPAIGN_HF` |
| Funded Cos | `FUNDING_EVENT` | `INSTANTLY_CAMPAIGN_FUNDING` |

### Analytics Google Sheet

1. Create a new Google Spreadsheet
2. Add a sheet named exactly `Daily Analytics`
3. The `crm-sync` workflow auto-appends rows with these columns:
   - Date, Total Signals, Qualified, Sequenced, Replied, Meetings, Open Rate, Reply Rate, Cost USD, Cost Per Meeting, Tier A, Tier B, Tier C
4. Copy the document ID from the URL and set it as `GOOGLE_SHEETS_ANALYTICS_DOC_ID`

---

## 7. First Run

Walk through this sequence end-to-end to verify the full pipeline:

### Step 1 — Run a signal scanner

```bash
python -m scripts.github_rl_scanner --lookback-days 7 --output /tmp/github-signals.json
```

Expected output: JSON file with `signals_found` array. Each signal should have `company_name`, `signal_type`, `signal_strength`, and `source_url`.

### Step 2 — Stack signals

```bash
python -m scripts.signal_stacker --inputs /tmp/github-signals.json --output /tmp/stacked.json
```

Expected output: Ranked `CompanyProfile` list. Top entries should have `icp_score` of A or B.

### Step 3 — Research a prospect

Open Claude Code and run:

```
/prospect-researcher <company_name from stacked.json>
```

Claude will run firmographic and technographic research and output an ICP score + RL maturity classification.

### Step 4 — Find contacts

```
/contact-finder <company_domain>
```

Claude will run the waterfall enrichment and return verified contacts with `email_verified: true`.

### Step 5 — Generate email

```
/email-writer
```

Provide the signal payload, contact, and research output when prompted. Claude will generate 3 email variants using the appropriate template.

### Step 6 — Launch sequence

Enroll the contact in the relevant Instantly.ai campaign manually (or trigger the `sequence-launcher` n8n workflow with the contact payload).

### Step 7 — Verify CRM

Check HubSpot for a new deal in **Signal Detected** stage with the correct custom properties (`signal_source`, `icp_grade`, `composite_score`).

---

## 8. Troubleshooting

| Problem | Diagnosis | Fix |
|---------|-----------|-----|
| `ValueError: Scanner 'github' requires github_token` | `GITHUB_TOKEN` not set in `.env` | Add token and restart |
| GitHub scanner returns 0 signals | Rate limit exceeded (unauthenticated) | Confirm token is valid with `curl -H "Authorization: Bearer $GITHUB_TOKEN" https://api.github.com/rate_limit` |
| n8n webhook not receiving | n8n not publicly accessible | Ensure port 5678 is reachable or use n8n Cloud |
| Missing deals in HubSpot | Custom properties not created | Create all properties listed in Section 5 |
| Instantly.ai not receiving leads | Campaign ID not set | Set `INSTANTLY_CAMPAIGN_*` variables in n8n |
| Enrichment pipeline finds 0 contacts | All enrichment keys missing | Set at least one of `APOLLO_API_KEY`, `HUNTER_API_KEY`, `PROSPEO_API_KEY` |
| 429 rate limit in n8n nodes | n8n HTTP nodes don't retry by default | Enable **Retry on fail** under node Settings |
