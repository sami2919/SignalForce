# Analytics Feature Handoff

## Summary

The new analytics feature turns SignalForce's feedback loop into an inspectable performance system. It captures richer metadata about detected signals, outbound touches, and downstream outcomes, then produces local reports that show which sources, ICP grades, templates, and experiments are converting.

This is intentionally lightweight: it runs on the existing SQLite-backed tracker and does not require HubSpot, Instantly, n8n, Slack, or Google Sheets to prove value. External systems can still feed the same tables later.

## What It Does

The feature adds four main capabilities:

| Capability | What It Answers | Where It Lives |
|---|---|---|
| Funnel metrics | How many signals became outreach, replies, meetings, and deals? | `scripts.analytics.get_funnel_metrics` |
| Conversion breakdowns | Which signal types, ICP grades, templates, variants, or experiments are performing best? | `scripts.analytics.get_breakdown` |
| Stale signal detection | Which qualified signals have not received outreach within the SLA window? | `scripts.analytics.get_stale_signals` |
| Optimization recommendations | What should be doubled down, paused, rewritten, or deprioritized? | `scripts.analytics.get_recommendations` |

Reports are generated through:

```bash
python -m scripts.analytics_report --last-days 30 --format markdown
python -m scripts.analytics_report --last-days 7 --format json --out out/analytics.json
```

## Why It Is Beneficial

Before this feature, SignalForce could find signals, generate outreach, and log outcomes, but the learning loop was thin. The new analytics layer makes the system measurable and easier to improve.

Key benefits:

- **Closes the GTM learning loop**: teams can see which buying signals actually turn into replies, meetings, and deals instead of relying on intuition.
- **Improves prioritization**: breakdowns by `signal_type`, `icp_grade`, and `scanner_name` show where to spend limited research and outbound capacity.
- **Supports experiment discipline**: template variants, subject variants, CTA variants, and experiment tags can be tracked against real outcomes.
- **Protects speed-to-lead**: stale signal detection surfaces accounts that were discovered but never worked, which prevents high-intent opportunities from aging out.
- **Reduces wasted sends**: deterministic recommendations flag weak templates and low-yield ICP grades before more volume is spent.
- **Keeps V1 operationally simple**: the first version works locally, so analytics can be used during demos, pilots, and development without external integration setup.

## Data Model Changes

The existing feedback-loop tables were extended with analytics metadata.

`tracked_signals` now supports:

- `icp_grade`
- `composite_score`
- `scanner_name`

`outreach_events` now supports:

- `template_variant`
- `subject_variant`
- `cta_variant`
- `experiment_tag`
- `external_id`
- `detected_to_sent_hours`

`outcome_events` now supports:

- `external_id`

The valid outcome set now includes deliverability and engagement events such as `delivered`, `opened`, `clicked`, `bounced`, `negative_reply`, `no_response`, and `unsubscribed`, in addition to reply, meeting, and deal outcomes.

Existing local databases are handled by a small additive SQLite migration in `scripts.db.init_db()`. The migration only adds nullable columns, so old callers and existing rows remain compatible.

## Implementation Map

| File | Role |
|---|---|
| `scripts/db.py` | SQLAlchemy schema, valid outcome types, and additive SQLite migration |
| `scripts/outcome_tracker.py` | Write helpers for signals, outreach, outcomes, and legacy conversion queries |
| `scripts/analytics.py` | New analytics query layer and recommendation logic |
| `scripts/analytics_report.py` | CLI report builder with Markdown and JSON output |
| `docs/results-framework.md` | User-facing reporting cadence and command examples |
| `tests/unit/test_analytics.py` | Coverage for funnel metrics, breakdowns, stale signals, recommendations, and rendering |
| `tests/unit/test_db.py` | Coverage for analytics columns on fresh databases |
| `tests/unit/test_outcome_tracker.py` | Coverage for metadata persistence and new outcome types |

## How To Use It

1. Initialize or reuse the local feedback-loop database:

```python
from scripts.db import create_db_engine, init_db

engine = create_db_engine()
init_db(engine)
```

2. Log campaign activity with analytics metadata:

```python
from scripts.outcome_tracker import create_campaign, log_signal, log_outcome, log_outreach

campaign_id = create_campaign(engine, client_name="ExampleCo")
signal_id = log_signal(
    engine,
    campaign_id,
    signal_type="job_posting",
    company_name="Acme",
    signal_strength=3,
    icp_grade="A",
    scanner_name="jobs",
)
outreach_id = log_outreach(
    engine,
    signal_id,
    channel="email",
    template="hiring-signal",
    template_variant="A",
    experiment_tag="job-email-A",
)
log_outcome(engine, outreach_id, outcome_type="positive_reply")
```

3. Generate a report:

```bash
python -m scripts.analytics_report --last-days 30 --format markdown
```

Use `--campaign-id` to isolate one campaign, `--format json` for machine-readable output, and `--out` to write the report to disk.

## Current Behavior

Funnel rates are calculated from the local tracker tables. Open, click, reply, positive reply, meeting, deal, bounce, and unsubscribe rates are safe-divided and return `0.0` when there is no denominator.

Breakdowns currently support:

- `signal_type`
- `scanner_name`
- `icp_grade`
- `channel`
- `template_used`
- `template_variant`
- `experiment_tag`

Recommendations are deterministic and rule-based. V1 flags:

- the strongest signal source in the selected window
- templates with enough sends but no positive outcomes
- C/D ICP grades consuming volume without positive outcomes
- outreach sent more than seven days after signal detection

## Handoff Notes

The most important next integration is getting external engagement systems to write into the tracker tables consistently. Instantly, HubSpot, and n8n should map their event IDs into `external_id` so duplicate imports can be handled cleanly in a later pass.

The current migration approach is intentionally minimal and SQLite-specific. If SignalForce moves to a shared production database, replace `_migrate_existing_schema()` with a real migration tool such as Alembic.

Recommendation thresholds are conservative defaults. The report is useful immediately for small pilots, but recommendations become more reliable once each segment has enough sends to compare conversion rates meaningfully.

## Verification

Relevant tests:

```bash
pytest tests/unit/test_analytics.py tests/unit/test_db.py tests/unit/test_outcome_tracker.py
```

These cover empty and populated funnels, grouped analytics, stale signal detection, recommendation rendering, metadata persistence, new outcome types, and analytics schema columns.
