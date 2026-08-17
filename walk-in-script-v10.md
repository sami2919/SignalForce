N# Conversion Walk-In Script v10 — The Reveal, Aligned

**Audience:** Ishaan Maheshwari, who leads GTM Engineering at Conversion. Verify his last name in the lobby directory before you go up.

**Date:** Monday, June 1, 2026  
**Location:** 300 Beale St, Suite A, San Francisco  
**Arrival window:** 9:30 to 10:00 AM PT  
**Goal:** The next interview.

---

## What changed in v10

This is the day I've been working toward for nine months.

Twelve days ago, on May 19th, Conversion shipped Conversion Agents. Neil's launch post called it the first agent layer built natively into a marketing automation platform. Vibe marketing. Twenty-five-plus prebuilt agents. A native data layer sitting on Salesforce plus your warehouse plus product events. A reviewable artifact for every run. SOC 2 Type II. An MCP server exposed so Claude Desktop and Cursor can reach Conversion's audiences and campaigns directly.

v9 was written before that shipped. The script needed to walk in knowing what Conversion just put into the world — not just what Ishaan's JD says they want to build.

v10 keeps everything that worked in v9. The three-act personal arc. The honest-seed framing on the live scan. The Meridian A-grade reveal. The compiler frame. Repointability. The candidate-not-vendor ask.

What v10 adds is the spine that reportedly got Ishaan hired in the first place. Ishaan walked into Conversion and broke down what was wrong with the current GTM and MarOps category. The architecture argument. The own-data-versus-rent-data thesis. The migration-paralysis insight. The line that the incumbents have been running on software invented in 2006.

The winning move on Monday is to mirror that thinking back at him in his own language — and then extend it one step further than he's published it. Walking in with a critique is table stakes. Walking in having advanced his own argument is what makes the hire obvious.

---

## Mindset

You are not a candidate asking for a chance.

You are a builder walking in to show the person who wrote the job description what you've been doing in preparation for it — without knowing he was going to write it.

Every once in a while, a category of work comes along that changes how a thing gets done. And the people who shape that category aren't always the ones with the most years on a resume. They're the ones who saw it coming early and started building.

Three years ago at AWS, you didn't know what to call this role. Two years ago at Circuit, you still didn't. One year ago when you started SignalForce, you began to. Six weeks ago when Ishaan published the JD, the name was finally there.

Twelve days ago, Conversion shipped Agents.

Today, you walk in and you reveal the synthesis.

The voice you carry into the room is slow. Deliberate. A half-beat behind what feels natural. You're not selling. You're unveiling. The pace is the proof.

---

## Carry-ons

Laptop, charged 100%, tabs in this order:

1. Tab 1: `github.com/sami2919/SignalForce` README on the `marops` branch
2. Tab 2: Terminal ready for `python -m scripts.demo_scan --lookback-days 30 --min-grade B`
3. Tab 3: `examples/marops/hubspot-ceiling.yaml`
4. Tab 4: `demo/hubspot-ceiling.html` rendered locally in Chrome
5. Tab 5: `demo/veriforce.html` as backup
6. Tab 6: One real job posting URL from a B-grade company in Sunday night's scan
7. Tab 7: Neil's "Introducing Conversion Agents" launch post — open and ready, in case the conversation goes deep
8. VS Code: `icp_fit_scorer.py` + `intent_scorer.py` + the `tool_use` block in `briefer.py`

Physical:

- Two printed briefs. The Meridian one — `hubspot-ceiling.html` — folded in half, back pocket. Veriforce in the bag.
- Resume in the bag. Hand only if directly asked.
- Business card with GitHub QR + "marops branch" written on the back.
- Phone: Ashby JD screenshot, Next Play article, Sunday-night scan screenshot, Neil's launch post, Ishaan's migration-paralysis LinkedIn post. All cached.

---

## Pre-flight, Sunday night

Same pre-flight discipline as v9. Three render bugs are fixed at the source. Don't regenerate the demo brief via `python -m scripts.marops.cli` — it calls Claude live and rewrites the rehearsed copy. Render from existing JSON if you need to refresh.

Then everything else, in order.

1. Run the live scan and screenshot the top five
2. Pull one live job posting URL from a B-grade company and cache it in Tab 6
3. Verify Ishaan's last name on LinkedIn — confirms Maheshwari
4. Re-read Neil's Conversion Agents launch post on `conversion.ai/blog` one more time
5. Re-read Ishaan's migration-paralysis post one more time
6. Read the Ashby JD and the Next Play piece one final time
7. Cold-run the short pitch out loud under ninety seconds
8. Cold-run the long form once end-to-end with the laptop

