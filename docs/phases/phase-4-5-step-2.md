# Phase 4.5, Step 2: Shared Canonical Utilities

**Status:** Complete  
**Scope:** Behavior-neutral canonical JSON and SHA-256 utility extraction.

## Result

Canonical serialization and hashing moved to dependency-free
`tradepilot.core.canonical`. Duplicated serialization in source-artifact code
was removed. `tradepilot.reporting.canonical` remains a compatibility re-export
so existing callers continue to work.

Imports now point toward the low-level core package. Canonical UTF-8 bytes,
Decimal strings, timestamps, dataset IDs, checksums, report identities, and
research formulas remain unchanged.

## Main files

```text
research/src/tradepilot/core/canonical.py
research/src/tradepilot/core/__init__.py
research/src/tradepilot/reporting/canonical.py
research/src/tradepilot/data/source_artifacts.py
research/tests/test_identity_golden.py
```

## Verification

Golden identity regression tests verify byte-for-byte and hash compatibility.
The later Phase 4.5 final verification passed all eight identity tests and the
complete 234-test suite, with two credential-gated OANDA skips.

## Limitations

Atomic storage, simulation, workflow composition, and research formulas were
intentionally not refactored.

## Next step

Move cross-domain readiness orchestration out of the data package.

