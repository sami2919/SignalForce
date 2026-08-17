# Kana Walk-In Script — Customer Zero GTM Engineer

**Audience:** founders or whoever owns GTM hiring at Kana  
**Goal:** get into the formal interview loop for the GTM Engineer (AI-First) role

## Core frame

You are not pitching SignalForce as a product.

You are demonstrating that you already built the internal demand engine Kana says this role should own:

1. account discovery
2. routing and personalization
3. HubSpot write-back
4. experiment tagging
5. internal agent usage as Customer Zero

## Tabs to have open

- repo README on `kana-ai-first`
- terminal ready with `python -m scripts.kana_demo --sample`
- `out/kana-customer-zero.html`
- `out/kana-agent-brief.html`

## Reception opener

“Hey — sorry to drop in cold. My name’s Sami, I’m a GTM engineer based in SF. I read your GTM Engineer role and built a working version of the system it describes. It’s open source, and I have one concrete thing to show. Takes 90 seconds. Is the hiring manager or one of the founders around this morning?”

## 90-second sequence

### Beat 1 — Frame

“Your JD isn’t looking for a coordinator. It’s looking for someone who treats the funnel like code: sourcing, routing, HubSpot plumbing, experimentation, and AI-native execution as one system. That’s the work I built.”

### Beat 2 — Live proof

Run:

```bash
python -m scripts.kana_demo --sample
```

Say:

“This is the Customer Zero operating queue. Not just a lead list — company, why-now signal stack, route, message angle, experiment tag, and what gets written back to HubSpot.”

### Beat 3 — Artifact

Open `out/kana-customer-zero.html`.

Say:

“This is the actual operating surface. If I were in the role, this is what sales and growth would use to decide who gets worked now and how.”

### Beat 4 — Product empathy

Open `out/kana-agent-brief.html`.

Say:

“This second artifact is smaller on purpose. It’s not me pretending to rebuild Kana. It’s me showing how Kana should use its own agents internally as Customer Zero.”

### Beat 5 — Ask

“That’s the work sample. I want the interview loop. I’d rather show you week one than talk abstractly about fit.”
