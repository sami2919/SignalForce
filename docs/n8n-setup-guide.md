# n8n Workflow Setup Guide

This guide covers importing and configuring the four SignalForce automation workflows in n8n.

## Prerequisites

- n8n instance (self-hosted or n8n Cloud) running v1.30+
- Python 3.11+ installed on the n8n host with SignalForce repo at `/opt/signalforce`
- All API keys from `.env.example` provisioned

---

## 1. Importing Workflows

### Via n8n UI

1. Open your n8n instance (e.g., `http://localhost:5678`)
2. Click **Workflows** in the left sidebar
3. Click **Import from file** (or use **+ New → Import**)
4. Import each file in this order (dependencies flow top to bottom):

   | Order | File | Purpose |
   |-------|------|---------|
   | 1 | `n8n-workflows/crm-sync.json` | No dependencies |
   | 2 | `n8n-workflows/sequence-launcher.json` | No dependencies |
   | 3 | `n8n-workflows/enrichment-pipeline.json` | Calls sequence-launcher |
   | 4 | `n8n-workflows/daily-signal-scan.json` | Calls enrichment-pipeline |

5. After importing each workflow, **activate** it using the toggle in the top-right corner.

### Via n8n CLI

```bash
n8n import:workflow --input=n8n-workflows/crm-sync.json
n8n import:workflow --input=n8n-workflows/sequence-launcher.json
n8n import:workflow --input=n8n-workflows/enrichment-pipeline.json
n8n import:workflow --input=n8n-workflows/daily-signal-scan.json
```

---

## 2. Environment Variables (n8n Variables)

Configure these in **Settings → Variables** in the n8n UI. These are referenced as `$vars.VAR_NAME` inside workflow nodes.

### Required

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

### Optional

| Variable | Description |
|----------|-------------|
| `CLAY_API_KEY` | Clay.com enrichment API key (skipped gracefully if absent) |
| `PROSPEO_API_KEY` | Prospeo LinkedIn email enrichment |
| `INSTANTLY_CAMPAIGN_GITHUB` | Campaign ID for GitHub signal contacts |
| `INSTANTLY_CAMPAIGN_ARXIV` | Campaign ID for ArXiv signal contacts |
| `INSTANTLY_CAMPAIGN_JOBS` | Campaign ID for job posting signal contacts |
| `INSTANTLY_CAMPAIGN_HF` | Campaign ID for HuggingFace signal contacts |
| `INSTANTLY_CAMPAIGN_FUNDING` | Campaign ID for funding event contacts |

---

## 3. Credential Configuration

### Slack OAuth2

1. Go to **Settings → Credentials → Add Credential → Slack OAuth2 API**
2. Create a Slack app at https://api.slack.com/apps with scopes: `chat:write`, `chat:write.public`
3. Add the OAuth redirect URL from n8n
4. Name the credential `Slack OAuth2` (matches workflow reference)

### HubSpot OAuth2

1. Go to **Settings → Credentials → Add Credential → HubSpot OAuth2 API**
2. Create a HubSpot private app at https://app.hubspot.com/private-apps
3. Required scopes: `crm.objects.deals.read`, `crm.objects.deals.write`, `crm.objects.contacts.read`, `crm.objects.contacts.write`
4. Name the credential `HubSpot OAuth2`

### Google Sheets OAuth2

1. Go to **Settings → Credentials → Add Credential → Google Sheets OAuth2 API**
2. Create a Google Cloud project and enable the Sheets API
3. Configure OAuth consent screen and credentials
4. Name the credential `Google Sheets OAuth2`

---

## 4. Instantly.ai Webhook Configuration

The `crm-sync` workflow listens for engagement events from Instantly.ai.

1. After activating `crm-sync`, copy the webhook URL from the **Instantly Events Webhook** node:
   - Format: `https://your-n8n-instance.com/webhook/instantly-events`
2. In Instantly.ai dashboard: **Settings → Integrations → Webhooks**
3. Add a new webhook with the copied URL
4. Select event types: `email_opened`, `email_replied`, `email_bounced`, `email_clicked`
5. Save and verify with a test event

---

## 5. Google Sheets Setup

1. Create a new Google Spreadsheet
2. Add a sheet named exactly `Daily Analytics`
3. The workflow will auto-append rows with these columns:
   - Date, Total Signals, Qualified, Sequenced, Replied, Meetings, Open Rate, Reply Rate, Cost USD, Cost Per Meeting, Tier A, Tier B, Tier C
4. Copy the document ID from the URL (`https://docs.google.com/spreadsheets/d/{DOC_ID}/edit`) and set it as `GOOGLE_SHEETS_ANALYTICS_DOC_ID`

---

## 6. Instantly.ai Campaign Setup

Each signal type routes to a separate campaign for segmentation. Create these campaigns in Instantly.ai before enabling the sequence launcher:

1. **GitHub RL** — for contacts from GitHub signal type
2. **ArXiv Labs** — for contacts from ArXiv papers
3. **Hiring Signal** — for job posting signals
4. **HF Models** — for HuggingFace model uploads
5. **Funded Cos** — for funding event signals

After creating campaigns, set their IDs as the `INSTANTLY_CAMPAIGN_*` variables.

---

## 7. Testing Each Workflow Manually

### Test daily-signal-scan

1. Open the workflow in n8n
2. Click **Execute Workflow** (manual trigger)
3. Verify each scanner node shows a `stdout` output
4. Confirm the Merge and Stack Signals nodes produce valid JSON
5. Check that the Slack alert fires if any A-tier signals exist

### Test enrichment-pipeline

1. Open the workflow
2. Click the Webhook Trigger node → **Test step**
3. Send a test POST payload:
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
4. Step through each node and verify data flows correctly
5. Check HubSpot for the created deal

### Test sequence-launcher

1. Open the workflow
2. Click Webhook Trigger → **Test step**
3. Send a test payload:
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
4. Verify the Claude API returns email copy
5. Confirm Instantly.ai receives the lead (check campaign dashboard)

### Test crm-sync

**Webhook branch:**
1. Open workflow → Instantly Events Webhook → **Test step**
2. Send a mock Instantly event:
   ```json
   {
     "event_type": "replied",
     "lead_email": "test@example.com",
     "campaign_id": "test-campaign",
     "reply_text": "Yes, interested! Let's schedule a call."
   }
   ```
3. Verify classification returns `positive` and Slack hot-lead alert fires

**Analytics branch:**
1. Click **Daily Analytics Trigger** → **Execute from this node**
2. Verify HubSpot deals are fetched
3. Confirm metrics calculation node produces expected fields
4. Check Google Sheets for a new row

---

## 8. Cron Schedule Reference

| Workflow | Cron | Time (PST) | Time (UTC) |
|----------|------|------------|------------|
| daily-signal-scan | `0 15 * * *` | 7:00 AM | 15:00 |
| crm-sync (analytics) | `0 2 * * *` | 6:00 PM | 02:00 +1 |

Adjust cron expressions in the Schedule Trigger nodes if your n8n instance runs in a different timezone.

---

## 9. Monitoring and Troubleshooting

- **Execution logs**: Workflows → select workflow → **Executions** tab
- **Failed executions**: Look for red nodes; click to inspect input/output
- **Rate limit errors (429)**: The Python scripts handle retries, but n8n HTTP nodes may need retry settings enabled under node **Settings → Retry on fail**
- **Webhook not receiving**: Verify n8n is publicly accessible and the webhook URL matches exactly what Instantly has configured
- **Missing deals in HubSpot**: Check that the `icp_score` and `signal_type` custom properties exist in HubSpot (create under CRM → Properties if absent)