Verify the API keys are live. Both `SERPAPI_KEY` and `GITHUB_TOKEN` in `.env`. The scan needs to run without `403 quota exhausted`. On the last dry run GitHub was rate-limited and "five scanners in parallel" became three. Let the quota reset, or swap in a fresh token.

The rate-limit handler bug. If the scan hangs, Ctrl-C immediately and fall to the Sunday screenshot. Don't troubleshoot in front of him.

If you plan to use the "drop a company in and re-run" move during objections, `config/g2_seeds.yaml` is still the `Example Corp` placeholder. Seed two or three real G2 reviews into it Sunday night, or set `G2_SESSION_COOKIE` in `.env`.

Don't plan to run the full `pytest` suite live. Cite 547 tests passing from a clean run. If you must show green live, run `pytest tests/marops/ -q`.

Print both briefs. Confirm 300 Beale St on the map. Charge everything.

Midnight. Stop. Sleep.

Monday morning:

- Re-screenshot the Ashby JD.
- Re-run the live scan.
- Verify tabs.
- Arrive 9:30 to 10:00 AM.
- Confirm the lobby directory lists Conversion or Relentlo before going up.

---

## Step 1 — Reception

Twenty-five seconds. Calm pace. Eye contact.

> "Hi — sorry to drop in cold. My name's Sami. I'm a GTM engineer in SF and I'm here to see Ishaan. He published the Founding GTM Engineer post six weeks ago. Twelve days ago you shipped Conversion Agents. I've spent the last nine months building the open-source version of the systems his JD describes. I have one concrete thing to show — takes ninety seconds. Your careers page says you work in-person five days a week because it makes you faster. That's why I walked in instead of sending a Loom. Is he available this morning?"

Alternative version:

> "Hi — sorry to drop in cold. My name's Sami. I'm a GTM engineer and I recently moved to SF maybe 2-3 weeks ago. Funny enough i’m staying in the building right next door so I’m always walking past your guys office. And out of curiosity i did research on what you guys do, which by the way i love what you guys are doing a platform that connects your CRM, your warehouse, and your product data into a single context layer. I come from a GTM engineering background so I think this is a huge step up from marketo, hubspot, pardot. I’m here to see you, or ishaan really. He published the Founding GTM Engineer post six weeks ago. I've spent the last couple months building the open-source version of the systems he describes in it. I have one concrete thing to show — takes ninety seconds. Your careers page says you work in-person five days a week because it makes you faster. That's why I walked in instead of sending a Loom. Is he available this morning"

Hand them the business card. Not the resume. Not the brief.

If he's busy: get a specific return time.

If they ask about Ashby:

> "Applied this morning. The JD said you operate with complete autonomy and care about craft over output. Figured a working prototype lands faster than a resume in queue."

Twenty-minute hard stop. After that, leave the brief and the card. Send the Loom that afternoon.

---

## Step 2A — The Short Form

Ninety seconds, if he's between meetings.

This is the day I've been working toward for nine months.

Every once in a while, a category of work comes along that changes how a thing gets done. And the people who shape that category aren't always the ones with the most years on a resume. They're the ones who saw it coming early and started building.

Six weeks ago Ishaan gave that category a name. Twelve days ago he and Neil shipped Conversion Agents into it. Today you walk in with what you've been building toward both.

Three movements. Twenty-five seconds, thirty seconds, thirty-five seconds.

### Movement One — The Through-Line

Look at him. Don't open the laptop yet. Slow down a half-beat from what feels natural.

> "Ishaan — for the last three years I've been doing the same job at three different companies, under three different titles.
>
> At AWS I was an Applied AI Solutions Architect on the GenAI team. Eleven Fortune 500 accounts. Three terabytes of documents per account. Production RAG on Bedrock for buyers who didn't know what production AI was supposed to feel like.
>
> At Circuit AI I was the founding product engineer at a manufacturing AI startup. Drove a hundred percent pipeline growth quarter over quarter. Sourced eighty-two percent of opportunities. Built an ML inference pipeline for prospect scoring at ninety-five percent accuracy across thirty iterations.
>
> Before that I founded ProspectNav. Scaled it to fifty paying accounts with no sales team and no marketing budget.
>
> Different industries. Same job."

Pause.

> "Replace intuition and manual research with a system.
>
> That's the through-line. That's what your JD describes. Six weeks ago you finally gave it a name. Twelve days ago Neil's post called it vibe marketing on a native data layer. Ninety seconds and I'll show you what nine months of work toward that name looks like."

Open the laptop. Calmly.

### Movement Two — The Live Reveal

Run `python -m scripts.demo_scan --lookback-days 30 --min-grade B`.

