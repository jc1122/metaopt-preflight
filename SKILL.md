---
name: metaopt-preflight
description: >
  One-shot idempotent preflight skill that validates backend, repository, and
  environment readiness before an ml-metaoptimization campaign begins.
---

# metaopt-preflight

## Overview

**Lane type:** standalone / one-shot
**Model class:** to be determined
**State mutation:** bounded persistent bootstrap mutations only (detailed boundaries TBD)

This skill runs before the `ml-metaoptimization` orchestrator starts a campaign.
It checks that all prerequisites are met (backend reachable, repo state clean,
required files present, environment configured) and emits a persisted readiness
artifact that the orchestrator uses to gate campaign entry.

## Input contract

<!-- To be defined in later tasks -->

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| TBD | — | — | — |

## Output contract

<!-- To be defined in later tasks -->

| Field | Type | Description |
|-------|------|-------------|
| TBD | — | — |

The output is a **readiness artifact** consumed by `ml-metaoptimization` to
confirm that the environment is safe to begin a campaign run.

## Behavioral rules

<!-- To be refined in later tasks -->

1. The skill MUST be idempotent — running it twice produces the same result.
2. The skill MAY perform bounded persistent bootstrap mutations (e.g., backend/delegation setup, metaopt scaffolding, declared repo-preparation steps) required for metaoptimization readiness. It MUST NOT make experiment-specific code changes or modify campaign state. Detailed mutation boundaries will be specified in later tasks.
3. The skill MUST produce a clear pass/fail signal with actionable diagnostics on failure.
4. The skill MUST complete in a single invocation (no resumption).

## Common mistakes

| Mistake | Why it matters |
|---------|----------------|
| Unbounded or experiment-specific mutations | Preflight may bootstrap, but must not make experiment-specific changes; all mutations must be idempotent |
| Skipping backend connectivity | Campaign will fail at runtime if backend is unreachable |
| Coupling to orchestrator internals | This skill must remain independently invocable |

## References

- [ml-metaoptimization](../ml-metaoptimization) — downstream orchestrator
- [ml-metaoptimization/references/backend-contract.md](../ml-metaoptimization/references/backend-contract.md) — backend expectations
