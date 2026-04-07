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
- **Campaign input validation** — full schema validation and sentinel
  detection for `ml_metaopt_campaign.yaml` belong to `ml-metaoptimization`
  (`LOAD_CAMPAIGN`). Preflight only checks that the campaign file exists and
  parses / has basic structure.

See `references/boundary.md` for the authoritative boundary and lifecycle
specification.

## Lifecycle phases

A single invocation proceeds through these phases in order:

1. **Gather** — read configuration sources (campaign file, environment,
   backend declarations) to determine what must be checked and what bootstrap
   actions may be required. For the campaign file this means checking
   existence and basic structure only — full schema validation is
   `LOAD_CAMPAIGN`'s responsibility.
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

The output is a **readiness artifact** persisted at
`.ml-metaopt/preflight-readiness.json`. The full schema and freshness rules
are defined in `references/readiness-artifact.md`.

Key fields:

| Field | Type | Description |
|-------|------|-------------|
| `schema_version` | integer | Artifact schema version (currently `1`). |
| `status` | string | `"READY"` or `"FAILED"`. |
| `campaign_id` | string | Campaign identifier from the campaign spec. |
| `campaign_identity_hash` | string | Campaign identity hash (`sha256:…`), matching the definition in `ml-metaoptimization/references/contracts.md`. |
| `runtime_config_hash` | string | Runtime config hash (`sha256:…`), matching the definition in `ml-metaoptimization/references/contracts.md`. |
| `emitted_at` | string | ISO 8601 timestamp of artifact emission. |
| `checks_summary` | object | Aggregate counts: `total`, `passed`, `failed`, `bootstrapped`. |
| `failures` | array | Failure records with `check_id`, `category`, `message`, `remediation`. Empty when `READY`. |
| `next_action` | string | `"proceed"` when `READY`; remediation guidance when `FAILED`. |
| `diagnostics` | string or null | Free-form notes (bootstrap actions taken, warnings). |

**Status semantics:** `READY` means all checks passed and
`ml-metaoptimization` may proceed. `FAILED` means one or more checks remain
failed — `failures` contains actionable details.

**Freshness model:** The orchestrator verifies binding freshness cheaply by
checking that the artifact's `campaign_identity_hash` and
`runtime_config_hash` match its own computed values. Operational conditions
(backend reachability, dependency availability) are point-in-time and cannot
be re-verified without re-running preflight.

**Overwrite semantics:** Each invocation overwrites any prior artifact. The
latest on disk is always authoritative.

## Behavioral rules

1. The skill MUST be idempotent — running it twice produces the same result.
2. The skill MUST complete in a single invocation (no resumption, no
   persisted machine state).
3. The skill MAY perform bounded idempotent bootstrap mutations (e.g.,
   backend/delegation setup, metaopt scaffolding, declared repo-preparation
   steps) required for metaoptimization readiness. It MUST NOT make
   experiment-specific code changes or modify campaign state.
4. The skill MUST produce a clear pass/fail signal with actionable
   diagnostics on failure.
5. The skill MUST NOT read or write `.ml-metaopt/state.json` or the
   `AGENTS.md` resume hook.
6. The skill MUST remain independently invocable — it must not depend on
   orchestrator internals or require the orchestrator to be running.

Detailed mutation boundaries are specified in the backend and repo setup
contracts. See `references/backend-setup.md` for backend bootstrap actions and
`references/repo-setup.md` for repo scaffolding and structural readiness.

## Common mistakes

| Mistake | Why it matters |
|---------|----------------|
| Unbounded or experiment-specific mutations | Preflight may bootstrap, but must not make experiment-specific changes; all mutations must be idempotent |
| Skipping backend connectivity | Campaign will fail at runtime if backend is unreachable |
| Coupling to orchestrator internals | This skill must remain independently invocable |
| Writing campaign state files | `.ml-metaopt/state.json` and the `AGENTS.md` hook belong to `ml-metaoptimization` |
| Implementing retry/resume logic | Preflight is one-shot; the caller re-invokes if needed |
| Inventing new identity hashes incompatible with `ml-metaoptimization` | Reuse `campaign_identity_hash` and `runtime_config_hash` from `ml-metaoptimization/references/contracts.md` |

## References

- `references/boundary.md` — authoritative ownership boundary and lifecycle
- `references/readiness-artifact.md` — readiness artifact schema, freshness rules, and consumption protocol
- `references/backend-setup.md` — backend setup contract, readiness conditions, and bootstrap actions
- `references/repo-setup.md` — repo setup contract, structural readiness, and scaffolding mutations
- [ml-metaoptimization](../ml-metaoptimization) — downstream orchestrator
- [ml-metaoptimization/references/contracts.md](../ml-metaoptimization/references/contracts.md) — campaign identity and runtime config hash definitions
- [ml-metaoptimization/references/backend-contract.md](../ml-metaoptimization/references/backend-contract.md) — backend expectations