> "Five scanners in parallel. GitHub, SerpAPI across Greenhouse and Lever and Ashby, Crunchbase, LinkedIn, G2. Configured against your ICP. Companies that are currently bottlenecked on a legacy MAP — Marketo, HubSpot Enterprise, Pardot."

Table prints.

> "The names at the top are real companies in active buying windows, scored from live data. The TYPES column is the story at a glance — the top ones hit A-grade because three signal types fire together: a funding round, a G2 frustration review, and a live job posting.
>
> Straight answer on the data, because it matters: the job postings are live, pulled this morning. The G2 and funding signals I seed manually because the live G2 path is behind DataDome and I won't fake live coverage I don't have. The engine — stacking, scoring, grading — is real. Two of five collection paths are manual today. That's a day-one Playwright fix."

### Movement Three — The A-Grade and the Ask

Switch to `demo/hubspot-ceiling.html`. Pull the printed brief from your back pocket. Hand it to him.

> "And this is what an A-grade looks like. Three signals in eight days. G2 review three days ago — VP Marketing called HubSpot's Snowflake integration 'a lot of duct tape.' Hiring signal five days ago — Marketing Data Engineer building attribution from scratch outside a MAP. Conference registration eight days ago. She registered for Snowflake Summit.
>
> Conversion has a booth at Snowflake Summit.
>
> Three signals. Six days of shelf life. She's already decided on the data stack — the question is which MAP runs on top of it."

Pause. Ten seconds. Let him scan. Silence is the point.

> "That's not a lead. That's a calendar event."

Wait again.

> "Ishaan, I'd rather show you week one than tell you about it. Pick a vertical from your active sales motion. End of next week you have a working signal pipeline, a ranked list of accounts in buying windows, and a clear answer on whether I'm the founding GTM engineer you're looking for.
>
> I'm not asking for a trial. I'm asking for the next interview. When can we make that happen?"

Stop. Eye contact. Don't fill the silence.

---

## Step 2B — The Long Form

If he invites you in. The keynote. Nine acts. Fifteen to eighteen minutes if you don't rush.

The architecture argument runs as the spine. Personal arc opens it. The Conversion Agents launch sits as the worked example. Ishaan's own published thinking gets mirrored back at him. The pitch closes by extending his thesis one step further than he's published it.

### Before You Open the Laptop

Three minutes of discovery.

> "Before I show you anything — can I ask what your current pipeline for finding new customers looks like? Conferences, inbound, paid, outbound — what's the mix?"

Listen. The conferences they attend become the conference-trigger argument later. The pain about timing becomes the wedge. The ICP definition shapes what you emphasize.

> "Perfect. The system I built solves for exactly that. But before I get to the demo, I want to back up and tell you how I got here — and where I think the category is going. Because the two arguments are the same argument."

### Act One — The Three Years

Ninety seconds. No laptop. Just you, telling the story.

> "Three years ago I was finishing my Computer Information Systems degree at UT Dallas and running an internship at AWS as an Applied AI Solutions Architect.
>
> The team was technical business development for GenAI. The job was deeply technical. I was on calls with Fortune 500 customers — eleven of them — architecting RAG systems on Bedrock with Claude Sonnet. Three terabytes of documents per account. Bizarre legacy sources. SharePoint via Graph API with broken pagination. Email archives. PDFs with formatting so inconsistent the embedding model couldn't chunk them.
>
> Production systems for buyers who didn't know what production AI was supposed to feel like.
>
> Then I joined Circuit AI as the founding product engineer. Tyson Tuttle had just raised fifteen to twenty-five million from Breyer Capital and 7BC. Manufacturing AI. Answers in under ten seconds for a domain where the industry average was six minutes.
>
> I built the AI backend from scratch. RAG pipelines that ingested CAD drawings, bills of materials, service manuals. Optimized our retrieval from sixty-seven percent accuracy to ninety-four percent. Built confidence-based routing so the system knew when to auto-generate versus flag for human review.
>
> And on the GTM side — a hundred percent pipeline growth quarter over quarter. Sourced eighty-two percent of opportunities. ML inference for prospect scoring at ninety-five percent accuracy across thirty model iterations. Led fifty-plus customer demos. Automated sales workflows with Python and Clay and HubSpot — cut manual sales ops work by sixty percent.
>
> Before all of that, I founded ProspectNav. Multi-agent B2B SaaS on CrewAI and LlamaIndex. Scaled to fifty paying accounts with no sales team and no marketing budget. Just me. Build the product. Find the customers. Iterate."

Pause.

> "Three different jobs. Three different titles. Same work.
>
> And I kept seeing the same gap. GTM teams were the last teams to get systems. Engineering had MLOps. Product had analytics infrastructure. Sales had a CRM, a vibes-based lead score, and an SDR running plays in Notion.
>
> That gap is the role I want to build inside of."

