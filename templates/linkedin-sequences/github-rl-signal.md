# GitHub RL Signal LinkedIn Sequence

## Signal Context

Active RL GitHub repos surface engineers who are building right now — not planning to. LinkedIn works here because the repo gives you a concrete, non-generic conversation hook. Engineers respond to peers who have actually looked at their code. Keep the connection request about their work, never about your product.

## Placeholders

- `{{contact_first_name}}` — Recipient's first name
- `{{company_name}}` — Company name
- `{{signal_reference}}` — GitHub repo name (e.g., `acme/rl-trading-env`)
- `{{repo_focus}}` — One-phrase description of what the repo does
- `{{rl_method}}` — RL method used in the repo (e.g., PPO, SAC, GRPO)
- `{{technical_detail}}` — Specific implementation detail showing you looked

---

## Connection Request Note (≤300 chars)

### Variant A: Signal Reference

Saw {{signal_reference}} — the {{technical_detail}} caught my attention. We're both working on {{rl_method}} infrastructure problems. Would value connecting with someone building at this level.

### Variant B: Mutual Interest

Working on RL environment infrastructure and came across your {{repo_focus}} work. Always interested in connecting with engineers pushing {{rl_method}} in production — rare to see it done this carefully.

---

## Follow-Up Message (Day 2-3 after connection accepted)

{{contact_first_name}}, thanks for connecting. We recently published a breakdown of how teams maintaining custom Gymnasium environments handle the drift problem at scale — covers version pinning strategies and environment state serialization. Happy to share if useful for where {{company_name}}'s {{repo_focus}} work is headed.

---

## Second Follow-Up (Day 7, only if no response)

{{contact_first_name}}, one more resource that may be relevant: a benchmark comparing in-house vs. managed environment approaches across experiment throughput and maintenance hours. No pressure — reach out whenever the timing makes sense.
