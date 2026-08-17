# Veriforce — Tier-2 Supplier Re-Engagement

### Compliance Lapse → Renewal · A lifecycle campaign brief, ready to run on Conversion's platform

---

## Executive summary

Veriforce has a population of Tier-2 industrial suppliers — oil & gas, utilities, construction — whose compliance verification has lapsed in the last 90 days but who are still under active contracts with hiring clients that legally require verified suppliers. These are not cold prospects; they are paying customers drifting toward churn while sitting on a contractual reason to come back. This campaign re-engages roughly **2,400 contacts across 840 accounts** over a **21-day sequence** (email → in-app banner → AE task → optimized email → personal LinkedIn), with three AI agents owning execution, QA, and optimization in non-overlapping roles. The expected outcome is **~101 account renewals (12% of the cohort) recovering $1.2M–$1.6M in dormant ARR within a quarter**, while cutting the AE labor required to do it by roughly 65% versus fully manual outreach. The play works because the message isn't a discount — it's the customer's own contractual reality, surfaced at the moment it still costs them something to ignore.

---

## Why now — the buying window

The timing isn't a guess; it's structural. Three forces make this the right quarter to run the play:

- **A 90-day decay window.** A supplier whose verification expired this week is recoverable. One who lapsed six months ago has likely already lost the contract and the habit. The segment deliberately targets the **0–90 day post-lapse band** — the period where the customer still has something to save and the relationship is still warm.
- **Pre-churn, not post-churn.** Every account in scope is flagged with a **churn-risk score of 60 or higher** but has *not* yet churned. We are intervening before the renewal decision hardens, not trying to win back a lost account.
- **A live contractual hook.** Each targeted account has at least one hiring client with an **active contract that requires verified suppliers**. The lapse doesn't just inconvenience the supplier — it puts *their* customer out of compliance too. That shared exposure is the most durable reason-to-act available, and it exists right now.

In plain terms: these customers have a clock running, a real consequence, and a one-click fix. The campaign meets them inside that window.

---

## The segment — who we're talking to

**~2,400 contacts across ~840 accounts.** The targeting layer combines Salesforce account/contact filters with warehouse behavioral and intent traits, then strips out anyone we shouldn't touch.

