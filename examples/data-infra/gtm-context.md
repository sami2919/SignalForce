# GTM Context: PipelineHQ

Shared context loaded by all SignalForce skills. Reference this file for company positioning, ICP definitions, messaging guidelines, and qualification criteria.

---

## Company

| Field | Details |
|---|---|
| Name | PipelineHQ |
| Category | Data pipeline orchestration |
| Founded | 2022 |
| HQ | Seattle, WA |
| Stage | Series A |

---

## Product

**Core offering:** Managed data pipeline orchestration that eliminates the infrastructure burden of running Airflow, Dagster, or Prefect at scale.

- Connect your existing data sources and destinations — PipelineHQ handles scheduling, retries, alerting, and scaling
- **Key differentiator:** Zero-ops pipeline management — no Kubernetes, no Helm charts, no on-call for the orchestrator itself
- **Compatibility:** Drop-in replacement for self-managed Airflow with full DAG import support
- Covers batch, micro-batch, and streaming pipelines within a single managed platform

---

## ICP Tiers (Priority Order)

### Tier 1: Data Engineering Teams at Analytics-Heavy Companies

| Field | Details |
|---|---|
| Target companies | E-commerce, fintech, media, SaaS with 5+ data engineers |
| Buyer signal | Airflow, dbt, Spark repos, data engineering job postings |
| Decision makers | Head of Data Engineering, VP of Data |
| Why they buy | Tired of maintaining the orchestration layer instead of building pipelines |
| Deal size | $50K–$200K ARR |

### Tier 2: Enterprise Data Platform Modernization

| Field | Details |
|---|---|
| Target companies | Large enterprises migrating from on-prem Hadoop to cloud |
| Buyer signal | Data lakehouse repos, Databricks or Snowflake adoption, platform re-architecture postings |
| Decision makers | Director of Data Engineering, VP of Data |
| Why they buy | Need managed orchestration during migration without building a new platform team |
| Deal size | $150K–$500K ARR |

### Tier 3: Real-Time and Streaming Data Teams

| Field | Details |
|---|---|
| Target companies | Fraud detection, personalization, operational analytics teams |
| Buyer signal | Kafka or Flink repos, real-time analytics job postings |
| Decision makers | Head of Data Engineering, CTO |
| Why they buy | Streaming pipelines have tighter SLAs and need managed retry and monitoring |
| Deal size | $80K–$300K ARR |

---

## Target Titles (Priority Order)

1. Head of Data Engineering / Director of Data Engineering
2. VP of Data
3. Principal Data Engineer / Staff Data Engineer
4. VP Engineering / CTO (at companies with fewer than 50 data engineers)
5. Data Engineering Manager

---

## Voice & Tone

**Persona:** Fellow data engineer, not a vendor.

**Always do:**
- Lead with the operational burden of their current setup (on-call for Airflow, upgrade cycles, infra toil)
- Reference their specific stack (Airflow version, dbt project size, Kafka topic counts if visible)
- Use data engineering terminology (DAG, orchestration, lineage, backfill, SLA breach, data quality)
- Keep initial outreach to 4 sentences maximum
- Use low-friction CTAs ("worth a 20-minute technical conversation?")

**Never use:**
- "I hope this email finds you well"
- Generic claims about "10x faster pipelines"
- "I noticed your company"
- Feature lists without connecting to their specific data stack

---

## Quick Reference: Signal Keywords

Use these to identify qualified prospects from public signals:

**Strong signals:**
- Airflow, dbt, Spark, Kafka, Flink, Dagster, Prefect
- Data lakehouse, ETL, ELT, data orchestration, data pipeline
- Job postings for: Data Engineer, Data Platform Engineer, Analytics Engineer
- GitHub repos with data-pipeline, etl, data-engineering, apache-airflow topics

**Weak / disqualifying signals:**
- No data engineering function — only analysts using BI tools
- Fewer than 5 data engineers
- Data infrastructure fully managed by turnkey SaaS with no pipeline ownership
