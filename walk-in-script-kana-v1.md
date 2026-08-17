# Kana Walk-In Script v1 — The Reveal, Customer Zero

**Audience:** the founders or whoever owns GTM hiring at Kana.  
**Date:** use the actual day you walk in.  
**Location:** fill in once confirmed.  
**Arrival window:** 9:30 to 10:00 AM PT.  
**Goal:** the next interview.

---

## What changes from the Conversion walk-in

The Conversion walk-in was built around one central critique: legacy marketing automation platforms were architecturally broken, and SignalForce could detect the exact buying windows where that breakage became visible.

Kana is a different conversation.

The role is not asking you to prove that old MAPs are obsolete. The JD already assumes that. The job is asking for the builder who can turn a messy GTM stack into an AI-first operating system and use Kana itself as **Customer Zero**.

So this script keeps what worked in the Conversion walk-in:

- the candidate-not-vendor framing
- the slow reveal pace
- the live proof moment
- the architecture argument
- the direct ask for the next interview

What changes is the spine.

At Kana, the spine is:

1. GTM should be treated like software, not like a coordination function.
2. The role exists because “growth,” “revops,” “sales ops,” and “marketing ops” are all too narrow for what the company actually needs.
3. Kana’s own product thesis is augmentation, not replacement, so the strongest possible proof is a **Customer Zero engine** that keeps the stack intact and removes the glue work.

You are not walking in with “I rebuilt Kana.”

You are walking in with:

> “I built the internal operating system this role is supposed to own, and I can show you exactly how Kana should use its own platform inside it.”

---

## Mindset

You are not asking for a shot.

You are showing them the system they described before they hired the person to build it.

Every once in a while, a role shows up that doesn’t belong to one function anymore.

Not pure growth.
Not pure revops.
Not pure marketing ops.
Not pure engineering.

It belongs to the person who can wire all of it together, instrument it, and iterate on it fast enough that the company compounds before the org chart catches up.

That is the role Kana is hiring for.

The tone is deliberate. Slightly slower than feels natural. No rush. No over-explaining.

You are not pitching a tool.

You are unveiling a system.

---

## Carry-ons

Laptop, charged 100%, tabs in this order:

1. `github.com/sami2919/SignalForce` README on the `kana-ai-first` branch
2. Terminal ready for `python3.11 -m scripts.kana_demo --sample`
3. `examples/kana-ai-first/config.yaml`
4. `out/kana-customer-zero.html` rendered locally in Chrome
5. `out/kana-agent-brief.html` rendered locally in Chrome
6. One real or sample company row you can talk through from the queue output
7. The Kana job description, cached

VS Code:

- `scripts/kana_demo.py`
- `scripts/icp_fit_scorer.py`
- `scripts/intent_scorer.py`

Physical:

- One printed queue artifact: `kana-customer-zero.html`
- One printed supporting brief: `kana-agent-brief.html`
- Resume in the bag. Only if asked.
- Business card with GitHub QR and `kana-ai-first` written on the back
- Phone with the job description screenshot and a screenshot of the demo output cached offline

---

## Pre-flight, Sunday night

The rule is the same as Conversion: do not depend on live systems in the room.

1. Run `python3.11 -m scripts.kana_demo --sample`
2. Confirm both files render clean:
   - `out/kana-customer-zero.html`
   - `out/kana-agent-brief.html`
3. Screenshot the queue output in the terminal
4. Print both artifacts
5. Re-read the Kana job description
6. Rehearse the short form out loud under ninety seconds
7. Rehearse the long form once with the laptop open and once with it closed

Monday morning:

1. Re-run `python3.11 -m scripts.kana_demo --sample`
2. Confirm tabs are in order
3. Charge everything
4. Arrive in the 9:30 to 10:00 window
5. If no one relevant is available, get a specific return time

---

## Step 1 — Reception

Twenty-five seconds. Calm pace. Eye contact.

> "Hi — sorry to drop in cold. My name’s Sami. I’m a GTM engineer in SF and I’m here because I read your GTM Engineer role. It’s one of the clearest descriptions I’ve seen of how AI-first go-to-market should actually work. I spent the last nine months building the open-source version of the systems that role describes. I have one concrete thing to show — takes ninety seconds. Your role says you want someone who treats the funnel like a high-performance engine. That’s why I walked in instead of sending a Loom. Is whoever owns GTM hiring available this morning?"

