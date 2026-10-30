# Backend readiness review

## Verdict

The research codebase is ready for backend **contract and integration design**.
Its immutable artifacts, provenance, deterministic workflows, dependency gates,
and test coverage provide a stable foundation. It is not yet ready to expose
research execution directly as a production backend service.

No item below requires changing research formulas.

## Blocking before backend execution integration

1. **Choose and document the process boundary.** The planned Node.js backend
   must not import Python internals. Approve one explicit boundary—such as a
   versioned Python worker/service or controlled job process—with cancellation,
   timeout, resource, and error semantics.
2. **Version the machine-facing contract.** CLI JSON is useful for developers
   but is not yet a supported backend API. Define versioned request/result/error
   schemas for dataset lookup, candidate generation, report verification, and
   job status before backend code depends on output fields.
3. **Define artifact access and authorization.** Decide how the backend locates
   immutable datasets/reports, validates IDs before reading, prevents arbitrary
   path access, and separates locked-test artifacts from ordinary research.
4. **Add an automated CI gate.** A backend should not integrate against changes
   unless editable installation, the full suite, identity goldens, dependency
   boundaries, and CLI entry-point checks run on every change.

These are integration safeguards, not blockers for creating an isolated API
skeleton with synthetic responses and no research execution.

## Optional architecture improvements

- Adopt a formatter/linter/type checker only with a scoped configuration and a
  low-churn rollout; do not mix mass formatting with backend integration.
- Add coverage reporting as observation first, then approve thresholds based on
  risk rather than a blanket percentage.
- Replace broad package `__init__` re-exports where they cause measurable import
  cost or cycles; current dependency tests show no blocking violation.
- Add architecture decision records for future cross-language and persistence
  choices.
- Introduce explicit public facades only when a real backend use case shows that
  current workflow functions are too broad or unstable.

## Deferred product and research concerns

- Production scheduling, PostgreSQL persistence, authentication, scanner event
  deduplication, alerts, frontend, and AI explanations belong to later phases.
- Provider licensing and sufficient multi-year real-data coverage must be
  resolved before distributing data or making real-market evidence claims.
- Locked-test authorization remains sealed and must not be weakened for a demo.
- Financing, margin, liquidation, live execution, and broker integration remain
  intentionally outside the implemented research scope.
- Strategy profitability is not established; backend presentation must preserve
  evidence labels and avoid profitability claims.

## `pyproject.toml` review

The runtime declarations match current code: Python 3.12+, PyArrow, and Windows
`tzdata`. All 11 console scripts point to callable modules. Tests use standard
library `unittest` and `tomllib`, so no test dependency is missing.

Recommended minimal sequence:

1. add CI using the current dependency set;
2. select lint/type/coverage tools with configurations in a separate proposal;
3. only then add a `dev` optional-dependency group containing tools the project
   actually runs.

Adding unused development packages now would not improve reproducibility.

