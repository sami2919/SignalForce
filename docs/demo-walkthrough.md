# Demo Walkthrough: Test Every Skill in 30 Minutes

> Run this walkthrough to see every skill in action using a real example company. No API keys required — you can test with simulated data.

---

## Prerequisites

```bash
cd /Users/sami/SignalForce
source .venv/bin/activate  # or however you activate your virtualenv
pytest tests/ -q           # verify everything works (should see 436 passed)
```

---

## The Scenario

You're the founding GTM engineer at Collinear AI (RL Environment-as-a-Service). It's Monday morning. Let's run the full pipeline.

**Target company for this demo:** Cohere (AI lab, known to work on RLHF for language models)

---

## Skill 1: `signal-scanner` — Find Target Accounts

**What it does:** Runs all 6 scanners to detect companies investing in RL.

### Option A: With GitHub API key configured

```
Scan for companies investing in reinforcement learning in the last 7 days
using the signal-scanner skill
```

### Option B: Without API keys (simulation mode)

The scanners work in simulation mode. Or you can test the signal stacker directly with mock data:

```python
# Quick test in Python
python3 -c "
from scripts.models import Signal, SignalType, SignalStrength, ScanResult
from scripts.signal_stacker import SignalStacker
from datetime import datetime, UTC

# Simulate signals we 'found'
signals = [
    Signal(
        signal_type=SignalType.GITHUB_RL_REPO,
        company_name='Cohere',
        company_domain='cohere.com',
        signal_strength=SignalStrength.STRONG,
        source_url='https://github.com/cohere-ai/cohere-rl',
        raw_data={},
        metadata={'repo_name': 'cohere-rl', 'repo_count': 3, 'total_stars': 450},
    ),
    Signal(
        signal_type=SignalType.ARXIV_PAPER,
        company_name='Cohere',
        company_domain='cohere.com',
        signal_strength=SignalStrength.MODERATE,
        source_url='https://arxiv.org/abs/2403.12345',
        raw_data={},
        metadata={'paper_titles': ['Reward Modeling at Scale'], 'paper_count': 1},
    ),
    Signal(
        signal_type=SignalType.JOB_POSTING,
        company_name='Cohere',
        company_domain='cohere.com',
        signal_strength=SignalStrength.MODERATE,
        source_url='https://jobs.lever.co/cohere/rl-engineer',
        raw_data={},
        metadata={'job_titles': ['RL Engineer'], 'posting_count': 1},
    ),
]

scan_result = ScanResult(
    scan_type=SignalType.GITHUB_RL_REPO,
    started_at=datetime.now(UTC),
    completed_at=datetime.now(UTC),
    signals_found=signals,
    total_raw_results=3,
    total_after_dedup=3,
)

# Stack with intent scoring
stacker = SignalStacker(use_intent_scoring=True)
profiles = stacker.stack_signals([scan_result])

for p in profiles:
    print(f'{p.company_name} | Score: {p.composite_signal_score:.1f} | Grade: {p.icp_score}')
    print(f'  Signals: {len(p.signals)} from {len(set(s.signal_type for s in p.signals))} sources')
"
```

**Expected output:** Cohere shows as a high-scoring account with 3 signals from 3 sources.

---

## Skill 2: `prospect-researcher` — Deep-Dive a Company

**What it does:** Researches a company and scores it against the ICP rubric.

```
Use the prospect-researcher skill to evaluate Cohere for RL infrastructure fit.
They have 3 RL repos on GitHub, published a paper on reward modeling,
and are hiring an RL engineer.
```

**What Claude does:**
1. Researches Cohere's firmographics (Series C, ~500 employees, Toronto/SF)
2. Identifies RL maturity stage (SCALING — multiple RL projects, hiring RL engineers)
3. Maps decision-makers (Head of ML, VP Engineering)
4. Scores against the 5-dimension rubric
5. Outputs a structured company brief with ICP grade

