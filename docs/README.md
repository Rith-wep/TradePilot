# TradePilot AI development reports

This folder records what was completed during each approved project step. The
reports use simple technical language so a developer can understand the result,
reproduce it, and see what remains unfinished.

## Reports

| Phase | Step | Report | Status |
| --- | --- | --- | --- |
| 1 | 1 | [Python Research Workspace and Data Validation](phases/phase-1-step-1.md) | Complete |
| 1 | 2 | [Market Data Provider Adapter and Historical Ingestion](phases/phase-1-step-2.md) | Complete |
| 1 | 3 | [Historical Dataset Integrity and Reproducibility](phases/phase-1-step-3.md) | Complete |
| 2 | 1 | [Technical Indicator Engine](phases/phase-2-step-1.md) | Complete |
| 2 | 2 | [Deterministic Trading Strategy Engine](phases/phase-2-step-2.md) | Complete |
| 2 | 3 | [Signal Validation and Reproducible Reports](phases/phase-2-step-3.md) | Complete |
| 3 | 1 | [Backtesting Architecture and Domain Models](phases/phase-3-step-1.md) | Complete |
| 3 | 2 | [Deterministic Event-Driven Execution Simulator](phases/phase-3-step-2.md) | Complete |
| 3 | 3 | [Deterministic Portfolio Accounting and Analytics](phases/phase-3-step-3.md) | Complete |
| 3 | 4 | [Chronological Validation and Robustness](phases/phase-3-step-4.md) | Complete |
| 4 | 1 | [OANDA Historical Forex Data Integration](phases/phase-4-step-1.md) | Complete |
| 4 | 2 | [Real-Data Verification and Research Readiness](phases/phase-4-step-2.md) | Complete |
| 4 | CSV import | [Dukascopy Paired CSV Import](phases/phase-4-dukascopy-csv-import.md) | Complete |
| 4 | Multi-year CSV | [Dukascopy Multi-Year Batch Import](phases/phase-4-dukascopy-multiyear.md) | Complete |
| 4.5 | 1 | [Architecture Documentation and Identity Protection](phases/phase-4-5-step-1.md) | Complete |
| 4.5 | 2 | [Shared Canonical Utilities](phases/phase-4-5-step-2.md) | Complete |
| 4.5 | 3 | [Workflow Separation](phases/phase-4-5-step-3.md) | Complete |
| 4.5 | 4 | [Shared Research Workflow](phases/phase-4-5-step-4.md) | Complete |
| 4.5 | 5 | [Developer Readiness and Final Architecture Review](phases/phase-4-5-step-5.md) | Complete |
| 5 | 1 | [Backend Architecture Design](phases/phase-5-step-1.md) | Planning complete |
| 5 | 2 | [Backend Foundation](phases/phase-5-step-2.md) | Complete |
| 5 | 3 | [PostgreSQL Foundation](phases/phase-5-step-3.md) | Complete |
| 5 | 4 | [Trusted Python Artifact Verification Contract](phases/phase-5-step-4.md) | Complete |
| 5 | 5 | [Controlled Node/Python Verification Adapter](phases/phase-5-step-5.md) | Complete |
| 5 | 6 | [Trusted Artifact Catalog Registration](phases/phase-5-step-6.md) | Complete |
| 5 | 7 | [Read-only Research Catalog APIs](phases/phase-5-step-7.md) | Complete |

## Architecture and development

- [Architecture and identity compatibility](architecture.md)
- [Project structure](project-structure.md)
- [Data and research flow](data-flow.md)
- [Development and CLI reference](development.md)

## Report convention

Create one Markdown file after every approved step, including planning-only or
blocked steps, under `docs/phases/` using:

```text
phase-{phase-number}-step-{step-number}.md
```

For decimal milestone numbers, replace the decimal point with a hyphen, for
example `phase-4-5-step-1.md`. Add the report to the table in the same change.
Use an accurate status such as `Complete`, `Planning complete`, or `Blocked`;
never label unimplemented work complete.

Each report should contain:

1. Goal and scope.
2. What was implemented.
3. Important technical decisions.
4. Files created or changed.
5. Commands for setup and use.
6. Tests executed and their actual results.
7. Known limitations.
8. The recommended next step, pending approval.

Reports must not claim a test passed unless it was executed. They must not
record API keys, proprietary datasets, or invented performance results.

