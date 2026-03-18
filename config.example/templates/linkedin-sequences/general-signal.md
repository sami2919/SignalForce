# General Signal LinkedIn Sequence

## Signal Context

Fallback template for signals that don't map to a more specific LinkedIn sequence (e.g., HuggingFace model uploads, funding events, or generic RL activity). The connection hook must still be specific — use whatever signal detail is available (model name, funding round, product area) to avoid appearing generic. Never send a blank-slate "I'd like to connect" note.

## Placeholders

- `{{contact_first_name}}` — Recipient's first name
- `{{company_name}}` — Company name
- `{{signal_reference}}` — The specific signal detail (model name, funding announcement, etc.)
- `{{rl_focus}}` — What the company appears to be building with RL (inferred from signal)

---

## Connection Request Note (≤300 chars)

### Variant A: Signal Reference

Came across {{signal_reference}} from {{company_name}} — the {{rl_focus}} direction looks like serious work. Building infrastructure in the same space and would value connecting with someone leading this.

### Variant B: Mutual Interest

Following {{company_name}}'s work on {{rl_focus}} — it's one of the more thoughtful approaches in this space right now. Would be glad to connect with someone working at this level.

---

## Follow-Up Message (Day 2-3 after connection accepted)

{{contact_first_name}}, appreciate the connect. Teams pushing {{rl_focus}} into production tend to hit similar infrastructure inflection points around environment management and experiment reproducibility. We've been documenting how different teams have handled that transition — happy to share what's relevant if the timing is right for {{company_name}}.

---

## Second Follow-Up (Day 7, only if no response)

{{contact_first_name}}, dropping a resource in case it's useful: a technical overview of RL environment infrastructure patterns at scale. No rush — reach out whenever it makes sense.
