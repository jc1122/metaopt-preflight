# Backend Setup Contract

Authoritative reference for how `metaopt-preflight` configures and validates
backend readiness before an `ml-metaoptimization` campaign begins.

## Ownership model

Backend setup spans three layers. Each layer has a distinct role; preflight
coordinates but does not absorb responsibilities that belong elsewhere.

| Layer | Role in backend setup |
|-------|----------------------|
| **`metaopt-preflight`** | Orchestrates readiness evaluation and bounded bootstrap. Decides whether the backend is ready. Emits the readiness artifact. |
| **`hetzner-delegation`** | Delegation-first control layer. Owns cluster lifecycle actions (status, bootstrap, validate, sync, cleanup). Preflight delegates to it rather than invoking raw Hetzner/Ray commands. |
| **`ray-hetzner`** | Execution backend/runtime. Owns the queue infrastructure (`metaopt/` commands), cluster scripts, and server state. Preflight never modifies `ray-hetzner` internals directly. |
| **`ml-metaoptimization`** | Downstream consumer. Interacts with the backend exclusively through the `remote_queue` contract (`enqueue_command`, `status_command`, `results_command`). Assumes backend is ready at campaign start. |

**Key principle:** `metaopt-preflight` owns the *decision* of whether the
backend is ready. It delegates *actions* to `hetzner-delegation` and validates
*state* exposed by `ray-hetzner`. It never bypasses the delegation layer to
perform raw Hetzner administration.

## Supported backend path

The current implementation supports exactly one backend path:

```
metaopt-preflight
  └─ delegates to ─→ hetzner-delegation
                        └─ manages ─→ ray-hetzner (cluster + queue)
```

### How the relationship works

1. **Preflight invokes `hetzner-delegation` capabilities** — cluster status
   checks, bootstrap sequencing, and queue validation — using the delegation
   skill's documented interface. Preflight does not shell out to raw `hcloud`
   or SSH commands.

2. **`hetzner-delegation` translates to `ray-hetzner` scripts** — it calls
   `ray-hetzner` lifecycle scripts (`status.sh`, `setup_head.sh`,
   `build_base_snapshot.sh`, etc.) and queue commands (`enqueue_batch.py`,
   `get_batch_status.py`) as documented in the `ray-hetzner` README.

3. **Preflight interprets results** — the output from delegation calls
   (cluster state, queue response, error messages) is evaluated against the
   readiness conditions defined below. Preflight maps these to pass/fail
   check results in the readiness artifact.

### Extensibility

The backend path is not pluggable in the current implementation. If a second
backend is added in the future, the readiness conditions and bootstrap actions
should be defined in a separate backend-specific contract, and preflight
should route to the appropriate contract based on the campaign spec's
`remote_queue` configuration. This extensibility is out of scope for now.

## Backend readiness conditions

Preflight evaluates backend readiness through a set of checks. These checks
establish a **minimal ready state** — the minimum conditions under which
`ml-metaoptimization` can safely start its campaign loop and expect the
`remote_queue` contract to function.

### Minimal ready state (required before campaign start)

| Check | What it verifies | How verified |
|-------|-----------------|--------------|
| **Delegation prerequisites** | `hcloud` CLI authenticated, `config.env` populated, `ssh`/`rsync`/`jq` available | Delegate to `hetzner-delegation` prerequisite validation |
| **Head node reachable** | Cluster head is running and SSH-accessible | Delegate to `hetzner-delegation` cluster status check |
| **Queue infrastructure operational** | The `metaopt/` queue directories exist on the head node and queue commands respond | Invoke a no-op or status probe through the delegation layer (e.g., `get_batch_status.py` with a non-existent batch returns a well-formed error, not a crash) |
| **Queue commands available** | `enqueue_command`, `status_command`, `results_command` as declared in the campaign spec resolve to executable paths on the head node | Verify command availability through the delegation layer |
| **Network/credential validity** | SSH keys accepted, API tokens valid, private network functional | Implicit in head-reachability and delegation prerequisite checks |