**Expected output:** Grade A or B, with specific messaging angles tied to their RLHF work.

---

## Skill 3: `contact-finder` — Find the Decision-Maker

**What it does:** Waterfall enrichment to find verified email + LinkedIn for key contacts.

```
Use contact-finder to find the Head of ML at Cohere (cohere.com)
```

**What Claude does:**
1. Defines the waterfall: Apollo → Hunter → Prospeo → ZeroBounce
2. For each tool: provides API instructions (if key configured) or web UI steps
3. Guides you through finding and verifying the email

**Without API keys**, Claude gives you step-by-step manual instructions:
- "Go to Apollo.io → Search → Company: Cohere → Title: Head of ML → Copy email"
- "Go to Hunter.io → Domain search: cohere.com → Find pattern"

---

## Skill 4: `email-writer` — Standard Signal-Based Outreach

**What it does:** Generates personalized outreach emails that reference specific signals.

```
Use email-writer to generate outreach for Dr. Sarah Chen, Head of ML at Cohere.
Signal type: ArXiv paper.
Signal reference: "Reward Modeling at Scale: Efficient RLHF for Enterprise LLMs"
Company context: Series C, ~500 employees, heavy RLHF usage, Tier 1 AI lab
```

**Expected output:**
- 3 variants (Problem-Focused, Outcome-Focused, Social-Proof-Focused)
- Each variant has a 3-email sequence (Day 0, Day 3, Day 7)
- First sentence references the specific paper
- Under 4 sentences each
- Quality checklist (signal reference ✓, no generic openers ✓, low-friction CTA ✓)

---

## Skill 5: `resource-offer` — Blueprint-Before-Demo Outreach

**What it does:** Generates resource-first outreach (50% reply rates vs. 8-15% for demo asks).

```
Use resource-offer to generate outreach for Dr. Sarah Chen at Cohere.
Signal: They published a paper on reward modeling.
This is a Tier 1 AI lab, deeply technical buyer.
```

**Expected output:**
- Resource selection: "Framework: Environment Infrastructure Decisions for RL Research Teams"
- 3 variants, each leading with the resource (NOT a meeting ask)
- Email 1: Offer the framework
- Email 2: Share a specific insight from the framework
- Email 3: Low-friction conversation offer about the relevant section

**Compare this output with Skill 4's output** — notice how resource-first is more conversational and less "salesy."

---

## Skill 6: `multi-channel-writer` — Email + LinkedIn Sequence

**What it does:** Creates a coordinated, staggered sequence across email and LinkedIn.

```
Use multi-channel-writer to create outreach for Dr. Sarah Chen at Cohere.
We have both her email and LinkedIn URL.
Signal type: GitHub RL repos.
Signal reference: cohere-ai/cohere-rl repository with 450 stars
```

**Expected output:**
- Day 0: Email 1 (problem-focused, reference their repo)
- Day 1: LinkedIn connection request (≤300 chars, no product mention)
- Day 3: Email 2 (outcome-focused, share a resource)
- Day 4: LinkedIn follow-up message (if connected)
- Day 7: Email 3 (break-up, graceful exit)
- Day 8: LinkedIn second follow-up

---

## Skill 7: `pipeline-tracker` — CRM & Analytics

**What it does:** Manages HubSpot sync and generates pipeline reports.

```
Use pipeline-tracker to set up CRM tracking for our Cohere outreach.
Create a deal for Cohere with signal source: ArXiv paper + GitHub repos.
ICP score: A. Stage: SEQUENCED.
```

Then later:

```
Use pipeline-tracker to generate this week's analytics report
```

**Expected output:** Weekly metrics — signals detected, accounts qualified, sequences launched, reply rate, meetings booked, cost per meeting.

---

## Skill 8: `meeting-followup` — Post-Meeting Automation

**What it does:** Processes meeting notes and generates follow-up emails.

