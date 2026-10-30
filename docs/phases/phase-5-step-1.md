# Phase 5, Step 1: Backend Architecture Design

**Status:** Planning complete; no implementation  
**Scope:** Node.js, Express, PostgreSQL, and Python integration design only.

## Decision

The approved MVP design uses Express as the API/control plane and a dedicated
Node worker that invokes a fixed, versioned Python subprocess contract. Python
remains the only research engine. FastAPI is deferred until independent Python
scaling or a network service boundary is justified.

PostgreSQL is planned for catalog metadata, users, authorization, job state,
and audit records. Immutable Parquet datasets and canonical JSON reports remain
the research authorities. Node must never recalculate Python content identities
or duplicate trading formulas.

Planned read-only APIs cover instruments, datasets, historical candidate
reports, and evidence. Every research response must be explicitly historical
and must never be presented as a live signal.

## Required implementation sequence

1. Express and strict TypeScript foundation.
2. Secure immutable-artifact catalog and read APIs.
3. Versioned Python JSON contract.
4. Asynchronous PostgreSQL-backed research jobs.
5. Docker development and CI gates.
6. Authentication and production hardening.

## Limitations

This step created no files, endpoints, database objects, worker, containers, or
authentication. It made no research or identity changes.

## Next step

Implement only the backend foundation and health endpoints.

