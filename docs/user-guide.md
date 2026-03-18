# User Guide: How to Use rl-gtm-engine Day-to-Day

> This guide assumes you've completed [setup-guide.md](setup-guide.md) and have API keys configured.

---

## The 30-Second Mental Model

You have **11 skills** — think of them as specialized assistants. Each one handles a specific GTM task. You don't need to use them all at once. Here's the flow:

```
Find accounts → Research them → Find contacts → Write outreach → Track pipeline
     ↓              ↓               ↓              ↓               ↓
signal-scanner  prospect-     contact-finder  email-writer     pipeline-tracker
                researcher                    resource-offer
                                              multi-channel-writer
```

**The engine has two modes:**
1. **Autonomous** — n8n workflows run daily, detect signals, alert you on Slack
2. **Interactive** — You invoke skills in Claude Code for research, writing, and decisions

Most GTM engineers use both: n8n finds the accounts, you use skills to research and engage them.

---

## Your Weekly Workflow

### Monday: Signal Review (15 min)

**What happens automatically:** The n8n daily scan ran over the weekend, detecting companies with new RL activity across GitHub, ArXiv, Hugging Face, job boards, and funding announcements. Results are in your Google Sheet + Slack alerts for A-tier accounts.

**What you do:**

1. **Review A-tier alerts in Slack.** These are companies with strong, multi-source signals. They need immediate attention.

2. **Run the signal scanner manually** if you want fresh data or to check a specific time window:
   ```
   Use the signal-scanner skill to find companies investing in RL in the last 7 days
   ```
   Claude will run all 6 scanners, stack signals, and present a ranked table.

3. **Add LinkedIn activity data** for the highest-priority accounts. Export recent activity from Sales Navigator or collect it manually, save as JSON, then:
   ```
   Use signal-scanner with this LinkedIn activity data: [paste or reference file]
   ```
   This is the single highest-ROI step — 48-hour LinkedIn activity doubles response rates.

---

### Tuesday-Wednesday: Research & Enrich (30 min/day)

For each A-tier account from Monday's scan:

**Step 1: Deep research**
```
Use prospect-researcher to evaluate [Company Name] for RL infrastructure fit
```
Claude will research firmographics, technographics, RL maturity, and score against the ICP rubric. You'll get a structured brief with a grade (A/B/C/D), recommended messaging angle, and key contacts to target.

**Step 2: Find contacts**
```
Use contact-finder to find the Head of ML at [Company Name]
```
Claude walks you through the waterfall: Apollo → Hunter → Prospeo → ZeroBounce. If you have API keys configured, it runs them automatically. If not, it gives you step-by-step instructions for each tool's web UI.

**Step 3: Decide your approach**
- **A-tier, technical buyer?** → Use `resource-offer` skill (50% reply rates)
- **A-tier, business buyer?** → Use `email-writer` skill (standard signal-based)
- **Have both email and LinkedIn?** → Use `multi-channel-writer` skill (staggered sequence)
- **B-tier?** → Add to monitoring list, revisit next week

---

### Thursday: Write & Launch (30 min)

**For resource-first outreach (recommended for technical buyers):**
```
Use resource-offer to generate outreach for [Contact Name] at [Company].
Signal: They published a paper on [paper title].
```
Claude selects the right resource, generates 3 variants (Problem/Outcome/Social Proof), and produces a 3-email sequence where Emails 1-2 offer value and Email 3 offers a conversation.

**For multi-channel outreach:**
```
Use multi-channel-writer to create a coordinated email + LinkedIn sequence
for [Contact] at [Company]. Signal type: GitHub RL repo activity.
```
Claude generates a staggered sequence: Email Day 0 → LinkedIn connection Day 1 → Email Day 3 → LinkedIn follow-up Day 4 → etc.

**For standard signal-based outreach:**
```
Use email-writer to generate outreach for [Contact] at [Company].
Signal type: ArXiv paper. Signal reference: "[Paper Title]"
```

**Review the output, then:**
- Copy email copy into Instantly.ai campaign
- Send LinkedIn connection request manually (or via automation tool)
- Claude will recommend which variant to use

---

### Friday: Pipeline Review (15 min)

```
Use pipeline-tracker to generate this week's analytics report
```

Claude pulls data from HubSpot and generates:
- Signals detected this week
- Accounts qualified (A + B tier)
- Contacts enriched
- Sequences launched
- Reply rate, meetings booked
- Cost per meeting
- Week-over-week trends

**After any meeting this week:**
```
Use meeting-followup to process these meeting notes: [paste notes]
```
Claude extracts the outcome, objections, next steps, and generates the appropriate follow-up sequence (different templates for positive/neutral/negative/no-show outcomes).

---

## Skill Quick Reference

