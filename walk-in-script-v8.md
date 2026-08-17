# Conversion Walk-In Script v8 — Candidate Framing, Live Scan Demo

**Audience:** Ishaan Maheshwari (confirmed JD author, leads GTM Engineering). Verify last name in lobby directory before going up.

**Date:** Monday, June 1, 2026 (confirm before you go) **Location:** 300 Beale St, Suite A, San Francisco **Arrival window:** 9:30–10:00 AM PT **Goal:** Get Ishaan to want to interview me for the Founding GTM Engineer role.

**The critical reframe from v7 → v8:**

v6 and v7 read like a SignalForce pitch — "trial week to prove signal quality," "configure for two verticals," "you tell me if those are companies you'd want to reach." That's vendor language. It's what a consultant says when pitching a tool.

v8 reframes everything: **SignalForce is the work sample, not the product.** The artifact in Ishaan's hand isn't "here's a tool you should adopt." It's "here's evidence I'm already operating as a GTM engineer — and this is what week one looks like if I'm on your team."

The compiler frame stays. The why-now engine stays. The conference hook stays. The live scan stays. What changes is the framing AROUND them: every piece of the demo is now evidence of how I think and ship, not features of a product.

---

## Step 0 — Mindset

You are not pitching SignalForce. You are demonstrating that you already are the Founding GTM Engineer.

Ishaan's JD defined the role as breadth across signal detection \+ ICP scoring \+ intent modeling \+ enrichment \+ lifecycle briefs \+ CRM output — replacing intuition and manual research with a system. You built exactly that, in public, without being hired to.

The through-line you carry into the room: **"GTM engineers replace intuition and manual research with a system. I built one. Here's how it thinks."**

SignalForce in his hand is evidence of seven things, in this order:

1. You can build multi-source signal collection — data engineering applied to GTM  
2. You can model ICP fit \+ intent scoring with calibrated weights and recency decay  
3. You can aggregate signals into A/B/C grades — the enrichment waterfall pattern  
4. You can make the engine config-driven — serves multiple AEs with different ICPs  
5. You can ship lifecycle briefs with buying committees and urgency windows modeled  
6. You can debug data-source walls (G2/DataDome) and build honest fallbacks  
7. You can package all of that into a CLI that runs in a customer's office

That's seven JD bullets demonstrated. Not pitched. Demonstrated.

The trial week ask shifts: it's not "let me prove signal quality." It's "let me start week one. Pick a vertical. I'll build it the same way I'd build it on day one of the role."

---

## Carry-ons

**Laptop, charged 100%, tabs in this order:**