### Act Two — The Architecture Argument

Ninety seconds. This is the new spine in v10. Lead with the critique. Mirror Ishaan's published thinking back at him in his own language.

> "But before I get to the system I built — I want to spend a minute on what I think is actually broken in this category. Because I think the diagnosis is the answer to why the role you wrote the JD for exists in the first place.
>
> For two decades, marketers have been stuck using software invented in 2006. Eloqua. Pardot. Marketo. HubSpot Marketing Hub. These tools were built before LinkedIn ads existed, let alone AI-driven campaigns. Built before warehouse-native architecture was viable. Built when marketing and sales data lived in separate silos.
>
> The architecture has a specific shape. The MAP sits downstream of the CRM and the warehouse, syncing data through fragile pipelines. HubSpot's Snowflake integration flattens warehouse objects into contact properties. Marketo Measure's direct share works in one Azure region. These aren't UX problems. These are architectural decisions made before the warehouse was the system of record.
>
> Which means every AI feature the incumbents have shipped this year is a chat widget bolted onto a fifteen-year-old platform. Bolt-ons can't fix architectures that were never designed for agents to operate inside them. Agents on top of stale data are agents that hallucinate."

Pause.

> "And the second-order problem — the structural one — is that point tools that rent data are about to get eaten. Enrichment is being replaced by ChatGPT. Routing tools and outbound sequencers are getting their lunch eaten by AI-native tools. The question for any GTM leader evaluating their stack in 2026 isn't 'does this tool solve a problem.' It's 'does this tool own data, or does it rent it.'
>
> That's the part most people miss. The moat the incumbents have isn't just product quality. It's switching cost. Migration fear. MarOps leaders who say some version of 'Marketo stopped innovating, but at least we know it works.' The risk of being wrong feels worse than the risk of staying.
>
> But a couple days ago you guys dropped conversion agents — and what that launch actually does, architecturally, is collapse the switching cost. A four-week migration with agent assistance. The fear stops being the moat."

Pause.

> "Which is the part I want to extend one step further than I've seen anyone publish.
>
> If agents collapse switching cost, the entire category gets repriced overnight. The incumbents' moat was never the product. It was the cost of leaving. And the moment that cost goes to zero, every conversation Conversion has with a Marketo shop becomes a different conversation.
>
> That's not a marketing story. That's a GTM story. And that's the GTM problem I think the role you wrote the JD for is actually solving."

### Act Three — The Trigger

Forty-five seconds. Bridge from the category argument to the work.

> "So nine months ago I started building SignalForce. Open source. MIT licensed. Config-driven GTM toolkit. Five signal scanners. Intent scoring. Lifecycle briefs. Five-hundred-forty-seven tests passing. About five thousand people in the community Slack — the community that exists because the role you're hiring for is a category that didn't have a name two years ago.
>
> Two weeks ago I posted it on Reddit. And I got hammered on one piece of feedback. Repeated by multiple practitioners. Same point, over and over."

Pause.

> "Timing beats volume.
>
> ICP matching is table stakes. The real signal isn't 'this company looks like our customers.' It's 'this company is in a buying window right now and the window closes in six days.' G2 review velocity. Conference registrations. The second MOPs hire. A Marketing Data Engineer JD that says 'build attribution outside a MAP.' Those predict buying intent. Funding from six months ago is noise.
>
> So I built a why-now layer on top. Pure Python. No LLM. Deterministic signal decay. Forty-eight hours from the Reddit post to shipped code.
>
> Because that's how fast a GTM engineer should ship in response to real practitioner feedback."

Pause.

> "Let me show you what it does."

Open the laptop. Now.

### Act Four — The Live Scan

Ninety seconds. Run `python -m scripts.demo_scan --lookback-days 30 --min-grade B`.

> "Five scanners in parallel.
>
> GitHub for repos with MAP integration keywords. SerpAPI across Greenhouse, Lever, and Ashby for job postings. Crunchbase for funding events. LinkedIn for content signals. G2 for review activity.
>
> Each scanner emits a Signal object in the same schema, regardless of source. The aggregator groups by company. The intent scorer applies weights and recency decay. The grader cuts at configurable thresholds."

Table prints.

> "These are companies in active buying windows right now. Not a static list, not a CSV someone built last quarter. This ran against live data thirty seconds ago.
>
> [Read the top names off the screen. Point at the TYPES column.]
>
> The TYPES column is the story at a glance. The A-grades stack three signal types — a funding event, a G2 frustration review, and a live job posting — in the same window. That's when the shelf-life counter starts.
>
> Now, I want to be straight with you about the data. Because it matters."

Pause.