```
Use meeting-followup to process these meeting notes:

Meeting with Dr. Sarah Chen (Head of ML, Cohere) on March 17, 2026.
Attendees: Sarah Chen, CTO James Wu (joined for last 15 min).
Outcome: Positive.
Key discussion: They're building custom Gymnasium environments for RLHF
and spending 2 engineers full-time maintaining them. Interested in
managed alternative but concerned about Gymnasium API compatibility.
Objections: "Does it support custom reward functions?"
Next steps: Send Gymnasium compatibility documentation. Schedule
technical deep-dive with their RL team lead.
Decision timeline: Q2 2026 evaluation.
Stakeholders needed: RL team lead (not in meeting), VP Eng (budget).
```

**Expected output:**
- Structured MeetingOutcome extraction
- Positive outcome → 3-email follow-up sequence
- Email 1 (Day 0): Thank you + Gymnasium compatibility docs + calendar link
- Email 2 (Day 3): Case study addressing their specific use case
- Email 3 (Day 7): Check on internal alignment, offer to present to RL team lead

---

## Skill 9: `champion-tracker` — Job Change Monitoring

**What it does:** Monitors when known contacts change companies and triggers warm outreach.

```
Use champion-tracker — Dr. Sarah Chen moved from Cohere to Mistral AI
as their new Head of Post-Training. She was a positive contact at Cohere
who expressed interest in managed RL environments.
```

**Expected output:**
1. Research Mistral AI with `prospect-researcher` logic
2. ICP assessment (Tier 1 AI Lab → Grade A)
3. Warm outreach using `champion-job-change` template
4. "Congrats on the move to Mistral! At Cohere, we discussed Gymnasium-compatible environments for RLHF..."
5. CTA: catch-up conversation, not cold demo

---

## Skill 10: `deliverability-manager` — Email Infrastructure

**What it does:** Sets up and troubleshoots cold email sending infrastructure.

```
Use deliverability-manager to set up cold email infrastructure.
I have the primary domain collinear.ai and want to send 100 cold emails per day.
```

**Expected output:**
1. Domain strategy: Buy 3-5 secondary domains (collinear-ai.com, getcollinear.com, etc.)
2. DNS records: Exact SPF, DKIM, DMARC syntax for each domain
3. Warmup schedule: Week 1-2 (5/day) → Week 3-4 (15/day) → Week 5+ (25-30/day)
4. Capacity calculation: 4 domains × 3 accounts × 25 emails = 300/day capacity
5. Monitoring: MXToolbox, Google Postmaster, bounce rate thresholds

---

## Skill 11: `compliance-manager` — Regulatory Compliance

**What it does:** Manages opt-outs, suppression lists, and regulatory compliance.

```
Use compliance-manager to run the monthly audit checklist.
We're sending cold emails to prospects in the US and EU.
```

**Expected output:**
1. CAN-SPAM checklist (physical address ✓, opt-out mechanism ✓, etc.)
2. GDPR requirements (legitimate interest basis, right to erasure process)
3. Suppression list audit (global opt-out synced? bounced emails removed?)
4. Data handling review (no PII in git repos? contact data only in CRM?)
5. Action items for any gaps found

---

## Bonus: Test the Intent Scoring Engine

See how the new intent-weighted scoring compares to the legacy model:

