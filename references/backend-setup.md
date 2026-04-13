# Backend Setup Contract

Authoritative reference for how `metaopt-preflight` evaluates and bootstraps
backend readiness before an `ml-metaoptimization` v4 campaign begins.

## Ownership model

Backend responsibilities are split between preflight (readiness evaluation)
and the runtime worker (execution). There is no delegation layer between them.

| Layer | Role in backend setup |
|-------|----------------------|
| **`metaopt-preflight`** | Evaluates whether the execution environment has the prerequisites for a campaign: SkyPilot installed and configured for Vast.ai, WandB credentials available, project repo accessible. Performs bounded environment-level bootstrap when possible. Emits the readiness artifact. |
| **`skypilot-wandb-worker`** | Leaf execution worker dispatched by the orchestrator at runtime. Owns all SkyPilot and WandB API operations: sweep creation, `sky launch` on Vast.ai, sweep polling with watchdog, smoke tests. Never invoked by preflight. |
| **`ml-metaoptimization`** | Orchestrator. Dispatches `skypilot-wandb-worker` via directives. Consumes the readiness artifact to gate campaign entry at `LOAD_CAMPAIGN`. Assumes backend prerequisites are satisfied when the artifact says `READY`. |

**Key principle:** preflight owns the *decision* of whether the environment
can support a campaign. It does not provision compute, create sweeps, or
manage any runtime backend lifecycle — all of that belongs to
`skypilot-wandb-worker` at runtime.

## Backend technology

The v4 backend uses:

- **SkyPilot** — cloud orchestration layer. Launches ephemeral GPU instances
  via `sky launch` on **Vast.ai**. Instances self-terminate via
  `--idle-minutes-to-autostop`. There is no persistent cluster or head node.
- **WandB API** — sweep creation and monitoring. The worker creates sweeps via
  `wandb sweep`, launches WandB agents on SkyPilot instances, and polls sweep
  status through the WandB Python API.
- **No persistent infrastructure** — no Ray cluster, no Hetzner servers, no
  queue directories, no head node. Every compute instance is ephemeral and
  managed by SkyPilot.

## Backend readiness checks

Preflight evaluates backend readiness through a set of checks. These checks
establish a **minimal ready state** — the minimum conditions under which
`ml-metaoptimization` can safely start its campaign loop and expect
`skypilot-wandb-worker` operations to succeed.

### Check catalog

| Check | What it verifies | How verified |
|-------|-----------------|--------------|
| **SkyPilot installed** | `sky` CLI is available on PATH | Check that `sky` command resolves |
| **Vast.ai configured** | SkyPilot can reach the Vast.ai provider | Run `sky check` and verify Vast.ai is listed as enabled |
| **WandB credentials** | WandB API access is configured | Check that `WANDB_API_KEY` environment variable is set, or that `~/.netrc` contains a `wandb.ai` entry (indicating `wandb login` was run) |
| **Project repo accessible** | `project.repo` git URL can be reached | Verify git credentials allow access (e.g., `git ls-remote` against the URL) |
| **Smoke test command present** | `project.smoke_test_command` is syntactically non-empty | Verify the field is a non-empty string in the campaign spec. Preflight does NOT execute the command — execution happens during `LOCAL_SANITY` at runtime via `skypilot-wandb-worker` |

All checks in this table must pass for the readiness artifact to emit
`status: "READY"`. Failure of any check produces `status: "FAILED"` with
an actionable `failures` entry.

### What is NOT part of backend readiness

The following are **runtime/capacity concerns** that belong to the campaign
execution loop — not to preflight:

- **GPU availability or pricing** — preflight does not probe whether the
  requested accelerator (e.g., `A100:1`) is currently available on Vast.ai.
  Availability is transient and checked by SkyPilot at launch time.
- **WandB project/entity existence** — preflight verifies credentials but
  does not create the WandB project or validate entity permissions. The
  worker handles project creation implicitly via `wandb sweep`.
- **Sweep creation or management** — sweep lifecycle is owned entirely by
  `skypilot-wandb-worker` at runtime.
- **SkyPilot cluster provisioning** — there are no persistent clusters to
  provision. `sky launch` creates ephemeral instances on demand.
- **Budget enforcement** — spend tracking and budget caps are enforced during
  `poll_sweep` at runtime, not during preflight.

## Bootstrap mutations

When a readiness check fails due to a missing but installable prerequisite,
preflight MAY perform a bounded idempotent bootstrap action. All bootstrap
actions must satisfy the constraints in `references/boundary.md` § Bootstrap
mutations.