> "The job postings are live. Pulled from Greenhouse, Lever, and Ashby this morning.
>
> The G2 and funding signals I seed manually. I pull representative MAP-frustration reviews and public funding rounds and feed them into the scoring engine — because the live G2 path is behind DataDome bot protection, and I won't fake live coverage I don't have.
>
> The engine — the stacking, the breadth multiplier, the scoring, the grading — is real and running. The collection step for two of the five sources is manual today. That's a day-one Playwright build. I'd rather tell you that than have you find it later."

### Act Five — The Signal Behind the Grade

Sixty seconds. Pick a B-grade company from the table — the one whose live job posting URL you cached Sunday in Tab 6.

> "This row isn't a keyword match on the company name. The scanner found a live job posting on Greenhouse, extracted the title, matched it against a MOPs keyword table, floored the signal strength at MODERATE — because one marketing automation hire is a real buying signal, not noise.
>
> Look at this. [Name the company and the exact role title from the posting you cached Sunday.] A MAP-relevant hire, named explicitly. If it's a director-level title, even better — director-level means the budget is already approved.
>
> The scoring formula is ICP fit times 0.45 plus intent times 0.55. Recency decay with a fourteen-day half-life for job postings, twenty-one for G2, three for LinkedIn posts.
>
> I picked those weights by running the scorer against a hundred labeled accounts and calibrating until the rank order matched what you'd expect. When the CRM tells you 'lead score 72,' nobody can explain why. That's the 6sense problem in three words. I built the model that produces the number — and documented every weight."

### Act Six — The A-Grade Reveal

Ninety seconds. This is the moment.

Open `demo/hubspot-ceiling.html`. Pull the printed brief from your back pocket. Hand it to him.

> "And this is what an A-grade looks like.
>
> Three signals stacked. Eight days. One account.
>
> Three days ago — three-star G2 review on HubSpot Enterprise. Not one-star. A one-star is someone who's already gone. A three-star is someone who's evaluating.
>
> That's the moment.
>
> The quote: 'HubSpot Enterprise doesn't talk to our Snowflake warehouse without a lot of duct tape. Our RevOps team spends thirty percent of their time on plumbing.' That's a sentence written by someone who is shopping. And it's the exact pattern Neil's launch post calls out — flat contact fields instead of warehouse objects. This person knows their stack is the bottleneck.
>
> Five days ago — Marketing Data Engineer posting on LinkedIn. The job description says, verbatim, 'building marketing attribution models from scratch outside of a MAP.' That is not a sentence about scaling HubSpot. That is a sentence about replacing it.
>
> Eight days ago — VP Marketing registered for Snowflake Data Cloud Summit."

Pause.

> "Conversion has a booth at Snowflake Summit.
>
> Three signals. Six days of shelf life left. She's already decided on the data stack — the question is which MAP runs on top of it.
>
> This isn't a lead.
>
> This is a calendar event.
>
> And the brief in your hand tells your AE team exactly when to walk up to her booth meeting and exactly what to say."

Pause. Let him read. Don't speak.

### Act Seven — The Compiler

Ninety seconds. Switch to `scripts/marops/briefer.py`. Show the `tool_use` block.

> "Now the part that earns the platform framing — and the part that maps directly to what Conversion Agents shipped twelve days ago.
>
> Every other AI brief tool in this space — Jasper, Copy.ai, custom GPT wrappers — produces a document. A human reads it, types it into Salesforce, drags it into the campaign builder.
>
> A translation step at the end. And that translation step is where speed dies. That's the difference between content tools and infrastructure.
>
> So I built a compiler.
>
> The brief in your hand isn't the artifact. The artifact is the JSON that produced it. Salesforce `SObject.Field__c` syntax. Warehouse trait queries. Agent role assignments that map to your Campaign Creation, Personalization, Auditing, and Data Analysis agents — the four named on your agents page. Schema-enforced via Claude's `tool_use` API.
>
> Without schema enforcement, free-form LLM JSON breaks roughly twenty percent of the time at scale. With it — deterministic.
>
> That's not a workaround. That's the architectural decision that turns brief generation from a content problem into an infrastructure problem. The same decision that lets your Conversion Agents return a reviewable artifact per run instead of a paragraph a human has to translate."

Pause.

> "Same way I think about every place LLMs touch production data. Schema. Fallback. Determinism. The way I learned at AWS. The way I shipped at Circuit. The way I'd ship here.
>
> And the bigger point — the marops compiler isn't a tool that competes with Conversion Agents. It's an upstream system that produces the artifact your agents consume. Signal detection on one end. Reviewable artifact on the other. The whole pipeline lives in one schema."

### Act Eight — Repointability

Thirty seconds. Switch briefly to `demo/veriforce.html`.