```python
python3 -c "
from scripts.models import Signal, SignalType, SignalStrength, ScanResult
from scripts.signal_stacker import SignalStacker
from datetime import datetime, timedelta, UTC

# Fresh signal (today) vs stale signal (7 days ago)
fresh = Signal(
    signal_type=SignalType.ARXIV_PAPER,
    company_name='FreshCo',
    company_domain='fresh.com',
    signal_strength=SignalStrength.STRONG,
    source_url='https://arxiv.org',
    raw_data={},
    metadata={'paper_titles': ['RL Paper']},
)

stale = Signal(
    signal_type=SignalType.ARXIV_PAPER,
    company_name='StaleCo',
    company_domain='stale.com',
    signal_strength=SignalStrength.STRONG,
    source_url='https://arxiv.org',
    raw_data={},
    metadata={'paper_titles': ['Old Paper']},
    detected_at=datetime.now(UTC) - timedelta(days=7),
)

scan = ScanResult(
    scan_type=SignalType.ARXIV_PAPER,
    started_at=datetime.now(UTC),
    completed_at=datetime.now(UTC),
    signals_found=[fresh, stale],
    total_raw_results=2,
    total_after_dedup=2,
)

# Compare scoring models
intent = SignalStacker(use_intent_scoring=True)
legacy = SignalStacker(use_intent_scoring=False)

print('=== INTENT SCORING (timing beats targeting) ===')
for p in intent.stack_signals([scan]):
    print(f'  {p.company_name}: {p.composite_signal_score:.2f} (Grade {p.icp_score})')

print()
print('=== LEGACY SCORING (all signals equal) ===')
for p in legacy.stack_signals([scan]):
    print(f'  {p.company_name}: {p.composite_signal_score:.2f} (Grade {p.icp_score})')
"
```

**What to notice:** With intent scoring, FreshCo scores higher than StaleCo even though both have the same signal strength. With legacy scoring, they're identical. This is the "timing beats targeting" principle in action.

---

## Bonus: Test the LinkedIn 48-Hour Filter

```python
python3 -c "
from scripts.linkedin_activity import LinkedInActivityScanner
from datetime import datetime, timedelta, UTC

# Simulate LinkedIn activity data
activity_data = [
    {
        'name': 'Sarah Chen',
        'company': 'Cohere',
        'activity_type': 'posted',
        'topic': 'Excited about our new reinforcement learning from human feedback pipeline',
        'timestamp': datetime.now(UTC).isoformat(),
    },
    {
        'name': 'James Wu',
        'company': 'Cohere',
        'activity_type': 'commented',
        'topic': 'Great paper on reward modeling approaches',
        'timestamp': datetime.now(UTC).isoformat(),
    },
    {
        'name': 'Old Contact',
        'company': 'StaleCorp',
        'activity_type': 'posted',
        'topic': 'reinforcement learning environments',
        'timestamp': (datetime.now(UTC) - timedelta(hours=72)).isoformat(),
    },
]

scanner = LinkedInActivityScanner(max_age_hours=48)
result = scanner.scan_from_data(activity_data)

print(f'Total activities: {len(activity_data)}')
print(f'Signals after 48hr filter: {len(result.signals_found)}')
for sig in result.signals_found:
    print(f'  {sig.company_name}: {sig.signal_strength.name} ({sig.metadata[\"activity_count\"]} activities)')
    print(f'    Contacts: {sig.metadata[\"active_contacts\"]}')
"
```

**Expected:** Cohere passes the 48-hour filter (2 activities → 1 STRONG signal). StaleCorp is filtered out (72 hours old).

---

## Bonus: Test Multi-Channel Sequencing

```python
python3 -c "
from scripts.multi_channel_sequencer import build_sequence, select_primary_channel
from scripts.models import OutreachChannel, SignalType

# Determine channels
channels = select_primary_channel(has_email=True, has_linkedin=True)
print(f'Channels: {[c.value for c in channels]}')

# Build staggered sequence
steps = build_sequence(channels, SignalType.ARXIV_PAPER)
print(f'\\nSequence ({len(steps)} steps):')
for step in steps:
    print(f'  Day {step.day}: {step.channel.value} — {step.action} ({step.template_name})')
"
```

**Expected:** 6-step staggered sequence alternating between email and LinkedIn.

---

## What To Do After the Demo

1. **Configure real API keys** in `.env` (start with just GITHUB_TOKEN — it's free)
2. **Run `signal-scanner` with real data** to find actual target accounts
3. **Customize `.agents/gtm-context.md`** if you're adapting for a different product
4. **Set up Instantly.ai** and secondary sending domains using `deliverability-manager`
5. **Import n8n workflows** for automated daily scanning