If they ask whether you applied:

> "Applied already. The role reads like you care about builders, not résumé theater. Figured a working system lands better than another application in a queue."

Hand them the business card. Not the resume. Not the printed artifact.

Twenty-minute hard stop. After that, leave the card and one printed artifact. Follow up later that day.

---

## Step 2A — The Short Form

Ninety seconds, if someone is between meetings.

Three movements. Roughly twenty-five, thirty, thirty-five.

### Movement One — The Through-Line

Don’t open the laptop yet.

> "For the last three years I’ve been doing the same job under different titles.
>
> At AWS it looked like production AI systems for enterprise buyers. At Circuit it looked like product engineering plus GTM systems. Before that, with my own company, it looked like building the product and the distribution engine at the same time.
>
> Different industries. Same work.
>
> Replace intuition and manual research with a system."

Pause.

> "Your Kana role is the cleanest naming of that job I’ve seen. Not a growth marketer. Not a sales ops lead. A GTM engineer. Someone who owns sourcing, routing, HubSpot plumbing, experimentation, and AI-native execution as one system. Ninety seconds and I’ll show you what I built toward that."

Open the laptop.

### Movement Two — The Live Reveal

Run:

```bash
python3.11 -m scripts.kana_demo --sample
```

As it prints:

> "This is the Kana-shaped Customer Zero engine. Ranked accounts, routes, message angles, experiment tags, and HubSpot write-back. Not just who to work. How to work them. What channel. What hypothesis. What gets written back into the system of record."

When the output appears:

> "This is the operating queue. The point is not ‘here are leads.’ The point is ‘here is the AI-first machine that maximizes at-bats without increasing manual ops overhead.’"

### Movement Three — The Artifact and the Ask

Switch to `out/kana-customer-zero.html`. Then briefly to `out/kana-agent-brief.html`.

> "This first artifact is the operating surface. The queue sales and growth actually use.
>
> This second artifact is smaller on purpose. It’s not me pretending to rebuild Kana. It’s me showing how Kana should use its own agents internally as Customer Zero."

Pause.

> "I’d rather show you week one than describe it abstractly. If this is the kind of system you want this role to own, I’m not asking for a trial. I’m asking for the next interview. When can we make that happen?"

Stop. Eye contact. No filler.

---

## Step 2B — The Long Form

If they invite you in. Fifteen minutes if you stay disciplined.

The spine here is not migration pain. It is **AI-first GTM as an operating system**.

### Before You Open the Laptop

Start with discovery.

> "Before I show you anything — can I ask what the current GTM stack actually looks like day to day? What’s working, what’s manual, and where do you feel the drag most? Outbound, inbound, routing, content, paid, CRM — where does the engine slow down?"

Listen.

That answer tells you where to lean:

- if they talk about outbound, emphasize the queue and routing
- if they talk about content or SEO, emphasize AEO and content experiments
- if they talk about process drag, emphasize HubSpot write-back and automation

Then:

> "Perfect. The system I built is really a response to exactly that problem."

### Act One — The Three Years

No laptop yet.

> "Three years ago I was working on production AI systems at AWS. Enterprise buyers, messy data, real deployment constraints.
>
> Then I went to Circuit AI and ended up doing what I’d now call GTM engineering before I had the name for it: building product, sourcing opportunities, scoring accounts, automating workflows, and tightening the feedback loop between the product and the pipeline.
>
> Before that I built my own company and had no separation between product, sales, ops, and growth because there wasn’t a team big enough to separate them.
>
> That’s where the through-line became obvious.
>
> The real bottleneck in GTM is not effort. It’s that too many decisions still happen by intuition, spreadsheets, stale routing logic, and manual glue work.
>
> So the job becomes: replace intuition and manual research with a system."

Pause.

> "Your role is one of the first times I’ve seen that written down clearly."

### Act Two — The Kana Argument

This is the architecture critique, but for Kana.

