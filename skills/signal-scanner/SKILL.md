---
name: signal-scanner
description: Use when looking for companies actively investing in reinforcement learning, when needing to find new target accounts, or when running periodic signal detection scans
---

# Signal Scanner

## Signal Sources

| Scanner | Script | Lookback |
|---------|--------|----------|
| GitHub RL repos | `scripts.github_rl_scanner` | 7 days |
| ArXiv papers | `scripts.arxiv_monitor` | 7 days |
| HuggingFace models | `scripts.hf_model_monitor` | 7 days |
| Job postings | `scripts.job_posting_scanner` | 7 days |
| Funding rounds | `scripts.funding_tracker` | 30 days |

## Steps

**1. Validate API keys**

```bash
python3 -c "from scripts.config import Config; Config.load()"
```

Fix any missing keys before proceeding. GITHUB_TOKEN is required; others are optional but improve coverage.

**2. Run scanners**

```bash
python3 -m scripts.github_rl_scanner --lookback-days 7 --output /tmp/github_signals.json
python3 -m scripts.arxiv_monitor --lookback-days 7 --output /tmp/arxiv_signals.json
python3 -m scripts.hf_model_monitor --lookback-days 7 --output /tmp/hf_signals.json
python3 -m scripts.job_posting_scanner --lookback-days 7 --output /tmp/job_signals.json
python3 -m scripts.funding_tracker --lookback-days 30 --output /tmp/funding_signals.json
```

**3. Stack signals**

```bash
python3 -m scripts.signal_stacker \
  --inputs /tmp/github_signals.json /tmp/arxiv_signals.json /tmp/hf_signals.json \
           /tmp/job_signals.json /tmp/funding_signals.json \
  --output /tmp/stacked.json
```

**4. Present results**

Show a summary table:

```
Company | ICP Tier | RL Maturity | Signals (sources) | Composite Score | Grade
```

Sort by composite score descending. Group by grade (A → B → C → skip D).

**5. Recommend next action**

- Grade A accounts: "Run `prospect-researcher` on these accounts before outreach."
- Grade B accounts: "Ready for `contact-finder` + `email-writer`."
- Grade C accounts: "Log for 30-day nurture revisit."
- Grade D: skip, log with reason.
