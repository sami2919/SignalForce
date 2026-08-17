# Neil Loom Script - SignalForce x Conversion

**Audience:** Neil at Conversion  
**Format:** Loom screen share with webcam bubble  
**Target length:** 3:00 to 3:30  
**Goal:** Earn a 30-minute conversation by showing the artifact, not re-sending the resume.

This is the Loom version of the unused walk-in script. It keeps the core thesis:

> Replace intuition and manual research with a system.

But the posture changes. This is not a lobby reveal for Ishaan. This is a concise founder-level note to Neil:

- You understand the category shift Conversion is betting on.
- You built a small proof around that shift.
- You are asking for one real problem to prove the work against.

---

## Core Thesis

The real shift in marketing automation is not "AI writes better copy."

It is that the campaign brief, the audience segment, QA rules, agent assignments, and optimization loop become structured objects an agent can operate on.

Most AI GTM tools make brief-writing faster. SignalForce tries to remove brief-writing as a human translation step.

The output is closer to platform config than a document.

---

## Recording Setup

Use Loom with webcam bubble in the lower right. Close Slack, Messages, email, and anything with notifications.

Open tabs in this order:

1. GitHub or local README: `github.com/sami2919/SignalForce` on the relevant branch
2. `examples/marops/veriforce.yaml`
3. `scripts/marops/briefer.py`
4. `demo/veriforce.html`
5. Optional backup: `out/veriforce-ceo-brief.md`

Optional terminal, already open but do not run live unless tested:

```bash
python3.11 -m scripts.marops.cli veriforce
```

Safer path: show the command in the README or terminal, then show the already generated artifact.

---

## Do Not Say

Do not say:

- "I have not heard back."
- "As a last resort."
- "I know this is weird."
- "I just wanted a chance."
- "This is basically your product."
- "I rebuilt Conversion."

Say:

- "The resume is less useful than the artifact."
- "I built a system."
- "The output is structured enough to operate on."
- "Point me at one real campaign problem."

---

## Screen Flow

### 0:00-0:25 - Webcam Hook

Start on webcam, or a blank browser tab with webcam prominent.

Say:

> Hey Neil - Sami here. I stopped by Conversion and sent my resume over, but honestly, the resume is the least interesting artifact.
>
> I recorded this because I think the real shift in marketing automation is not "AI writes better copy."
>
> It is that the campaign brief, the segment, the QA rules, and the optimization loop become structured objects an agent can operate on.
>
> So I wanted to show you the system I built, not the resume.

Switch to the repo.

### 0:25-0:55 - SignalForce Repo

Show the README. If possible, start near the `marops` section and the "30-second version."

Say:

> This is SignalForce. It started as a signal-based prospecting engine: scan public signals, find companies entering a buying window, score them, and turn that into action.
>
> For Conversion, I repointed the same engine at MarOps. Instead of outputting a ranked prospect list, it outputs a lifecycle campaign brief shaped around how a marketing automation platform actually works.
>
> The important part is that the output is not just prose. It has segment logic, sequence steps, agent assignments, QA rules, optimization triggers, and pipeline projection.

If the README table is visible, point to the rows for segmentation, agent orchestration, multi-touch sequence, optimization triggers, and pipeline projection.

### 0:55-1:25 - YAML Input

Switch to:

```text
examples/marops/veriforce.yaml
```

Say:

> This is the input. A YAML config for Veriforce: the company, the lifecycle motion, the objective, the signals, and the constraints.
>
> The operator changes config, not code. That matters because GTM teams should not need an engineer every time the campaign changes.
>
> The system takes this structured intent and generates the campaign artifact from it.

Point to the company, lifecycle motion, signals, and constraints. Do not explain every field.

### 1:25-2:05 - The Compiler

Switch to:

```text
scripts/marops/briefer.py
```

Show the `tool_use` schema or the strict output model area.

Say:

> This is the core. Claude is not being asked to "write a nice brief." It is forced through a `tool_use` schema.
>
> That means the model has to return the shape the system expects. Then Pydantic validates it again before anything renders.
>
> The distinction I care about is this: most AI GTM tools make brief-writing faster. This tries to remove brief-writing as a human translation step.
>
> The output is closer to platform config than a document.