> "The reason I took this role description seriously is that it doesn’t confuse tool usage with system ownership.
>
> Most companies think they need a better growth marketer, or a better RevOps person, or someone who knows the latest outbound tools.
>
> But that’s not actually the problem.
>
> The problem is fragmentation.
>
> Clay knows one thing. HubSpot knows another. Sales Navigator is upstream. Instantly sits somewhere else. LinkedIn outreach sits in another surface. SEO and content decisions happen in another loop. Paid experiments happen in another loop. Then someone manually translates all of it into action.
>
> That’s not a GTM engine. That’s a relay race.
>
> What your role describes is the person who turns that relay race into a system.
>
> And what makes Kana interesting is that your product thesis matches that exactly. Not rip-and-replace everything. Not ‘AI replaces marketers.’ Augmented intelligence. Agents that plug into the stack and remove the glue work.
>
> That’s the part I agree with most strongly.
>
> The strongest proof that thesis is real is not a landing page. It’s Customer Zero. Use Kana internally first. Let the internal engine become the proof."

Pause.

> "That’s the system I built for this walk-in."

### Act Three — Why This Role Exists

> "The role exists because the old categories are too small.
>
> Growth alone is too channel-specific.
>
> RevOps alone is too CRM-specific.
>
> Sales ops alone is too downstream.
>
> Traditional marketing ops is too execution-oriented.
>
> The company actually needs one person who can own all of the handoffs: sourcing, enrichment, routing, experimentation, channel orchestration, content feedback loops, and CRM integrity.
>
> That’s why the title is right. GTM engineer."

Pause.

> "Let me show you the system."

Now open the laptop.

### Act Four — The Live Queue

Run:

```bash
python3.11 -m scripts.kana_demo --sample
```

Talk while it runs:

> "This is the Customer Zero operating queue. It takes signal inputs, prioritizes accounts, assigns routes, defines message angles, attaches experiment tags, and makes HubSpot the system of record instead of the graveyard at the end of the workflow."

When it prints:

> "This is the ranked queue. Grade, route, experiment, next action.
>
> The important move here is that the output is operational. Not a dashboard someone glances at. Not a CSV. A working queue with a path attached."

Point at one row.

> "This company gets Clay research plus Instantly plus Valley because the signal stack implies an ops bottleneck and active leadership behavior.
>
> This one gets a different route because the problem is more content and SEO pressure.
>
> That distinction is the whole point. Same engine, different motion based on the signal."

### Act Five — The Operator Surface

Open `out/kana-customer-zero.html`.

> "This is the piece I’d want in front of sales and growth every morning.
>
> Company. Why now. Recommended titles. Message angle. Experiment tag. HubSpot sync behavior. Next action.
>
> Not a list of possibilities. A list of moves."

Pause.

> "The thing I care about here is that the funnel becomes inspectable. You can actually ask why a company is here, why this route was chosen, why this experiment exists, and what happens next."

### Act Six — Customer Zero

Open `out/kana-agent-brief.html`.

> "This is the smaller supporting artifact.
>
> I made it smaller on purpose because I don’t think the right proof for Kana is ‘I rebuilt your platform.’
>
> The right proof is: I understand how Kana should use its own product internally.
>
> Audience agent. Experiment agent. HubSpot sync agent. AEO agent.
>
> The structure mirrors the role description directly: outbound, inbound, CRM plumbing, content discoverability, and experiment routing living in one operating model."

Pause.

> "This is how Customer Zero should look. The product and the GTM engine reinforcing each other."

### Act Seven — The Stack Argument

Switch briefly to `examples/kana-ai-first/config.yaml` and then to `scripts/kana_demo.py`.

> "The other reason I wanted to show this in code is that the system is configurable rather than theatrical.
>
> Different ICP. Different signal keywords. Different titles. Different thresholds. Same engine.
>
> That matters because one founder’s instinct about the ideal account is not enough. The system has to be repointed as the motion evolves.
>
> Same thing with channels. Email, LinkedIn, content, paid — not separate functions. Just different output routes from the same decision layer."

### Act Eight — Why I Fit It

Laptop still open, but this is back to you.

> "The reason I fit this job isn’t that I’ve used every tool in your stack.
>
> It’s that I’ve spent the last few years doing the deeper job beneath the tools:
>
> building systems that connect messy inputs to useful actions,
> making AI outputs safe enough to use,
> instrumenting the feedback loop,
> and shipping fast enough that the model improves while the market is still moving."

