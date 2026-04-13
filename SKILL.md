---
name: metaopt-preflight
description: >
  One-shot idempotent preflight skill that validates backend, repository, and
  environment readiness before an ml-metaoptimization campaign begins.
---

# metaopt-preflight

## Overview

**Lane type:** standalone / one-shot
**Model class:** strong_reasoner
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

## Invocation

```bash
# Preferred (works from any directory):
python3 -m scripts.run_preflight --campaign path/to/campaign.yaml [--cwd /project/root]

# Also works (must be run from repo root):
python3 scripts/run_preflight.py --campaign path/to/campaign.yaml [--cwd /project/root]
```

Exit codes: `0` = READY, `1` = FAILED, `2` = usage/input error.

### CLI arguments

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `--campaign` | Yes | — | Path to campaign YAML file |
| `--cwd` | No | `.` | Project root directory |

## Input contract

### Campaign file — `ml_metaopt_campaign.yaml`

Preflight reads the campaign file for existence, basic structure, and the
fields needed to compute artifact hashes and scope readiness checks. It does
**not** perform full schema validation (that is `LOAD_CAMPAIGN`'s job).

| Field path | Used for |
|------------|----------|
| `campaign.name` | Campaign identifier; included in `campaign_identity_hash` |
| `objective.metric` | Included in `campaign_identity_hash` |
| `objective.direction` | Included in `campaign_identity_hash` |
| `wandb.entity` | WandB connectivity check; included in `campaign_identity_hash` |
| `wandb.project` | WandB connectivity check; included in `campaign_identity_hash` |
| `project.repo` | Repository structure validation |
| `project.smoke_test_command` | Smoke-test availability check (if declared) |
| `compute.*` | Backend/delegation infrastructure readiness checks |

### Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `WANDB_API_KEY` (or active `wandb login` session) | Yes | WandB authentication for connectivity check |
| SkyPilot configuration (`~/.sky/`) | Yes | Backend delegation infrastructure credentials |

### Runtime (implicit)

Preflight runs within the agent runtime provided by the caller. It does not
declare an explicit runtime dependency — any agent model/runtime that can
execute shell commands and read/write files is sufficient.

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
| `preflight_duration_seconds` | number | Wall-clock duration of the preflight invocation in seconds. |
| `checks_summary` | object | Aggregate counts: `total`, `passed`, `failed`, `bootstrapped`, `warnings`. |
| `failures` | array | Failure records with `check_id`, `category`, `message`, `remediation`. Empty when `READY`. |
| `next_action` | string | `"proceed"` when `READY`; remediation guidance when `FAILED`. |
| `diagnostics` | string or null | Free-form notes (bootstrap actions taken, warnings). |

**Status semantics:** `READY` means all checks passed and
`ml-metaoptimization` may proceed. `FAILED` means one or more checks remain
failed — `failures` contains actionable details.

**Freshness model:** The orchestrator verifies binding freshness cheaply by
checking that the artifact's `campaign_identity_hash` matches its own
computed value. If the campaign YAML is edited after preflight ran (changing
name, objective, or WandB target), the hash will not match and the
orchestrator will emit `BLOCKED_CONFIG` requiring a preflight rerun.
`runtime_config_hash` is included in the artifact for forward compatibility
but is **not validated by v4** of the orchestrator. Operational conditions
(backend reachability, dependency availability) are point-in-time and cannot
be re-verified without re-running preflight.

> **Authoritative hash definition:** The `campaign_identity_hash` computation
> is defined by `ml-metaoptimization/scripts/load_campaign_handoff.py::_identity_hash()`.
> It extracts only specific subfields — `campaign.name`, `objective.metric`,
> `objective.direction`, `wandb.entity`, `wandb.project` — not the entire
> top-level blocks as the prose in `contracts.md` Section 4 might suggest.
> Preflight must use the same subfields to produce a matching hash.

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

## Context Window Guide

**Read `references/context-window-guide.md` before your first action.** It tells you exactly which files to read, when, and which to skip to stay within your context budget.

TL;DR: read `SKILL.md` + `references/readiness-artifact.md` + the campaign YAML at the start of every invocation. Reach for the other reference docs only when debugging a specific check failure. Never read `tests/`, `scripts/bootstrap/`, or orchestrator source. Estimated budget: ~2000–4000 tokens before check results.

## References

- `references/boundary.md` — authoritative ownership boundary and lifecycle
- `references/readiness-artifact.md` — readiness artifact schema, freshness rules, and consumption protocol
- `references/backend-setup.md` — backend setup contract, readiness conditions, and bootstrap actions
- `references/repo-setup.md` — repo setup contract, structural readiness, and scaffolding mutations
- [ml-metaoptimization](../ml-metaoptimization) — downstream orchestrator
- [ml-metaoptimization/references/contracts.md](../ml-metaoptimization/references/contracts.md) — campaign identity and runtime config hash definitions
- [ml-metaoptimization/references/backend-contract.md](../ml-metaoptimization/references/backend-contract.md) — backend expectations
