# GTM Context: SecureAPI

Shared context loaded by all SignalForce skills. Reference this file for company positioning, ICP definitions, messaging guidelines, and qualification criteria.

---

## Company

| Field | Details |
|---|---|
| Name | SecureAPI |
| Category | API security testing platform |
| Founded | 2022 |
| HQ | San Francisco, CA |
| Stage | Series A |

---

## Product

**Core offering:** Automated API security testing that finds vulnerabilities before attackers do.

- Integrates directly into CI/CD pipelines — catches security regressions on every PR
- **Key differentiator:** Runs full DAST coverage on API endpoints without requiring manual test authoring
- **API compatibility:** Works with REST, GraphQL, and gRPC APIs — no instrumentation required
- Covers OWASP API Top 10, business logic flaws, and authentication weaknesses

---

## ICP Tiers (Priority Order)

### Tier 1: Enterprise DevSecOps Teams

| Field | Details |
|---|---|
| Target companies | SaaS companies with 50+ engineers and a dedicated AppSec or DevSecOps function |
| Buyer signal | Active hiring for AppSec roles, DAST/SAST tooling in repos |
| Decision makers | Head of Application Security, CISO |
| Why they buy | Need automated coverage at scale without manual test authoring |
| Deal size | $80K–$300K ARR |

### Tier 2: API-First SaaS Companies

| Field | Details |
|---|---|
| Target companies | Startups and mid-size SaaS where the product is an API |
| Buyer signal | API gateway code, public API docs, API security job postings |
| Decision makers | VP Engineering, CTO |
| Why they buy | A security incident on their API is a product outage |
| Deal size | $30K–$100K ARR |

### Tier 3: Financial Services and Fintech

| Field | Details |
|---|---|
| Target companies | Banks, fintechs, payment processors |
| Buyer signal | PCI-DSS compliance requirements, API security in job descriptions |
| Decision makers | CISO, VP of Security |
| Why they buy | Regulatory compliance mandates continuous API security testing |
| Deal size | $100K–$500K ARR |

---

## Target Titles (Priority Order)

1. Head of Application Security / Director of AppSec
2. CISO / VP of Security
3. Principal Security Engineer / Staff Security Engineer
4. VP Engineering / CTO (at companies with fewer than 100 engineers)
5. DevSecOps Lead / Security Architect

---

## Voice & Tone

**Persona:** Security peer, not a vendor.

**Always do:**
- Lead with the specific vulnerability class or attack surface you identified in their stack
- Reference their API documentation, GitHub repos, or job postings directly
- Use precise security terminology (DAST, SAST, OWASP API Top 10, IDOR, BOLA, etc.)
- Keep initial outreach to 4 sentences maximum
- Use low-friction CTAs ("worth a 20-minute technical walkthrough?")

**Never use:**
- "I hope this email finds you well"
- Generic security FUD without a specific threat
- "I noticed your company"
- Feature lists without connecting to their specific tech stack

---

## Quick Reference: Signal Keywords

Use these to identify qualified prospects from public signals:

**Strong signals:**
- OWASP, DAST, SAST, API security testing, penetration testing
- Fuzzing, vulnerability scanning, zero-day, BOLA, IDOR
- Job postings for: Application Security Engineer, DevSecOps Engineer, AppSec Lead
- GitHub repos with api-security, owasp, fuzzing topics

**Weak / disqualifying signals:**
- No public API surface
- Security team is entirely outsourced to an MSSP
- No active engineering team
