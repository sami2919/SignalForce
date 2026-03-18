---
name: validate
description: "Use when verifying config.yaml is valid after editing, when troubleshooting why scanners return no results, or after running /setup to confirm the generated config works"
---

# Validate

Run each check in order. Print a summary report at the end.

## Check 1 — Schema validation

```bash
python -c "from scripts.config_loader import load_config; load_config()"
```

- **OK**: config loaded without errors
- **ERROR**: print the exception and stop — remaining checks are unreliable until schema errors are fixed

## Check 2 — Scanner modules importable

For each scanner marked `enabled: true` in `config/config.yaml`, verify its module path imports cleanly:

```bash
python -c "import <module_path>"
```

- **OK**: import succeeds
- **ERROR**: module not found or import error — note the scanner name and error

## Check 3 — Scanner has `scan()` function

For each enabled scanner module, verify it exposes a `scan()` function:

```bash
python -c "from <module_path> import scan"
```

- **OK**: function found
- **ERROR**: `scan` not defined in module

## Check 4 — Templates exist for enabled scanners

For each enabled scanner, check that at least one matching template file exists:

- Email template: `config/templates/email-sequences/<signal-type>*.md`
- LinkedIn template: `config/templates/linkedin-sequences/<signal-type>*.md`

- **OK**: at least one template found per channel
- **WARN**: template missing for a channel — outreach for this signal type will fail at runtime

## Check 5 — Keyword lists not empty

For each enabled scanner, check that its keyword list in `config/config.yaml` contains at least one entry.

- **OK**: one or more keywords present
- **WARN**: empty keyword list — scanner will run but likely return zero results

## Check 6 — Optional fields present

Check for missing optional fields that improve accuracy:

- `company.website` — used by prospect-researcher for domain enrichment
- `icp.disqualifiers` — used to filter false positives from scanner results

- **OK**: field present and non-empty
- **WARN**: field missing — note which field and its purpose

## Summary report

Print one line per check:

```
[OK]    Schema validation
[OK]    Scanner import: scripts.github_rl_scanner
[ERROR] Scanner import: scripts.arxiv_monitor — ModuleNotFoundError
[OK]    scan() function: scripts.github_rl_scanner
[WARN]  Template missing: linkedin-sequences/github*.md
[WARN]  Empty keywords: job_posting_scanner
[WARN]  Missing optional field: icp.disqualifiers
```

If any ERRORs exist, end with: "Fix ERRORs before running scans." and list the specific files or commands needed.

If only WARNs exist, end with: "Config is functional. Address WARNs to improve signal coverage."

If all checks pass, end with: "Config is valid. Ready to run /signal-scanner."