> "Same engine. Completely different vertical. Veriforce — supplier compliance SaaS, industrial enterprise. Tier-two supplier re-engagement, not net-new prospecting. Renewal motion, not buying window. Different output shape, same compiler, same agent assignments.
>
> Config-driven. The same system serves multiple AEs with different ICPs without rebuilding the stack.
>
> That's the architectural decision that makes this a product, not a script."

### Act Nine — The Ask

Ninety seconds. Close the laptop. Eye contact. Slow down.

> "Ishaan, here's what I want.
>
> Three years. Three companies. Three titles. The same job, every time.
>
> AWS taught me production AI for enterprise customers. Circuit taught me to run GTM as engineering. ProspectNav taught me to build, sell, and support a system end-to-end by myself. SignalForce is the synthesis.
>
> Six weeks ago you wrote the JD for the role I've been training for. Twelve days ago you and Neil shipped the platform that role operates inside of."

Pause.

> "So here's the proposal.
>
> Pick a vertical from your active sales motion — the one where signal timing matters most. Give me five questions worth of context on your best current customers. Day one, I configure SignalForce for that ICP — target titles, disqualifiers, signal keywords, scoring thresholds, plus a blocklist so your existing customers and named competitors never surface in the feed. Days two through five, the scanners run against live data. Day six, you have a ranked list of every account that hit B-grade or higher, with the signal stack and shelf life for each.
>
> You evaluate the signal quality directly. If the accounts look like companies you'd want to reach, and the timing makes sense, we talk about the role. If they don't, you've got a piece of code and a clearer view of what timing looks like in your space.
>
> Either way, you've seen how I work."

Pause.

> "I'm not asking for a trial. I'm asking for the next interview."

Stop. Don't fill the silence.

---

## Step 3 — Objection Handlers

### "What do you actually think of Conversion Agents?"

The question Ishaan is most likely to ask. Have the answer ready.

> "Three things stand out, in order of how impressed I am.
>
> First — the architecture decision to build the agents on a native data layer instead of a chat sidebar. That's not a feature. That's the whole game. Agents on top of stale data hallucinate. Agents on a native layer don't.
>
> Second — the reviewable artifact per run. SOC 2 Type II, permission-scoped, auditable, replayable. That's the part that makes enterprise security teams sign off on agent autonomy. Everyone else is going to bolt this on after the first incident.
>
> Third — the MCP server. Exposing Conversion's audiences and campaigns to Claude Desktop and Cursor means the platform is reachable from anywhere a GTM engineer wants to work. That's the bet that agents-as-infrastructure beats agents-as-feature.
>
> What I'd push on, honestly — the public metrics in the launch post are internal pilot numbers, not independently verified. Forty-four percent MOps reduction, eighteen-hundred hours saved, ten-times faster campaign launch. Those are useful directional claims for marketing. For the GTM engineering conversation, the more interesting number is the four-week average migration time with agent assistance. That's the number that collapses the switching-cost moat. That's the number that matters."

### "G2 is behind a login. How are you detecting those signals?"

> "It is. DataDome for bot protection — fingerprints the browser, so a Python client with a session cookie won't pass even if you're logged in.
>
> Two real options. Playwright that passes fingerprinting — that's a one-day build. Or what I use for the demo today — pull reviews manually in the browser, seed them into the scoring engine. Same weight, same decay, different collection step.
>
> Honest answer: I hit the wall, diagnosed it, built the fallback. Every data source has a wall. Production version uses Playwright or a scraping proxy service. Day-one thing if I'm on the team."

### "How does this compare to Clay?"

> "Clay is enrichment — and Jordan Crawford himself just said publicly that Clay's UI/UX is amazing but it's built for humans, not agents. That's the structural ceiling. You bring a list, Clay fills the fields.
>
> SignalForce is timing. It generates the list and tells you why each company is on it right now. Complementary, not competitive. You'd feed SignalForce output into Clay for contact enrichment if you wanted both layers.
>
> But the bigger point — I'm not here to pitch a tool that competes with Clay. I'm here because the work demonstrates I think about GTM the way Conversion thinks about it. The real question is whether someone who builds this kind of system belongs on your team."

### "How does this compare to 6sense or Demandbase?"

> "Those tools give you a signal that an account might be interested. Then your team has to figure out everything else manually. Tapistro called it a signal dashboard, not a go-to-market system. I think that's right.
>
> The other structural problem is the black-box scoring. Account is in 'high intent' — why? You can't drill down. Sales stops trusting marketing. The alerts get ignored. I've watched that happen at two companies.
>
> SignalForce is the opposite. Every score is decomposed. Every weight is documented. Every signal has a recency decay you can audit. When the rep asks 'why is this account on my list,' there's a real answer."