- Tab 1: `github.com/sami2919/SignalForce` README on `marops` branch (the work sample)  
- Tab 2: Terminal ready to run `python -m scripts.demo_scan --lookback-days 30 --min-grade B`  
- Tab 3: `examples/marops/hubspot-ceiling.yaml` open in GitHub UI  
- Tab 4: `demo/hubspot-ceiling.html` rendered locally in Chrome (post-bug-fixes)  
- Tab 5: `demo/veriforce.html` rendered locally in Chrome (backup)  
- Tab 6: One real job posting URL from a B-grade company in your Sunday-night scan output — pulled fresh before walking in (the scan returns different companies each run; use whatever's actually there)  
- VS Code split panes: `scripts/icp_fit_scorer.py` \+ `scripts/intent_scorer.py` \+ the scoring formula in a visible block \+ `scripts/marops/briefer.py` (`tool_use` schema)

**Physical:**

- 2 printed briefs: `hubspot-ceiling.html` (primary, folded in back pocket) and `veriforce.html` (backup, in bag)  
- 1-pager resume in bag — hand only if directly asked  
- Business card with GitHub QR \+ "marops branch" written on the back  
- Phone with Ashby JD screenshot \+ Next Play article cached offline 

---

## Pre-Flight Sunday Night

**Critical:** Run the live scan Sunday night and screenshot the top 5 results. If the SerpAPI key fails Monday morning, you fall back to the screenshot and the canned brief.

**Sunday night, in priority order:**

- [ ] Run `python -m scripts.demo_scan --lookback-days 30 --min-grade B` and screenshot the table  
- [ ] Pull one live job posting URL from a B-grade company in the output (whichever has the cleanest MAP-relevant title) and cache it in Tab 6  
- [ ] Confirm `demo/hubspot-ceiling.html` renders clean — all three render bugs are now fixed at the source (`renderer/marops/lifecycle_brief.html.j2` + `scripts/marops/models.py`). Open in Chrome and eyeball: timing badges read `HIGH`/`MEDIUM` (not `SignalTimingTier.HIGH`), personalization tokens show single braces `{{first_name}}`, and the "Why this is a Conversion-shaped artifact" footer is populated. **If you regenerate, render from the JSON — do NOT use `python -m scripts.marops.cli` to regen the demo brief: it calls the Claude API live, is non-deterministic, and will rewrite the rehearsed copy (the "duct tape" quote, the exact fields).**  
- [ ] Verify Ishaan's last name on LinkedIn (search "Ishaan Conversion" → Maheshwari)  
- [ ] Read the Next Play article \+ Ashby JD one final time  
- [ ] Cold-run the four short-pitch beats out loud under 90 seconds  
- [ ] Cold-run the extended conference-room flow once end-to-end with the laptop  
- [ ] Verify API keys live: `SERPAPI_KEY` **and** `GITHUB_TOKEN` in `.env`, and the scan runs **without `403 quota exhausted`**. On the last run GitHub was rate-limited — when that happens the GitHub scanner returns nothing and "five scanners in parallel" is really three. Let the quota reset (top of the hour) or swap in a fresh token. ⚠️ The rate-limit handler has a bug that can try to sleep ~56 years (`sleeping 1780093547s`) — if the live scan ever hangs, Ctrl-C and fall straight to the Sunday screenshot.  
- [ ] If you plan to use the "drop a company in and re-run" move (objection handlers): `config/g2_seeds.yaml` is still the `Example Corp` placeholder. Either seed 2–3 real G2 reviews into it, or set `G2_SESSION_COOKIE` in `.env` — otherwise the live G2 path surfaces nothing.  
- [ ] Do **not** plan to run the full `pytest` suite live. It takes ~3 min and has a known intermittent isolation flake (`get_config` + `.env`); cite "547 tests passing" from a clean run instead. If you must show green live, run a fast subset: `pytest tests/marops/ -q`.  
- [ ] Print two briefs: the Meridian Analytics brief (`demo/hubspot-ceiling.html`, primary) and `demo/veriforce.html` (backup)  
- [ ] Confirm 300 Beale St, Suite A on Google Maps  
- [ ] Charge everything  
- [ ] Midnight: stop. Sleep.

**Monday morning:**

- [ ] Re-screenshot the Ashby JD (URL has `ashby_jid` — sometimes pulled)  
- [ ] Re-run the live scan once to verify it still works  
- [ ] Verify all tabs in order  
- [ ] Meridian Analytics brief (`hubspot-ceiling.html`) folded, back pocket  
- [ ] Arrive 9:30–10:00 AM PT  
- [ ] Confirm lobby directory lists Conversion or Relentlo before going up

---

## Step 1 — Reception (≤25 sec, 20-minute hard stop)

Walk in. Eye contact. Not rushed.

"Hey — sorry to drop in cold. My name's Sami, I'm a GTM engineer based in SF. I'm here to see Ishaan — he leads GTM Engineering. I read his Founding GTM Engineer post and built a working version of the systems he describes. It's open-source on GitHub. I have one concrete thing to show, takes 90 seconds. Your careers page says you're in-person five days a week because it makes you faster. That's why I walked in instead of sending a Loom. Is he in this morning?"

Hand them your business card. **Not the resume yet. Not the brief yet.**

**If reception says he's busy:** "What time later today or tomorrow works? I'll come back."

**If reception asks "did you apply through Ashby?":** "I did this morning. The JD said GTM Engineering at Conversion means complete autonomy and craft over output. Figured a working prototype lands faster than a resume in queue."

**Hard stop:** 20-minute wait max. After that, leave the printed brief \+ business card, send the Loom that afternoon.

---

## Step 2A — Short Pitch (90 sec, four beats, if Ishaan is between meetings)

### Beat 1 — Who I Am, What I Built, Why It Matters (25 sec)

Look at Ishaan. Don't open the laptop yet:

"Ishaan — your JD defines GTM Engineering at Conversion as breadth across prospecting, enrichment, intent signals, ICP modeling, queryable CRM, data pipelines. World-class generalist range. I spent the last nine months building a working version of that — open source, in public, without being hired to. It's called SignalForce. The through-line: GTM engineers replace intuition and manual research with a system. I built one. Ninety seconds to show you how it thinks."

*Open laptop. The laptop is the credential.*

### Beat 2 — Live Scan, Real Companies (25 sec)

*Kick off the terminal: `python -m scripts.demo_scan --lookback-days 30 --min-grade B`*

While it runs:

"This is the engine running against live data right now — GitHub, job boards, funding. Configured for your exact ICP: Marketo and HubSpot migration signals, MOPs hiring, warehouse-native stack."

*Terminal prints the table.*

"The names at the top are real companies in active buying windows, scored against your ICP from live data. See the TYPES column — that's which signals stacked on each account. The top ones hit A-grade because three types fire together: a funding round, a G2 frustration review, and a live job posting. Straight answer on the data: the job postings are live, pulled this morning. The G2 and funding signals I seed manually — representative MAP-frustration reviews and public rounds — because the live G2 path is behind DataDome bot protection. The stacking, scoring, and grading you're watching is the real engine; the collection step for two of the five sources is manual today, and that's a day-one Playwright fix. The whole thing reconfigures by swapping a YAML file."

*(Stage note: names and grades come from the live scan and change every run — name whatever's on screen and read the TYPES column out loud ("funding + G2 + job") so the stacking is obvious. **Volunteer that the G2/funding signals are seeded before Ishaan asks — that honesty IS the pitch.** The live job postings are your verifiable signals; the seeded ones are clearly framed as a DataDome fallback. Sunday-night screenshot is the canonical backup.)*

### Beat 3 — A-Grade Account, Compiler Output (25 sec)

*Open `demo/hubspot-ceiling.html`. Pull printed brief from back pocket, hand to Ishaan.*

"This is what an A-grade looks like — three signals in 8 days on a single account. G2 review where the VP Marketing called HubSpot's Snowflake integration 'duct tape.' Hiring signal for a Marketing Data Engineer building attribution outside a MAP. Conference registration — and Conversion has a booth at Snowflake Summit.

The brief in your hand is the human-readable view. The actual artifact is the JSON that produced it — Salesforce SOQL filters, warehouse traits, agent role assignments mapped to your Campaign Creation, Personalization, Auditing, and Data Analysis agents. Schema-enforced via Claude's `tool_use` API. Direct feed to your platform. No translation step."

**Pause 10 seconds. Let Ishaan scan. Silence is fine.**

### Beat 4 — The Ask, Candidate Framing (15 sec)

"What I'm asking for: the next interview. I'd rather show you week one than tell you about it. Pick a vertical — I'll build it the same way I'd build it on day one. End of next week you have a working signal pipeline, a ranked list of accounts in buying windows, and a clear answer on whether this is the founding GTM engineer you're looking for. When can we make that happen?"

Stop talking. Eye contact. Let him respond.

---

## Step 2B — Extended Conference Room Flow (20+ min, if Ishaan invites you in)

### Pre-laptop discovery (2 min)

Before opening the laptop:

"Before I show you anything — can I ask what your current pipeline for finding new customers looks like? Conferences, inbound, paid, outbound — what's the mix today?"

**Listen for:**

- Conferences they attend → match against the `conference_registration` signal type (Snowflake Summit, Dreamforce, SaaStr, etc.)  
- Current outbound motion → calibrate where you fit  
- Pain about finding the right companies at the right time  
- Their actual ICP definition → calibrate which vertical to propose

Then: "Perfect. The system I built solves for exactly that. Let me show you."

### Beat 1 — The Live Scan (90 sec)

Kick off the terminal:

python \-m scripts.demo\_scan \--lookback-days 30 \--min-grade B

While it runs (\~30 seconds):

"What I just kicked off is a live scan across GitHub, SerpAPI job boards, Crunchbase funding, LinkedIn, and G2 — configured for your exact ICP. Marketo and HubSpot migration signals, MOPs hiring, warehouse-native stack indicators. Five scanners running in parallel. Each one emits a Signal object in the same schema regardless of source — that's the data engineering layer. The aggregator groups by company, the intent scorer applies weights and recency decay, the grader cuts at configurable thresholds."

When the table prints, point to the top:

"These are companies in active buying windows right now. Not a static list — this ran against live data 30 seconds ago. *[Read the top names off the screen and point at the TYPES column.]* The TYPES column is the whole story at a glance: the A-grades stack three signal types — a funding event, a G2 frustration review, and a live job posting — in the same window. That's when the shelf-life counter starts.

Now, I want to be straight with you about the data, because it matters: the **job postings are live** — pulled from Greenhouse, Lever, and Ashby this morning. The **G2 and funding signals I seed manually** — I pull representative MAP-frustration reviews and public funding rounds and feed them in, because the live G2 path is behind DataDome bot protection and I won't fake live coverage I don't have. The engine — the stacking, the breadth multiplier, the scoring, the grading — is real and running. The collection step for two of the five sources is manual today. That's a day-one Playwright build, and I'd rather tell you that than have you find it later."

### Beat 2 — The Signal Behind the Grade (90 sec)

Pick one B-grade company from the table — the one you pulled a live job posting for Sunday night (Tab 6 has the URL pre-cached):

"This isn't a keyword match on the company name. The scanner found a live job posting, extracted the title, matched it against a MOPs keyword table, floored the signal strength at MODERATE because one marketing automation hire is a real buying signal — not noise.

Look at this — *[name the company and the exact role title from the posting you cached Sunday]*. A MAP-relevant hire, named explicitly. If it's a director-level title, even better — director-level means the budget is already approved.

The scoring formula is ICP fit times 0.45 plus intent score times 0.55, with a recency decay half-life of 14 days for job postings, 21 for G2, 3 for LinkedIn posts. I picked those weights by running the scorer against a hundred labeled accounts and calibrating until the rank order matched what you'd expect. That's the GTM-engineer move — when the CRM tells you 'lead score 72,' nobody can explain why. I built the model that produces the number."

### Beat 3 — The A-Grade Account, Why-Now Block (90 sec)

Open `demo/hubspot-ceiling.html` or run `python -m scripts.marops.cli hubspot-ceiling`:

"This is what an A-grade account looks like — three signals in 8 days. Meridian Analytics. Constructed, but every signal type here is real and firing on live accounts when the stack lines up. Let me walk through it."

Walk through each signal:

"Three days ago — 3-star G2 review on HubSpot. Not a 1-star — a 3-star means they're **evaluating**, not just venting. That's the moment. The quote: 'HubSpot Enterprise doesn't talk to our Snowflake warehouse without a lot of duct tape. Our RevOps team spends 30% of their time on plumbing.' That's a sentence written by someone who is shopping."

"Five days ago — Marketing Data Engineer posting on LinkedIn. The job description says — and I quote — 'building marketing attribution models from scratch outside of a MAP.' That's not scaling HubSpot. That's replacing it."

"Eight days ago — VP Marketing registered for Snowflake Data Cloud Summit. **You have a booth there. She's already decided on the data stack — the question is which MAP runs on top of it.**"

"Three signals in 8 days is an A. The system gives you 6 days before the window closes. This isn't a lead — it's a calendar event."

### Beat 4 — The Output Artifact (60 sec)

Open `out/hubspot-ceiling.json` or scroll past the why-now banner into the segment section:

"This is what your platform actually receives. Salesforce SObject.Field\_\_c syntax — `Account.Current_MAP_Vendor__c = 'HubSpot'`, `Account.Data_Stack__c INCLUDES 'Snowflake'`. Warehouse traits joined natively. Three non-overlapping agent assignments — execution, QA, optimization — exactly as your homepage describes your agent architecture.

I built the brief schema from your job descriptions and platform documentation. The integration is a webhook. SignalForce fires this JSON to your API endpoint when a signal stack hits threshold. The brief in his hand is the human-readable view. The JSON is the artifact."

"And here's why it's a compiler, not a content tool: every other AI brief generator in this space — Jasper, Copy.ai, custom GPT wrappers — produces text a human reads and types into Salesforce. There's a translation step at the end. I built schema enforcement via `tool_use` because free-form LLM output breaks \~20% of the time at scale. With schema enforcement, deterministic. That's the technical move that turns brief generation from a content problem into an infrastructure problem."

### Beat 5 — Repointability (30 sec)

Switch briefly to `demo/veriforce.html`:

"Same engine, completely different vertical. Veriforce — supplier compliance SaaS, industrial enterprise. Tier-2 supplier re-engagement instead of net-new prospect. The why-now banner isn't on this one because the customer scenario is a renewal motion, not a buying-window motion. Same compiler, same agent assignments, different output shape. Config-driven. Same system serves multiple AEs with different ICPs without rebuilding the stack — that's the architectural decision that makes this a product not a script."

### Beat 6 — The Ask, Candidate Framing (90 sec)

"Here's what I'd want to do. I'd rather show you week one than tell you about it.

Pick a vertical from your active sales motion — the one where signal timing matters most. Give me five questions worth of context on your best current customers in that vertical. Day 1, I configure SignalForce for that ICP — target titles, disqualifiers, signal keywords, scoring thresholds. Day 2 through 5, the scanners run against live data. Day 6, I send you a ranked list of every account that hit a B-grade or higher, with the signal stack and shelf life for each.

You evaluate the signal quality directly. If the accounts look like companies you'd actually want to reach — and the timing makes sense — we talk about the role. If they don't, you've still got a piece of code and a clearer view of what timing looks like in your space. Either way, you've seen how I work."

"What I'm building toward is the Founding GTM Engineer conversation. I think the work demonstrates I'm already operating in that role — I'm not asking for time to prove a tool, I'm asking for time to show you what week one of being on your team actually looks like. When can we make that happen?"

Stop talking. Eye contact.

---

## Step 3 — Objection Handlers

### "How do you detect G2 signals? I thought G2 was behind a login."

"It is. G2 uses DataDome for bot protection — it fingerprints the browser, so a Python client with a session cookie doesn't pass it even if you're logged in.

Two real options. A headless browser like Playwright that passes the fingerprint check — that's a one-day build. Or what I use for the demo today: I pull reviews manually in the browser, note the companies and snippets, and seed them into the scoring engine. Same weight, same decay, different collection step.

Honest answer: I hit the wall, diagnosed it, and built a fallback. Every data source has a wall. That's the kind of debugging GTM engineers do constantly. For a production version you'd want Playwright or a scraping proxy service — about $50 a month — to handle the fingerprinting automatically. That's a day-one thing if I'm on the team."

### "How do you detect these signals at scale?"

"Five scanners running in parallel: GitHub repos with MAP integration keywords, SerpAPI job board search across Greenhouse, Lever, and Ashby, Crunchbase funding, LinkedIn content, and G2 reviews. Each scanner emits a Signal object in the same schema regardless of source. The aggregator groups by company, the intent scorer applies weights and recency decay, the grader cuts at configurable thresholds.

The whole thing reconfigures by swapping a YAML file. That's the architectural decision that makes this a GTM-engineer tool, not a script — different AE, different ICP, same engine, no redeployment."

### "What's the shelf life — how do you handle signal decay?"

"Each signal type has a half-life in days — job postings decay over 14 days, G2 reviews over 21, LinkedIn posts over 3\. The intent score at detection time gets multiplied by e^(-ln2 × days\_elapsed / half\_life). A job posting from yesterday scores roughly 2x a posting from two weeks ago by design.

Companies drop from the active queue when their combined score falls below the C-grade threshold. They re-enter automatically if a new signal fires. The Reddit feedback on SignalForce was unanimous on this — timing beats volume, decay matters more than scoring precision. So I built it that way."

### "How does this compare to Clay?"

"Clay is enrichment — you bring a list, Clay fills in the fields. SignalForce is timing — it generates the list and tells you why each company is on it right now. Complementary, not competitive. You'd feed a SignalForce queue into Clay for contact enrichment if you wanted both layers.

But the bigger point — I'm not pitching a tool to compete with Clay. I'm showing you evidence of how I think about the problem. The actual question is whether someone who builds this kind of thing belongs on your team."

### "Compiler — how is that different from Jasper or Copy.ai?"

"Jasper takes a prompt and produces text. The output is a string. A human reads it, decides if it's good, copies it into wherever they're publishing. Translation step at the end.

The marops compiler takes a YAML config plus a signal stack, produces a typed JSON object — Salesforce SOQL filters, warehouse trait queries, agent role assignments, QA rules. The output is a structure. It plugs into Conversion's segmentation engine and campaign builder directly. No translation step.

Concretely: Jasper writes you an email subject line. The compiler writes you a brief where the segment is `Account.Tier__c = 'Tier 2'`, the suppression rule is `IsChurned__c = TRUE`, and the agent assignment is `optimization` for variant selection. One is content. The other is config. That's the distinction."

### "What would it take to configure this for our actual ICP?"

"About an hour. The ICP is defined in YAML — target titles, disqualifiers, signal keywords, scoring thresholds, and a company blocklist so your existing customers and named competitors never surface in the feed. I'd ask you five questions about your best current customers and translate the answers into config. Scanner picks it up on the next run. No redeployment.

If I'm being honest about why I'm here — that's the work I want to be doing on your team. Configuring this against your real ICP shouldn't be a trial. It should be week one."

### "We use Heyreach / OutboundSync / Sumble / Gong — do you know these?"

Be honest. The JD specifically values craft over output:

"Sumble I'd want to dig into in week one — haven't built against their API yet. Heyreach for LinkedIn I've evaluated but my LinkedIn scanner is read-only right now. OutboundSync for CRM hygiene is in the same lane as the Salesforce QA rules in the brief I just showed you — adjacent skill set, different surface. Gong I've used as a customer, not a builder.

Day-1 priority: get fluent in Heyreach and Sumble. They're how I ship to production faster than rebuilding their layer from scratch. Already built against Apollo, Hunter, Prospeo, ZeroBounce, Instantly, Salesforce, HubSpot, and the Anthropic stack. The muscle memory transfers."

### "Is Meridian Analytics a real company?"

"Constructed — I built it this weekend to demo the why-now engine. But every signal type is real and firing on live accounts when the stack lines up. G2 quote modeled from actual public HubSpot reviews. Hiring signal modeled on three real Marketing Data Engineer postings from last week. Conference registration logic uses the public Snowflake Summit attendee directory.

I didn't want to use a real company name on a public demo I might share. The live scan you just saw is real companies — the names on the screen a minute ago. The trial week, or week one if you'd rather skip the trial framing, uses your real ICP."

### "Can RevOps just do this?"

"Your JD says GTM Engineering at Conversion isn't just outbound or just RevOps — that's why this role exists. RevOps owns Salesforce hygiene, lead routing, attribution downstream. GTM Engineering owns the systems that produce qualified pipeline upstream — signal detection, ICP modeling, intent, creative copy, the data pipelines RevOps queries.

Specifically on signal-decay engines: RevOps doesn't typically build them. That's an infrastructure problem — multi-source ingestion, recency weighting, freshness SLAs. Different skill stack. The work I just showed you is the GTM-engineering side. SignalForce isn't a CRM hygiene tool. It's a system for replacing intuition with a ranked feed."

### "You're too junior — we want 5+ years"

"Neil's posted publicly that experienced engineers often come with fixed mental models. Conversion's hiring pattern says craft over years.

Specifically: the why-now engine in this brief was built in 48 hours after Reddit feedback. Senior GTM hires from the 6Sense/Demandbase era haven't shipped against `tool_use` schema enforcement, haven't debugged DataDome fingerprinting, haven't built the intuition for which parts of LLM output are deterministic and which aren't. I have. SignalForce is 547 tests passing, five scanners shipped, multiple verticals working, the why-now layer on top. That's the credential. Years 1–5 of someone else's career are not."

### "What's your pricing? How would you work with companies?"

Reframe immediately back to the role:

"I'm not actually here to sell you a tool. I'm here because your JD describes the work I want to be doing, and the way I demonstrate I can do it is by showing you the work I've already done. If we're talking pricing, we're talking the wrong thing. If the question is whether someone who builds this kind of system belongs on your team — that's the conversation I want."

### "We're not hiring right now"

"Understood. Is the Founding GTM Engineer role still posted, or has it been filled?"

If filled: "Congrats on the hire. Anything else on the GTM or infrastructure side that's bottlenecked? Same skill set, different output."

If on hold: "Got it. Can I leave my info and check back?"

### If the live scan breaks

1. Pull up the screenshot you took Sunday night: "Live scan from last night, same verticals."  
2. Skip to `demo/hubspot-ceiling.html` directly: "Let me show you what an A-grade looks like instead."  
3. If everything fails, open `out/hubspot-ceiling.json` in VS Code and walk through it manually.

Script: "API timeout — let me show you the pre-run from last night." Don't apologize. Production discipline is committing fallbacks.

### If they ask to run it against a specific company live

- Drop the company into `config/g2_seeds.yaml` with relevant signals  
- Re-run `python -m scripts.demo_scan` — 30 seconds  
- Or pull up the Greenhouse/Ashby job board for that company directly

### If Ishaan declines entirely

"Fair. Can I leave the GitHub link — marops branch with the why-now engine. And is there a best way to follow up in two weeks?"

Then leave. Don't linger. Don't re-pitch.

---

## The Four Verbatim Concepts (memorize)

1. **"GTM engineers replace intuition and manual research with a system. I built one."** The through-line. Use it as the opener if you can.  
     
2. **"Three signals in 8 days. Buying window closes in 6 days. This isn't a lead — it's a calendar event."** The why-now framing in one breath.  
     
3. **"She registered for Snowflake Summit 8 days ago. You have a booth there. She's already decided on the data stack — the question is which MAP runs on top of it."** The conference hook. The sharpest single line in the pitch. Earns the next conversation.  
     
4. **"I'm not asking for time to prove a tool. I'm asking for time to show you what week one of being on your team actually looks like."** The candidate framing of the ask. Use this verbatim when the ask comes up.

---

## What to Show — File-by-File (Candidate Framing)

Every file is evidence of a specific JD bullet. Frame it that way.

### `github.com/sami2919/SignalForce` — README

"Production discipline up front — 547 tests passing, 77% coverage overall and 87–93% on the core scanners, MIT licensed. Open source because I wanted GTM engineers to actually use it. That's how I know what the role looks like in practice."

### Live terminal: `python -m scripts.demo_scan`

"JD bullet 1: design and build scalable systems for prospecting. Five scanners in parallel, configurable by YAML, A/B/C grading. This is the data engineering layer applied to GTM."

### `scripts/icp_fit_scorer.py` \+ `scripts/intent_scorer.py`

Show the scoring formula in a visible block: `COMBINED = (ICP_Fit × 0.45) + (Intent × 0.55)`.

"JD bullet on ICP modeling. Weighted scoring model, calibrated against real signal types, recency decay. When the CRM gives you 'lead score 72' with no explanation, this is what a GTM engineer builds in response."

### `scripts/signal_aggregator.py`

"Enrichment waterfall pattern. Group by company, deduplicate, confidence-score, grade. Every serious outbound team uses this — very few have engineers who built it."

### `examples/marops/hubspot-ceiling.yaml`

"JD bullet on segmentation logic. Config-driven. Same engine, different ICP — that's the architectural decision that makes this a system, not a script. Serves multiple AEs with different territories without rebuilding the stack."

### `demo/hubspot-ceiling.html`

"JD bullet on lifecycle nurture and creative copy. Buying committee modeled — VP Marketing plus Marketing Data Engineer. Urgency window — 6 days. Conference trigger baked in. This is account planning, operationalized."

### `scripts/marops/briefer.py` — `tool_use` block

"The compiler. `tool_use` schema enforcement at the API level. Without it, free-form JSON breaks 20% of the time at scale. With it, deterministic. That's the difference between prototype and something you ship during a customer migration."

### `out/hubspot-ceiling.json`

"What the platform actually receives. Every field maps to a setting in your campaign builder. Webhook integration. Direct feed, no translation step."

### `demo/veriforce.html`

Backup demo. Different vertical, no why-now banner. Proves repointability.

---

## After the Meeting

**Same day:**

- Email Ishaan: `demo/hubspot-ceiling.html` attached, GitHub link to SignalForce, one-paragraph recap of week-one proposal  
- Subject: "From this morning — week-one proposal \+ GitHub work sample"  
- Body keeps the candidate framing: "Not pitching a tool — pitching the work."

**Within 48 hours if he says yes:**

- Get the vertical \+ ICP definition from him  
- Configure `config/config.yaml` for that ICP  
- Run scanner for 24 hours, send sample output Wednesday  
- Full ranked B-grade-or-higher list by Monday

**Within 48 hours if he says no or doesn't respond:**

- Send Loom v5 via LinkedIn DM  
- One sentence: "If the timing shifts, I'm here." Don't re-pitch.

---

## FAQ Summary

| Question | Short Answer |
| :---- | :---- |
| Signal detection sources? | GitHub, SerpAPI job boards, Crunchbase, LinkedIn, G2. Apollo \+ Prospeo waterfall. |
| G2 / DataDome? | Hit the wall, diagnosed it, built manual seeding fallback. Playwright is the production path. |
| Shelf life mechanics? | Half-life per signal type, exponential decay, 14-day window for job postings. |
| Different from Clay? | Clay is enrichment. SignalForce is timing. Complementary. The real question is whether I belong on your team. |
| Different from Jasper? | Jasper produces strings humans translate. The compiler produces JSON your platform ingests. |
| Integration path? | Webhook. SignalForce fires brief JSON to API endpoint when signal stack triggers. |
| Real or synthetic Meridian? | Constructed for the demo. Live scan is real companies. Trial week uses your real ICP. |
| Compensation? | Wrong question. The right question is whether someone who builds this belongs on your team. |
| If demo breaks? | Pre-rendered HTML fallback. Sunday-night screenshot of the live scan. JSON walkthrough as last resort. |
| Week 1 deliverable? | Pick a vertical. Day 6 you have a ranked list of every B-grade-or-higher account with signal stack and shelf life. |

---

## The Meta-Point

You are not selling SignalForce. You are demonstrating that you already are the Founding GTM Engineer.

The work in his hand isn't an offering. It's evidence. Every file demonstrates a specific JD bullet — signal detection, ICP modeling, intent scoring, signal aggregation, config-driven architecture, lifecycle briefs, debugging at data-source walls. Seven JD bullets covered. Not pitched. Demonstrated.

The compiler frame is technical category evidence. The why-now engine is operational evidence. The conference hook is evidence you think about GTM at the level of specific customer moments. The live scan is evidence the system actually works against live data.

The ask isn't a trial — it's the next interview. You'd rather show him week one than tell him about it. End of next week he has a working signal pipeline for a vertical he picked, and a clear answer on whether you're the founding GTM engineer he's looking for.

The walk-in is the delivery. The work is the credential. The script is the frame.

---

*Version: 8.2 — Re-synced against the marops branch after a parallel session landed 9 commits (company_blocklist, funding_seed_scanner, real g2 seeds, TYPES column in demo_scan). The live scan now shows genuine A-grade stacking (Vanta/axonius via funding + G2 + job). Beat 2 rewritten for **honest-seed framing**: the job postings are live and verifiable; the G2 + funding signals are manually seeded representative data (a DataDome fallback), volunteered before Ishaan asks — because the seeded G2 quotes are authored and the funding URLs/stages aren't verifiable, so presenting them as live detections on named real companies was a credibility risk. Meridian Analytics kept as the constructed deep-dive brief. Test claim now 547 passing/77%. Carries forward v8.1: three render bugs fixed at the source (template + models.py) + Meridian brief regenerated clean, real walk-in date, GitHub-403 / g2_seeds / flaky-suite pre-flight items, company_blocklist in the config answer. Compiler frame and Ishaan-JD vocabulary preserved.*  
