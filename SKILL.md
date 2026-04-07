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
**State mutation:** bounded idempotent bootstrap mutations only (detailed boundaries TBD)

This skill is a **one-shot preflight phase** that runs before the
`ml-metaoptimization` orchestrator enters its campaign loop. It evaluates
whether the environment, backend, and repository are ready for a campaign,
performs bounded bootstrap mutations when necessary to achieve readiness, and
emits a persisted readiness artifact that gates `ml-metaoptimization` entry.

A single invocation covers the full preflight lifecycle. The skill does not
resume, does not loop, and does not participate in the campaign state machine.

## Ownership boundary

### What this skill owns

- **Environment and backend readiness evaluation** — verifying that runtime
  dependencies, backend connectivity, and queue infrastructure are functional.
- **Repository readiness evaluation** — verifying that the target repository
  has the required structure, files, and configuration for a campaign.
- **Bounded bootstrap mutations** — performing idempotent setup actions
  (e.g., backend/delegation provisioning, metaopt directory scaffolding,
  declared repo-preparation steps) required to bring the environment to a
  ready state. All mutations must be idempotent and bounded to bootstrap
  concerns; they must not touch experiment-specific code or campaign state.
- **Persisted readiness signal** — producing a readiness artifact that
  `ml-metaoptimization` consumes to confirm safe campaign entry. The artifact
  persists on disk so downstream consumers can read it without re-running
  preflight.

### What this skill does NOT own

- **Campaign loop** — the resumable deterministic state machine
  (`LOAD_CAMPAIGN` → … → `COMPLETE`) belongs entirely to `ml-metaoptimization`.
- **Proposal lifecycle** — ideation, selection, design, and rollover of
  experiment proposals are orchestrator concerns.
- **Experiment materialization and analysis** — code changes, local sanity,
  remote execution, and result analysis are campaign-phase work.
- **Resumable state machine** — preflight has no persisted machine state and
  no resume semantics. If it must be re-run, it starts from scratch.
- **Campaign state files** — preflight never reads or writes
  `.ml-metaopt/state.json` or the `AGENTS.md` resume hook.
- **Worker dispatch** — preflight does not launch or manage subagent workers.

See `references/boundary.md` for the authoritative boundary and lifecycle
specification.

## Lifecycle phases

A single invocation proceeds through these phases in order:

1. **Gather** — read configuration sources (campaign file, environment,
   backend declarations) to determine what must be checked and what bootstrap
   actions may be required.
2. **Evaluate** — run readiness checks against backend, repository, and
   environment. Collect pass/fail results and diagnostics for each check.
3. **Bootstrap** — if any checks failed due to missing but provisionable
   prerequisites, perform bounded idempotent mutations to remedy them.
   Re-evaluate affected checks after mutation.
4. **Emit** — produce the persisted readiness artifact summarizing the final
   readiness state. On failure, the artifact contains actionable diagnostics.
   On success, it confirms that `ml-metaoptimization` may proceed.

The skill exits after the Emit phase regardless of outcome. There is no retry
loop internal to the skill; the caller may re-invoke if failures are
remediated externally.

## Idempotency and rerun semantics

- **Idempotent by design.** Running preflight twice against the same
  environment and configuration produces the same readiness outcome. Bootstrap
  mutations are individually idempotent — re-applying them to an already-ready
  environment is a no-op.
- **No incremental state.** Each invocation is self-contained. The skill does
  not read its own prior readiness artifact to decide what to do; it always
  evaluates from scratch.
- **Artifact overwrite.** A rerun overwrites any previously emitted readiness
  artifact. The latest artifact is always authoritative.
- **Safe to re-invoke.** Because mutations are idempotent and evaluation is
  stateless, re-invocation after external remediation or environment changes
  is the intended recovery path.

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
confirm that the environment is safe to begin a campaign run. The detailed
artifact schema will be defined in a later task.

## Behavioral rules

1. The skill MUST be idempotent — running it twice produces the same result.
2. The skill MUST complete in a single invocation (no resumption, no
   persisted machine state).
3. The skill MAY perform bounded persistent bootstrap mutations (e.g.,
   backend/delegation setup, metaopt scaffolding, declared repo-preparation
   steps) required for metaoptimization readiness. It MUST NOT make
   experiment-specific code changes or modify campaign state.
4. The skill MUST produce a clear pass/fail signal with actionable
   diagnostics on failure.
5. The skill MUST NOT read or write `.ml-metaopt/state.json` or the
   `AGENTS.md` resume hook.
6. The skill MUST remain independently invocable — it must not depend on
   orchestrator internals or require the orchestrator to be running.

Detailed mutation boundaries, backend setup contract, and repo setup contract
will be specified in later tasks.

## Common mistakes

| Mistake | Why it matters |
|---------|----------------|
| Unbounded or experiment-specific mutations | Preflight may bootstrap, but must not make experiment-specific changes; all mutations must be idempotent |
| Skipping backend connectivity | Campaign will fail at runtime if backend is unreachable |
| Coupling to orchestrator internals | This skill must remain independently invocable |
| Writing campaign state files | `.ml-metaopt/state.json` and the `AGENTS.md` hook belong to `ml-metaoptimization` |
| Implementing retry/resume logic | Preflight is one-shot; the caller re-invokes if needed |
| Fully specifying artifact schema here | The readiness artifact schema is deferred to a later task |

## References

- `references/boundary.md` — authoritative ownership boundary and lifecycle
- [ml-metaoptimization](../ml-metaoptimization) — downstream orchestrator
- [ml-metaoptimization/references/backend-contract.md](../ml-metaoptimization/references/backend-contract.md) — backend expectations