All checks in this table must pass for the readiness artifact to emit
`status: "READY"`. Failure of any check produces `status: "FAILED"` with
an actionable `failures` entry.

### What is NOT part of minimal ready state

The following are **operational/capacity concerns** that belong to the
campaign runtime or to explicit scaling requests — not to preflight:

- **Worker count or autoscaling policy** — preflight does not verify that a
  specific number of workers are running. The head node is sufficient for
  queue readiness; worker scaling is a runtime concern managed by
  `hetzner-delegation` or the operator during the campaign.
- **GPU/resource availability** — preflight does not probe hardware resources
  beyond basic head reachability.
- **Queue drain state** — preflight does not check whether prior batches
  are still running or queued. Queue lifecycle is the orchestrator's concern.
- **Code sync freshness** — preflight may verify that sync *can* work, but
  does not push a specific code version. The orchestrator or delegation layer
  handles sync at experiment time.
- **Daemon process state** — preflight verifies that queue *commands* respond,
  not that `head_daemon.py` is actively running. The daemon is a runtime
  operational concern.

## Allowed bootstrap actions

When a readiness check fails due to a missing but provisionable prerequisite,
preflight MAY perform a bounded idempotent bootstrap action through the
delegation layer. All bootstrap actions must satisfy the constraints in
`references/boundary.md` § Bootstrap mutations.

| Condition | Bootstrap action | Delegation target |
|-----------|-----------------|-------------------|
| Head node not running | Request cluster bootstrap (build snapshot if needed, set up head) | `hetzner-delegation` cluster bootstrap flow |
| Queue directories missing on head | Request queue infrastructure setup | `hetzner-delegation` → `ray-hetzner` queue setup |
| `config.env` incomplete but derivable | Populate missing fields from environment/defaults | Local file operation (no delegation needed) |

### Bootstrap constraints

- **Idempotent.** Re-running a bootstrap action against an already-ready
  backend is a no-op.
- **Delegation-mediated.** Bootstrap actions that touch remote infrastructure
  go through `hetzner-delegation`, never through raw `hcloud`/SSH.
- **Bounded.** Bootstrap does not add workers, tune autoscaling, modify
  experiment code, or alter campaign state. It brings infrastructure to
  minimal ready state only.
- **Fail-fast.** If a bootstrap action fails (e.g., `hcloud` auth invalid,
  snapshot build error), preflight records the failure and emits
  `status: "FAILED"` — it does not retry.

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
  (e.g., "cluster bootstrapped via hetzner-delegation").

Freshness considerations: backend readiness is a **Tier 2 (operational)**
signal — it reflects a point-in-time check that cannot be re-verified by
hash comparison alone. If the orchestrator suspects backend state has changed
since preflight ran, re-invocation is the correct response.
See `references/readiness-artifact.md` § Freshness tiers.

## Out of scope

The following topics are explicitly outside this contract:

| Topic | Where it belongs |
|-------|-----------------|
| Raw Hetzner server administration (firewall rules, DNS, billing) | Operator / `hcloud` directly |
| Detailed cluster lifecycle management (add/remove workers, autoscaling) | `hetzner-delegation` at campaign runtime |
| Experiment execution, result collection, batch monitoring | `ml-metaoptimization` via `remote_queue` contract |
| Repository setup and validation (file structure, dependencies, campaign file) | `references/repo-setup.md` |
| Full readiness check catalog with exact check IDs | Future check-catalog reference |
| Failure taxonomy and retry semantics | `references/readiness-artifact.md` for artifact schema; `ml-metaoptimization` for retry policy |
| Second backend implementations | Future extensibility; one backend path for now |

## References

- `references/boundary.md` — ownership boundary, lifecycle phases, mutation constraints
- `references/readiness-artifact.md` — artifact schema, freshness tiers, consumption protocol
- `hetzner-delegation/SKILL.md` — delegation skill contract and cluster lifecycle
- `ray-hetzner/README.md` — execution backend, queue infrastructure, command reference
- `ml-metaoptimization/references/backend-contract.md` — orchestrator's `remote_queue` contract