| Skill | When to Use | Input | Output |
|-------|------------|-------|--------|
| `signal-scanner` | Monday morning, or anytime you want fresh signals | Lookback days, optional LinkedIn data | Ranked company table with ICP grades |
| `prospect-researcher` | Before engaging any new account | Company name or domain | ICP score, RL maturity, messaging angles |
| `contact-finder` | After qualifying an account | Company + target title | Verified email, LinkedIn URL |
| `email-writer` | Standard signal-based outreach | Signal + contact + research | 3 variants × 3-email sequence |
| `resource-offer` | Technical buyers (Tier 1, 3) | Signal + contact | Resource-first 3-email sequence |
| `multi-channel-writer` | When you have email + LinkedIn | Contact + signal + channels | Staggered email + LinkedIn sequence |
| `meeting-followup` | After any meeting | Meeting notes | Follow-up emails + CRM actions |
| `pipeline-tracker` | Weekly review | — | Pipeline analytics report |
| `champion-tracker` | When a known contact changes jobs | Champion list | Research + warm outreach |
| `deliverability-manager` | Setting up or troubleshooting email infra | Domain, DNS questions | DNS records, warmup plan |
| `compliance-manager` | Monthly audit or opt-out handling | — | Compliance checklist, suppression sync |

---

## Common Scenarios

### "I just found a hot prospect manually"

Skip the scanner. Go straight to:
1. `prospect-researcher` → Score them
2. `contact-finder` → Get the email
3. `resource-offer` or `email-writer` → Write the outreach

### "A prospect replied positively"

1. Update HubSpot deal stage via `pipeline-tracker`
2. If they want a meeting → book it, then use `meeting-followup` after
3. If they want the resource → send it, then wait 3 days before follow-up

### "It's been 2 weeks, no response on email"

Use `multi-channel-writer` to escalate to LinkedIn:
```
Use multi-channel-writer for [Contact]. They didn't respond to our email
sequence. Let's try LinkedIn as a secondary channel.
```

### "A past champion just changed jobs"

```
Use champion-tracker — [Contact Name] moved from [Old Company] to [New Company]
```
Claude researches the new company, scores ICP fit, and generates warm outreach if it's a B+ account.

### "My emails are landing in spam"

```
Use deliverability-manager to diagnose deliverability issues.
Bounce rate is at 6%, open rates dropped to 15%.
```
Claude walks through DNS checks, blacklist monitoring, and remediation steps.

### "I need to check compliance before scaling outreach"

```
Use compliance-manager to run the monthly audit checklist
```

---

## What Runs Automatically (n8n)

| Workflow | Schedule | What It Does |
|----------|----------|-------------|
| Daily Signal Scan | 7 AM PST daily | Runs all 6 scanners, stacks signals, alerts on A-tier |
| Enrichment Pipeline | Triggered by scan | Auto-enriches A-tier signals through contact waterfall |
| Sequence Launcher | Triggered by enrichment | Generates email copy, pushes to Instantly.ai |
| CRM Sync | Ongoing + 6 PM daily | Updates HubSpot from Instantly events, generates daily digest |

You can run any workflow manually from the n8n UI if you don't want to wait for the schedule.

---

## Customizing for Your Product

The engine is built for RL infrastructure but works for **any technical product sold to a niche market**. To customize:

1. **Edit `.agents/gtm-context.md`** — Replace Collinear AI's ICP with yours. Change company info, ICP tiers, target titles, voice/tone, competitors, proof points.

2. **Edit scanner search terms** — Each scanner has configurable keyword lists (e.g., `RL_TOPICS` in `github_rl_scanner.py`). Change these to match your product domain.

3. **Edit email templates** — Templates in `templates/email-sequences/` use placeholders. The copy references RL, but you can swap for your domain.

4. **Edit the scoring rubric** — `templates/scoring-rubrics/icp-scoring-model.md` defines how companies are graded. Adjust weights and thresholds for your market.

That's it. The pipeline architecture (scan → stack → research → enrich → write → track) works for any signal-based outbound motion.

---

## Tips from the Field

1. **Start with signal-scanner + prospect-researcher only.** Don't try to use all 11 skills on day one. Get comfortable finding and qualifying accounts first.

2. **Resource-first outreach works better than you think.** The instinct is to ask for a meeting. Resist it. Offer the blueprint. Let the content sell.

3. **The 48-hour LinkedIn filter is real.** If you can only do one thing, check if your prospect was active on LinkedIn in the last 48 hours before sending anything.

4. **Don't send from your primary domain.** Use the `deliverability-manager` skill to set up secondary sending domains before you send a single cold email.

5. **Review compliance monthly.** One GDPR complaint can blacklist your domain. Use `compliance-manager` to stay clean.

6. **Track everything from day one.** Use `pipeline-tracker` even when volumes are low. The conversion metrics tell you what to fix (low reply rate → fix messaging, low open rate → fix deliverability).