If you have time, add:

> Same production instinct everywhere LLMs touch business data: schema, fallback, validation, determinism.

### 2:05-2:55 - Generated Veriforce Brief

Switch to:

```text
demo/veriforce.html
```

Scroll through the artifact while speaking.

Say:

> Here is the generated Veriforce brief.
>
> Segment: lapsed Tier-2 suppliers with contract pressure and churn risk.
>
> Sequence: email, in-app, AE task, optimized follow-up, LinkedIn.
>
> Agents are separated by role: execution owns sends, QA owns suppression and safety checks, optimization owns variant selection.
>
> And the campaign includes triggers: if someone renews, suppress the rest; if churn risk crosses a threshold, escalate to a human; if a variant wins, reallocate traffic.
>
> That is the operating loop: signal, segment, action, QA, optimization.

Pause briefly on the optimization trigger section. Let the artifact do some work.

### 2:55-3:25 - Webcam Close

Switch back to webcam.

Say:

> The reason I am sending this to you is that I think this is the direction the category goes.
>
> Not agents as chat windows. Agents as operators over structured campaign context.
>
> I would love 30 minutes. If useful, point me at one real vertical, lifecycle motion, or campaign problem, and I will come back with a working version by Friday.
>
> Repo is linked below. Thanks for watching.

Stop recording. Do not add another sentence.

---

## Shorter 2-Minute Backup

Use this if the full version keeps running long.

> Hey Neil - Sami here. I stopped by Conversion and sent my resume over, but the resume is the least useful artifact.
>
> I built SignalForce as a signal-based GTM engine: find companies entering a buying window, score the signals, and turn that into action.
>
> For Conversion, I repointed the same engine at MarOps. The input is a YAML config. The output is a lifecycle campaign brief with segment logic, sequence steps, agent assignments, QA rules, optimization triggers, and pipeline projection.
>
> The important distinction: Claude is not just writing prose. It is forced through a `tool_use` schema, validated again with Pydantic, and then rendered. So the output is closer to platform config than a document.
>
> Most AI GTM tools make brief-writing faster. This tries to remove brief-writing as a human translation step.
>
> Here is the Veriforce example: lapsed Tier-2 suppliers, contract pressure, churn risk, a five-touch sequence, separated execution/QA/optimization agents, and triggers that suppress, escalate, or reallocate based on behavior.
>
> I think this is where the category goes: not agents as chat windows, agents as operators over structured campaign context.
>
> I would love 30 minutes. Point me at one real vertical or campaign problem, and I will come back with a working version by Friday.

---

## Message To Send With Loom

Subject:

```text
Built a small proof around Conversion's agent thesis
```

Body:

```text
Hey Neil - Sami here. I stopped by Conversion and sent my resume over, but I realized the resume is the least useful artifact.

I recorded a 3-min Loom showing the system I built: SignalForce repointed at MarOps, generating schema-enforced lifecycle campaign briefs from config rather than hand-written docs.

The core idea: most AI GTM tools make brief-writing faster. This tries to remove brief-writing as a human translation step.

Loom: [link]
Repo: https://github.com/sami2919/SignalForce

If useful, point me at one real vertical or campaign problem and I will come back with a working version by Friday.
```

---

## Three Lines To Memorize

1. **"The resume is the least interesting artifact."**

Use this early. It reframes the follow-up from job-seeking to proof.

2. **"Most AI GTM tools make brief-writing faster. This tries to remove brief-writing as a human translation step."**

This is the sharpest product distinction.

3. **"Not agents as chat windows. Agents as operators over structured campaign context."**

This is the founder-level category thesis.

---

## Recording Discipline

- Hard cap: 3:30.
- One full take, then one retake only if the first has a real issue.
- Speak slower than feels natural.
- Do not narrate your mouse movements.
- Do not explain every field.
- Keep the repo and artifact visible longer than your face.
- End immediately after the ask.

The Loom works if Neil understands three things:

1. You understand the architecture argument.
2. You built a real artifact against that argument.
3. You are asking for a concrete next problem, not vague consideration.
