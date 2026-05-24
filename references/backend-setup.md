# Backend Setup Contract

Authoritative reference for how `metaopt-preflight` evaluates and bootstraps
backend readiness before an `ml-metaoptimization` v4 campaign begins.

## Ownership model

Backend responsibilities are split between preflight (readiness evaluation)
and the runtime worker (execution). There is no delegation layer between them.

| Layer | Role in backend setup |
|-------|----------------------|
| **`metaopt-preflight`** | Evaluates whether the execution environment has the prerequisites for a campaign: SkyPilot installed and configured for Vast.ai, WandB credentials available, project repo accessible. Emits the readiness artifact plus advisory remediation guidance for missing backend prerequisites. Does **not** install packages, prompt for credentials, or mutate remote backend/provider state. |
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

Hard-failure backend checks must pass for the readiness artifact to emit
`status: "READY"`. Warning-category backend checks are advisory: they
increment `checks_summary.warnings`, may be summarized in `diagnostics`, and do
**not** create backend failure records on their own. This does not weaken hard
repository checks over the same field; for example, missing
`project.smoke_test_command` still fails repo check R7.

### Check catalog

| Check | Category | Blocking? | What it verifies | How verified |
|-------|----------|-----------|------------------|--------------|
| **SkyPilot installed** | `backend` | Yes | `sky` CLI is available on PATH | Run `sky version` |
| **Vast.ai configured** | `backend` | Yes | SkyPilot can reach the Vast.ai provider | Run `sky check --cloud vast` and verify Vast.ai is reported as enabled |
| **WandB credentials** | `backend` | Yes | WandB API access is configured | Check that `WANDB_API_KEY` is set, or that `~/.netrc` contains an `api.wandb.ai` entry |
| **Project repo accessible** | `backend` | Yes | `project.repo` git URL can be reached | Verify git credentials allow access via `git ls-remote --exit-code` against the URL |
| **Smoke test command present** | `warning` | No additional backend blocker | Duplicate advisory check for `project.smoke_test_command` | Records a warning-category backend result. The authoritative presence requirement is hard repo check R7; preflight does **not** execute the command. |

All blocking backend checks in this table must pass for backend readiness.
Warning-category backend results do **not** populate `failures[]`; instead they
increment `checks_summary.warnings` and may be summarized in `diagnostics`.
They do not override hard repo failures.

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

## Backend bootstrap guidance

Backend bootstrap is **advisory-only**. `scripts/bootstrap/backend_bootstrap.py`
maps failed backend checks to operator guidance; it does not execute those
remediation steps on the user's behalf.

There is no backend package installation, credential prompting/storage, or
remote provider provisioning in the current implementation.

| Condition | Guidance emitted |
|-----------|------------------|
| `sky` not on PATH | Install SkyPilot manually (`pip install 'skypilot[vast]'`) and then run `sky check` |
| Vast.ai not configured in SkyPilot | Get a Vast.ai API key, run `vast set api-key <YOUR_KEY>`, then run `sky check` |
| `WANDB_API_KEY` missing and `wandb login` not run | Set `WANDB_API_KEY` or run `wandb login` manually |
| `project.repo` inaccessible | Configure SSH keys or HTTPS credentials for the git URL |
| `project.smoke_test_command` missing/empty | Set `project.smoke_test_command` in the campaign YAML so runtime can perform `LOCAL_SANITY` |

### Bootstrap constraints

- **Advisory-only.** Backend bootstrap emits guidance text only; there are no
  automated backend fixes in the current implementation.
- **Non-mutating.** Preflight does not install packages, run `wandb login`,
  write `~/.netrc`, configure Vast.ai, or provision remote compute.
- **Environment-scoped.** Guidance is limited to local tooling, credentials,
  and repo reachability prerequisites for runtime execution.
- **Fail-fast.** The original failed backend checks remain failed until the
  operator remediates them and re-runs preflight.

Because backend bootstrap performs no automated fix, the same invocation does
not re-evaluate backend checks into a bootstrapped success state. Backend
issues are resolved on a later preflight run after user action.

## Integration with the readiness artifact

Backend checks map to the readiness artifact as follows:

- **`checks_summary.total`** includes all backend checks evaluated.
- **`checks_summary.passed`** / **`failed`** reflect final hard-check
  outcomes.
- **`checks_summary.bootstrapped`** does not increase for backend checks in the
  current implementation because backend bootstrap is advisory-only.
- **`checks_summary.warnings`** counts failed warning-category checks such as
  `smoke_test_command_nonempty`.
- **`failures[]`** entries for backend hard failures use `category: "backend"`
  and include `check_id`, a human-readable `message`, and a `remediation`
  hint. Warning-category checks do not appear in `failures[]`.
- **`diagnostics`** may include backend guidance action IDs plus warning
  summaries (for example, `ENV_WANDB_GUIDANCE: ...` or `Warnings:
  smoke_test_command_nonempty: ...`).

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