### "Compiler — how is that different from Jasper or Copy.ai?"

> "Jasper takes a prompt and produces text. Output is a string. A human reads it, copies it into wherever they're publishing. Translation step at the end.
>
> The marops compiler takes a YAML config and a signal stack and produces a typed JSON object. Salesforce SOQL filters. Warehouse trait queries. Agent role assignments. QA rules. Plugs into your platform directly. No translation step.
>
> Jasper writes you a subject line. The compiler writes you a brief where the segment is `Account.Tier__c = 'Tier 2'`, the suppression rule is `IsChurned__c = TRUE`, and the agent assignment is optimization for variant selection.
>
> One is content. The other is config. That's the same distinction Neil drew in the launch post when he said agents are the operating layer of the platform, not a chat widget bolted on."

### "What would it take to configure this for our actual ICP?"

> "About an hour. ICP defined in YAML — target titles, disqualifiers, signal keywords, scoring thresholds, plus a company blocklist so your existing customers and named competitors never surface in the feed. I'd ask you five questions about your best current customers and translate the answers directly into config. Scanner picks it up on the next run. No redeployment.
>
> Honest answer about why I'm here — that's the work I want to be doing on your team. Configuring this against your real ICP shouldn't be a trial. It should be week one."

### "We use Heyreach, OutboundSync, Sumble, Gong — do you know these?"

> "Sumble I'd want to dig into in week one — haven't built against their API yet. Heyreach I've evaluated, but my LinkedIn scanner is read-only right now. OutboundSync for CRM hygiene is the same lane as the Salesforce QA rules in the brief I just showed you. Adjacent skill, different surface. Gong I've used as a customer, not as a builder.
>
> Day-one priority: get fluent in Heyreach and Sumble. Already built against Apollo, Hunter, Prospeo, ZeroBounce, Instantly, Salesforce, HubSpot, and the Anthropic stack. The muscle memory transfers."

### "Is Meridian Analytics a real company?"

> "Constructed. The signals are real-pattern though — G2 quote modeled from actual public HubSpot reviews, hiring signal modeled on three real Marketing Data Engineer postings from last week, conference registration logic uses the public Snowflake Summit attendee directory.
>
> Didn't want to use a real name on a public demo I might share. The live scan you just saw — those are real companies. The week-one engagement uses your real ICP."

### "Can RevOps do this?"

> "Jordan Crawford has the cleanest line on this — RevOps is CRM maintenance. GTM engineers take stuff from outside the walls and push them out into channels.
>
> Your JD describes the second function, not the first. RevOps owns Salesforce hygiene, lead routing, attribution downstream. GTM Engineering owns the systems that produce qualified pipeline upstream — signal detection, ICP modeling, intent, the data pipelines RevOps queries.
>
> RevOps doesn't typically build signal-decay engines. That's infrastructure work. Multi-source ingestion, recency weighting, freshness SLAs. Different skill stack. What I just showed you is the upstream side. The role you wrote the JD for."

### "You're too junior."

> "I get the instinct.
>
> What I'd push back on — the five-years profile was built in the 6Sense and Demandbase era. Lots of UX, specific clicks, well-understood playbooks. Senior hires from that era haven't shipped against `tool_use` schema enforcement. They haven't debugged DataDome fingerprinting. They haven't built the intuition for which parts of LLM output are deterministic and which aren't.
>
> The why-now engine in this brief was built in forty-eight hours after Reddit feedback. SignalForce is five-hundred-forty-seven tests passing. At Circuit AI — my second year out of college — I sourced eighty-two percent of opportunities and drove a hundred percent pipeline growth.
>
> Years are a proxy. The artifact is the credential."

### "Compensation?"

> "Wrong question. The right question is whether someone who builds this kind of system belongs on your team. If we get there, comp is a conversation. The careers page says competitive with big tech plus equity. I trust that as the starting point."

### "We're not hiring right now."

> "Understood. Is the Founding GTM Engineer role still open, or has it been filled?"

If filled:

> "Congrats. Anything else on the GTM or infrastructure side that's bottlenecked? Same skill set, different output."

If on hold:

> "Got it. Can I leave my info and check back in two weeks?"

### If the demo breaks

The live scan fails — pull up Sunday night's screenshot.

> "Live scan from last night, same verticals."

Don't apologize. Don't explain. Redirect.

If the scan hangs — Ctrl-C immediately. There's a known bug where the rate-limit handler can try to sleep fifty-six years. Don't troubleshoot in front of him. Fall straight to the screenshot.

Everything fails — walk through the JSON in VS Code manually. The story works without working software because the story is about you.

He declines.