Pause.

> "Tools change. That layer doesn’t."

### Act Nine — The Ask

Close the laptop. Slow down.

> "Here’s what I want.
>
> Not a consulting engagement. Not a product sale. Not a maybe-later conversation.
>
> I want the next interview.
>
> The role says your goal is to maximize at-bats for the sales team. The system I just showed you is built around exactly that.
>
> If you want, give me the real vertical you care about most right now. Give me the context on your best current customers. Week one, I’d repoint the engine to your actual motion, tighten the routes, and put a real queue in front of the team.
>
> You won’t need to guess how I work. You’ve already seen it."

Pause.

> "I’m not asking for a chance to prove I can do the job. I’m asking for the next interview because I already built the shape of it."

Stop there.

---

## Objection Handlers

### "How is this different from just using Clay well?"

> "Clay is a component. A very good one. It helps research and enrich.
>
> The problem is that most teams stop there. They enrich a list, but they still haven’t solved routing, prioritization, CRM integrity, experiment tracking, or how outbound and inbound learn from each other.
>
> Clay is not the operating system. It’s one part of the operating system."

### "Why not just hire a strong growth marketer?"

> "Because the bottleneck you’re describing in the JD is not creative taste. It’s systems design.
>
> A strong growth marketer can run campaigns. A GTM engineer builds the machine that decides what campaigns should run, what data they use, how they write back, and how the learnings compound."

### "What do you mean by Customer Zero?"

> "I mean Kana should be the first serious user of its own thesis.
>
> If the platform says AI agents can amplify marketers without replacing them, then the internal GTM engine should be the cleanest proof of that claim.
>
> Not abstractly. Operationally."

### "Is this live or staged?"

> "The structure is real and the sample path is deliberate. I don’t like walking into a room depending on external APIs behaving perfectly.
>
> The point of the demo is not fake liveness. The point is whether the operating system itself is coherent."

### "You haven’t used every tool in our stack."

> "Correct. But I’ve built against enough adjacent systems that the real question isn’t whether I know every button in each tool. It’s whether I understand the architecture underneath the motion. That part transfers."

### "Why should we believe you can do this at our pace?"

> "Because the repo is the artifact. The branch is the proof. The system exists already. I’m not describing how I think. I’m showing how I build."

### "You’re junior."

> "Years are a proxy. The artifact is the credential.
>
> The work I’m showing you is the work your JD describes. If you want, judge it at the level of the system instead of the level of the résumé timeline."

---

## The Six Verbatim Lines

These are the lines worth memorizing exactly.

1. **Replace intuition and manual research with a system.**
2. **The old GTM categories are too small for the job this role actually owns.**
3. **Clay is a component. It is not the operating system.**
4. **The strongest proof of Kana’s thesis is Customer Zero.**
5. **The point is not “here are leads.” The point is “here is the operating queue.”**
6. **I’m not asking for a trial. I’m asking for the next interview.**

---

## What to show — file by file

- README on `kana-ai-first`: the branch story and the Customer Zero framing
- `python3.11 -m scripts.kana_demo --sample`: the live reveal
- `out/kana-customer-zero.html`: the operator surface
- `out/kana-agent-brief.html`: the Kana-internal product empathy proof
- `examples/kana-ai-first/config.yaml`: repointability and ICP logic
- `scripts/kana_demo.py`: the queue generation and routing layer
- `scripts/icp_fit_scorer.py` + `scripts/intent_scorer.py`: documented scoring logic instead of vibes

---

## After the Meeting

Same day:

- send the GitHub link
- attach the queue artifact if you got email
- reference one specific moment from the conversation
- keep it short

Suggested subject line:

`From this morning — Customer Zero GTM engine`

Body shape:

1. one line referencing the part of the conversation that landed
2. one line with the repo link
3. one line restating that you’d like the next interview

No recap. No re-pitch.

---

## The Meta-Point

The walk-in is not about whether Kana should buy something.

It is about whether the company sees that you are already doing the work they wrote the role for.

Different titles. Same job.

Replace intuition and manual research with a system.

You built one.

You’re walking in to show them.
