# Phase 5, Step 12: Docker Compose and Full-System Integration

Status: implemented, pending review and commit.

## Topology

```text
trusted OIDC issuer --HTTPS/JWKS--> API --tradepilot_api--> PostgreSQL
                                      |                     ^
                                      | read-only artifacts |
                                      v                     |
                               dataset/report store         |
                                      ^                     |
                                      | reports read/write  |
                                      +-- worker --tradepilot_worker
                                             |
                                             +-- controlled Python engine

migrations --tradepilot_migrator---------------------------> PostgreSQL
```

PostgreSQL and the worker use an internal Docker network. The API has a separate
egress network only to retrieve trusted JWKS over HTTPS. No service publishes a
host port in `compose.yaml`; the development override binds only to loopback.

## Images and storage

The API and worker use multi-stage builds, a non-root runtime user, read-only
root filesystems, dropped capabilities, bounded processes, CPU and memory, and
an init process. Both include Python verification support; only the worker runs
the approved research-execution contract.

Dataset storage is mounted read-only. Report storage is read-only in the API
and writable only in the worker. Images contain no credentials, licensed data,
or host paths. Database passwords arrive through Docker secrets.

## Revision, recovery, and smoke test

Production builds and configuration require a lowercase 40-character Git SHA;
`unknown` is rejected. The API pins it into each job and workers reject a
mismatch.

`server/scripts/docker-integration.ps1` uses isolated temporary secrets and
synthetic artifacts. It starts a runtime-generated TLS OIDC fixture, migrates
the database, registers a verified dataset, authenticates, and submits a job.
It pauses and kills the worker after the job is running, waits beyond lease
expiry, restarts the worker, and verifies recovery, report registration,
historical evidence access, and deterministic immutable report reuse.

The OIDC fixture and execution delay exist only in the integration Compose
overlay. No profitability calculation, live signal, broker action, or real
market data is involved.

## Limitations

- Local Compose secrets are file backed; production should use a managed secret
  store.
- Artifact and PostgreSQL backup consistency remains an operator responsibility.
- Runtime resource limits do not replace cluster quotas and monitoring.
- OIDC egress should be restricted to the issuer by the deployment platform.
- The smoke OIDC service is test-only and must never be used as an identity
  provider.