> "Fair. Can I leave the GitHub link? Marops branch. And what's the best way to follow up in two weeks?"

Leave. Don't linger. Don't re-pitch.

---

## The Six Verbatim Lines

These are the six sentences worth memorizing for v10. Everything else can flex.

1. **Replace intuition and manual research with a system.**

   The through-line. Three years of work in seven words.

2. **For two decades, marketers have been stuck using software invented in 2006.**

   Ishaan's own line. Open Act Two with it.

3. **Agents on top of stale data are agents that hallucinate.**

   Neil's line. Use it to land the architecture argument.

4. **The incumbents' moat was never the product. It was the cost of leaving. And the moment that cost goes to zero, every conversation Conversion has with a Marketo shop becomes a different conversation.**

   The thesis extension. The part you've added beyond what either Neil or Ishaan has published. This is what makes the hire obvious.

5. **Three signals, six days of shelf life. She's already decided on the data stack — the question is which MAP runs on top of it.**

   The why-now and the conference hook fused into one breath. The sharpest single moment in the demo.

6. **I'm not asking for a trial. I'm asking for the next interview.**

   The ask. The whole thing builds toward this sentence. Don't soften it.

---

## What to Show — file by file

Each file maps to a JD bullet. Frame it that way when you open it.

- `github.com/sami2919/SignalForce` README. "Five-hundred-forty-seven tests passing, seventy-seven percent coverage overall and eighty-seven to ninety-three percent on the core scanners, MIT licensed. Open source because I wanted GTM engineers to actually use it. About five thousand in the community Slack."
- Live terminal scan. "JD bullet one. Design and build scalable systems for prospecting. Five scanners, YAML config, A/B/C grading. Data engineering applied to GTM."
- `icp_fit_scorer.py` + `intent_scorer.py`. "JD bullet on ICP modeling. Weighted scoring, calibrated weights, recency decay. The answer to 'lead score 72.'"
- `signal_aggregator.py`. "Enrichment waterfall pattern. Group by company, dedupe, confidence-score, grade."
- `hubspot-ceiling.yaml`. "JD bullet on segmentation logic. Config-driven. Same engine, different ICP. Blocklist for existing customers and named competitors."
- `demo/hubspot-ceiling.html`. "JD bullet on lifecycle nurture. Buying committee modeled. Urgency window. Conference trigger baked in. Account planning, operationalized."
- `briefer.py tool_use` block. "Schema enforcement at the API level. Same architectural decision as the reviewable artifact per run in Conversion Agents. Free-form JSON breaks twenty percent of the time at scale. With it, deterministic."
- `demo/veriforce.html`. "Same engine, different vertical. Renewal motion instead of buying window. Proves repointability."

---

## After the Meeting

Same day — email Ishaan. Attach `demo/hubspot-ceiling.html`. Include the GitHub link. One paragraph of week-one proposal. Subject line: `From this morning — week-one proposal + work sample`.

Body keeps the candidate framing. Not pitching a tool. Pitching the work. Reference one specific moment from the conversation — the architecture argument, the agent launch, the migration-paralysis insight, whichever landed hardest. Don't recap. One line. Move forward.

Within forty-eight hours if yes — get the vertical and ICP from him. Configure the scanner. Run for twenty-four hours. Send the sample Wednesday. Full B-grade-or-higher list by Monday.

Within forty-eight hours if no — send the Loom via LinkedIn DM. One sentence: If the timing shifts, I'm here. No re-pitch.

---

## The Meta-Point

You are not a candidate asking for a chance. You are a builder revealing eighteen months of work to the person who wrote the job description for it.

The walk-in is the reveal. The work is the credential. The story is the spine. The architecture argument is what makes the hire obvious — because that's what got Ishaan hired in the first place, and showing you can do the same thing is how you prove you belong on the team.

Three years. Three companies. Three titles. One job.

Replace intuition and manual research with a system.

You built one. You're walking in to show him.

---

**Version:** 10.0 — Adds the architecture critique as the spine (Act Two), drawing directly from Ishaan's own published thinking. Quotes Neil's launch post ("software invented in 2006," "agents on top of stale data hallucinate") and Ishaan's migration-paralysis post. Extends the thesis one step further than either has published — the switching-cost-collapse argument. Acknowledges the May 19 Conversion Agents launch throughout. New objection handler: "What do you think of Conversion Agents." Compiler frame now explicitly mirrors the reviewable-artifact-per-run architecture in Conversion Agents. Six verbatim lines instead of four. All v9 strategic content preserved — honest-seed framing, 547 tests, blocklist in config answer, pre-flight items, render-bug fixes. Treats Conversion's published metrics as vendor pilot numbers, not independent truth — credibility move for a technical reader.