**Who's in (plain terms):**
- Tier-2 **supplier** accounts, currently active customers, with annual revenue on record.
- Compliance status of **Expired** or **Pending Renewal**, with a verification expiry that landed inside the last 90 days.
- **No login in 90+ days** — genuinely dormant, not just quiet.
- A **churn-risk score of 60+** and **medium-or-high third-party intent** for compliance software (they're looking — possibly at alternatives).
- At least one **hiring client with an active contract** depending on their verified status.
- Contacts who have **opted in** to email and SMS.

**Who's deliberately excluded:**
- Accounts with an **open critical or high-severity support case** (don't market over a fire).
- Accounts with an **active AE opportunity** already in motion (no stepping on sales).
- Anyone who has **opted out** of email or SMS.
- Accounts already marked **churned**.

The exclusions matter as much as the inclusions: they keep marketing out of conversations sales already owns and out of accounts where outreach would be tone-deaf.

---

## The 5-touch sequence

Each touch escalates only if the prior one didn't convert, and every touch is suppressed the instant the customer renews. Channel, timing, intent, and the owning agent:

| # | Day | Channel | The point of this touch | Owned by |
|---|-----|---------|--------------------------|----------|
| 1 | Day 0 | **Email** | Factual, non-alarmist alert: your verification lapsed *N* days ago, here are the named hiring clients now flagged because of it, here's the one-click pre-filled renewal portal. Sent 9 AM local, Tue/Wed only. | Execution |
| 2 | Day 3 | **In-app banner** | Fires on next login. Persistent top-of-screen banner showing days expired, count of affected hiring clients, and a "Renew Now" button. Re-surfaces if dismissed. | Execution |
| 3 | Day 7 | **AE task** | If the email was opened or the banner clicked but no renewal started, create a high-priority Salesforce task for the named AE with full context, ARR-at-risk, and a recommended talk track — human outreach within one business day. | Execution |
| 4 | Day 14 | **Email (A/B)** | Optimization agent picks the variant by Day-0 engagement: **Variant A** (cold, churn-risk ≥75) leads with consequence — your clients may have to find a new verified supplier; **Variant B** (engaged) leads with a frictionless "pick up where you left off" renewal checklist. | Optimization |
| 5 | Day 21 | **LinkedIn** | For accounts still silent with churn-risk ≥70, a personal, peer-to-peer DM from the mapped AE — capped at 300 characters, calendar link plus direct renewal link. The human, final ask. | Execution |

Every step carries hard QA gates: real-time opt-out and open-case re-checks at send time, null-token blocking (no "Hi {{first_name}}" misfires), subject-line spam-length limits, live-URL validation on the renewal link, and per-account deduplication so a single account never gets hit five times in parallel.

---

## Optimization triggers — the if-this-then-that rules

The optimization agent watches the campaign in real time and reroutes on signal rather than waiting for the calendar:

- **If** a contact opens the Day-0 email and clicks the renewal CTA but doesn't finish within 72 hours → **then** skip the Day-3 default timing, surface the banner on their very next login, and raise a low-priority AE awareness task immediately.
- **If** an account's compliance status flips to **Active** (they renewed) at any point → **then** instantly suppress every remaining touch, write the status back to Salesforce, enroll them in post-renewal onboarding, and log the conversion.
- **If** an account's churn-risk score crosses **85** → **then** pull it out of automation entirely, create a *Critical* AE task due today, and ping the AE on Slack — manual outreach within 4 business hours.
- **If** Variant A matches or beats Variant B (≥10% click-to-initiation by Day 16) → **then** reallocate the remaining untouched cohort 70/30 toward Variant A and update the subject-line weights.
- **If** a Day-7 AE task sits incomplete past 48 business hours → **then** escalate to the AE's manager via Chatter, and re-assign to the CSM overflow queue if still untouched at 72 hours.
- **If** three or more contacts on the same account engage but nobody starts a renewal → **then** flag it as high multi-contact intent and open a "Renewal Discovery" opportunity for an AE to run a consultative assist.

---

## Pipeline projection — base case and downside

**Base case:**
- **~101 account renewals** — 12% of the 840-account cohort.
- **$1.2M–$1.6M ARR recovered**, at an average Tier-2 ARR of ~$14,300/account.
- **30–35% of conversions AE-assisted** (the Step 3 and Step 5 human touches), the rest self-serve.
- **AE efficiency:** task volume is capped at ~168 (Step 3 fires on ~20% of accounts), LinkedIn outreach limited to ~200–250 high-risk non-responders. Total AE labor: **140–180 hours across the quarter, versus ~520 hours fully manual — a ~65% efficiency gain.**
- **Runtime:** 21-day active sequence per cohort; full campaign closes Day 28 (final touch plus a 7-day conversion window). Review cadence at Days 7, 14, 21, and 28.

**Downside scenario (~25% probability) — stated plainly, because a CEO will ask:**

If email deliverability degrades or compliance data sync lags, segment accuracy drops 20–30% and the addressable pool shrinks to **~600 accounts**. Open rates fall to ~18%, portal click-through to ~3.5%, and renewal conversion to 5–6% of the smaller pool — roughly **36 accounts and ~$515K recovered**. AE task volume holds, but AE-assisted conversion falls proportionally.

The brief ships with the mitigations attached: (1) warm the sending domain for 7 days pre-launch; (2) reconcile warehouse-to-Salesforce compliance status within 48 hours of kickoff; (3) stand up SMS as a parallel Step-1 fallback for contacts with verified mobiles if open rates drop below 15% at the Day-3 check. The downside is real but bounded, and it has named levers — not a shrug.

---

## How this was produced

This brief is not a slide written by hand. It is **config-driven and schema-enforced**: a single YAML file describing the prospect and objective goes in; a Claude `tool_use` JSON schema makes the model physically unable to return an off-shape object; the result is re-validated against a frozen Pydantic model before anything renders. The output you're reading maps one-to-one onto what Conversion's platform consumes — segment, sequence, agent assignments, QA rules, optimization triggers, pipeline projection.

Swap the config, get a different real-company brief in the same shape, in **~30 seconds for roughly $0.002 per brief**.

---

*Source: live generation via `python3.11 -m scripts.marops.cli veriforce` (`out/veriforce.json`), model `claude-sonnet-4-6`, generated 2026-06-08. Every figure above traces to that file or to `examples/marops/veriforce.yaml`. No metrics were invented.*
