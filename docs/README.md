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

## Report convention

Create one Markdown file after every completed step under `docs/phases/` using:

```text
phase-{phase-number}-step-{step-number}.md
```

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