In v4, backend bootstrap is limited to **environment-level prerequisites**.
There is no remote infrastructure to provision (no cluster, no queue
directories, no head node).

| Condition | Bootstrap action |
|-----------|-----------------|
| `sky` not on PATH | Advise installation of SkyPilot (`pip install skypilot[vastai]`). Preflight MAY attempt the install if the Python environment is writable. |
| Vast.ai not configured in SkyPilot | Advise running `sky check` setup flow. Preflight records the failure with remediation instructions. |
| `WANDB_API_KEY` missing and `wandb login` not run | Advise setting the environment variable or running `wandb login`. Preflight MAY prompt for the key if running interactively. |
| `project.repo` inaccessible | Advise configuring SSH keys or HTTPS credentials for the git URL. No automated bootstrap — credential setup requires user action. |

### Bootstrap constraints

- **Idempotent.** Re-running a bootstrap action against an already-ready
  environment is a no-op.
- **Environment-scoped.** Bootstrap actions are limited to local tool
  installation and credential verification. Preflight never provisions remote
  compute or creates cloud resources.
- **Bounded.** Bootstrap does not modify experiment code, campaign state,
  WandB projects, or SkyPilot clusters. It brings the local environment to
  minimal ready state only.
- **Fail-fast.** If a bootstrap action fails, preflight records the failure
  and emits `status: "FAILED"` — it does not retry.

After bootstrap, preflight re-evaluates the affected readiness checks. If
they now pass, the bootstrap is considered successful.

## Integration with the readiness artifact

Backend checks map to the readiness artifact as follows:

- **`checks_summary.total`** includes all backend checks evaluated.
- **`checks_summary.passed`** / **`failed`** reflect final post-bootstrap
  results.
- **`checks_summary.bootstrapped`** counts checks that failed initially but
  passed after a bootstrap action.
- **`failures[]`** entries for backend checks use `category: "backend"` and
  include `check_id`, a human-readable `message`, and a `remediation` hint.
- **`diagnostics`** may include notes on bootstrap actions taken
  (e.g., "installed SkyPilot via pip").

Freshness considerations: backend readiness is a **Tier 2 (operational)**
signal — it reflects a point-in-time check that cannot be re-verified by
hash comparison alone. If the orchestrator suspects backend state has changed
since preflight ran, re-invocation is the correct response.
See `references/readiness-artifact.md` § Freshness tiers.

## `runtime_config_hash`

The readiness artifact includes a `runtime_config_hash` field. In v4 this
hash covers `compute`, `wandb`, `project.repo`, and
`project.smoke_test_command` from the campaign spec.

Preflight computes this hash using the same canonicalization rules as
`ml-metaoptimization` (see `ml-metaoptimization/references/contracts.md`
§ Identity Hash Computation). The orchestrator uses it for binding freshness
— verifying that the environment preflight checked matches the campaign
configuration the orchestrator is about to run.

**Current status:** v4 does not validate `runtime_config_hash` at campaign
entry. The field is emitted by preflight and reserved for v5+ orchestrator
validation. Preflight must still compute and include it so the artifact
schema is forward-compatible.

## Out of scope

The following topics are explicitly outside this contract:

| Topic | Where it belongs |
|-------|-----------------|
| SkyPilot cluster creation (`sky launch`) | `skypilot-wandb-worker` at runtime |
| WandB sweep creation and monitoring | `skypilot-wandb-worker` at runtime |
| Budget tracking and spend caps | `skypilot-wandb-worker` `poll_sweep` operation |
| Smoke test execution | `skypilot-wandb-worker` `run_smoke_test` operation (via `LOCAL_SANITY`) |
| Instance lifecycle (autostop, crash recovery) | `skypilot-wandb-worker` + SkyPilot autostop |
| Repository setup and validation (file structure, dependencies, campaign file) | `references/repo-setup.md` |
| Failure taxonomy and retry semantics | `references/readiness-artifact.md` for artifact schema; `ml-metaoptimization` for retry policy |

## References

- `references/boundary.md` — ownership boundary, lifecycle phases, mutation constraints
- `references/readiness-artifact.md` — artifact schema, freshness tiers, consumption protocol
- `ml-metaoptimization/references/backend-contract.md` — worker operations contract (launch_sweep, poll_sweep, run_smoke_test)
- `ml-metaoptimization/references/dependencies.md` — environment dependencies and campaign YAML validation rules
- `ml-metaoptimization/references/contracts.md` — state schema, identity hash, `runtime_config_hash` definition
- `ml-metaoptimization/.github/agents/skypilot-wandb-worker.agent.md` — leaf worker that drives SkyPilot/WandB at runtime
