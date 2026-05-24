# Repository Setup Contract

Authoritative reference for how `metaopt-preflight` evaluates and bootstraps
repository readiness before an `ml-metaoptimization` campaign begins.

For preflight ownership and lifecycle, see `references/boundary.md`.
For the readiness artifact schema, see `references/readiness-artifact.md`.
For backend setup, see `references/backend-setup.md`.

---

## Ownership model

Repository setup spans two skills with distinct responsibilities. Preflight
prepares the repo to the point where the orchestrator can start; the
orchestrator owns everything from campaign entry onward.

| Layer | Role in repo setup |
|-------|-------------------|
| **`metaopt-preflight`** | Evaluates structural readiness. Performs bounded idempotent scaffolding. Emits repo-related check results into the readiness artifact. |
| **`ml-metaoptimization`** | Owns all campaign-phase repo mutations: `state.json` creation, `AGENTS.md` hook, worktrees, patches, artifact packaging, code changes. Validates campaign semantics during `LOAD_CAMPAIGN`. |

**Key principle:** preflight ensures the repo is *structurally ready* for the
orchestrator to begin. It does not perform semantic validation of campaign
content, experiment code, or application logic.

---

## Current repo ready state (R1-R9)

The current implementation in `scripts/checks/repo_checks.py` defines repo
readiness as nine concrete checks. Preflight evaluates them in order and may
bootstrap only the ones marked scaffoldable.

### Required conditions

| # | Condition | Scaffoldable | Verification method |
|---|-----------|:------------:|---------------------|
| R1 | `.ml-metaopt/` directory exists | **Yes** | `{project_root}/.ml-metaopt/` is a directory |
| R2 | Root `.gitignore` excludes `.ml-metaopt/` | **Yes** | `{project_root}/.gitignore` exists and contains one of `.ml-metaopt/`, `.ml-metaopt`, or `.ml-metaopt/*` |
| R3 | `.ml-metaopt/handoffs/` exists | **Yes** | `{project_root}/.ml-metaopt/handoffs/` is a directory |
| R4 | `.ml-metaopt/worker-results/` exists | **Yes** | `{project_root}/.ml-metaopt/worker-results/` is a directory |
| R5 | `.ml-metaopt/tasks/` and `.ml-metaopt/executor-events/` exist | **Yes** | Both directories exist under `{project_root}/.ml-metaopt/` |
| R6 | `.ml-metaopt/artifacts/{code,data,manifests,patches}/` all exist | **Yes** | All four artifact subdirectories exist under `{project_root}/.ml-metaopt/artifacts/` |
| R7 | `project.smoke_test_command` is present and non-empty | No | `project` exists and `project.smoke_test_command` is a non-empty string. Preflight does not execute it. |
| R8 | Required top-level campaign keys are present | No | Top-level keys `campaign`, `project`, `wandb`, `compute`, and `objective` are all present. This is presence-only, not deep schema validation. |
| R9 | `project.repo` is present and non-empty | No | `project` exists and `project.repo` is a non-empty string |

### What "required top-level keys" means (R8)

R8 is intentionally shallow. It checks only for the presence of these five
top-level keys:

- `campaign`
- `project`
- `wandb`
- `compute`
- `objective`

It does **not** require a top-level `campaign_id` or `campaign_name`.
`scripts/run_preflight.py` derives the emitted readiness-artifact
`campaign_id` from `campaign.name`, with flat `campaign_name` retained only
as a runner fallback when `campaign.name` is absent. That extraction behavior
is separate from repo readiness and does not change the R8 contract.

### Smoke test command scope (R7)

R7 checks only that `project.smoke_test_command` is a non-empty string.
Preflight does **not** execute the command and does not validate whether it
is runnable in the local shell, container, or backend environment. Runtime
execution belongs to downstream phases, and backend-side command availability
is covered by `references/backend-setup.md`.

### Legacy or deferred items from older contract drafts

Older drafts of this reference described additional repo checks that are **not
part of the current R1-R9 implementation**:

- Git repository detection and merge/rebase hygiene are not currently checked
  by `scripts/checks/repo_checks.py`.
- Campaign file discovery and YAML parseability are handled before repo checks
  run; they are not numbered repo checks.
- Dataset-path existence is not checked by the current repo checks.

Keep those topics out of the R1-R9 table unless the implementation changes and
the contract is updated with matching tests.

---

## Allowed bootstrap mutations

When a scaffoldable condition fails, preflight may perform a bounded
idempotent mutation to satisfy it. All mutations must conform to the
constraints in `references/boundary.md` § Bootstrap mutations.

### Mutation catalog

| ID | Trigger | Action | Idempotency |
|----|---------|--------|-------------|
| B1 | `.ml-metaopt/` directory missing (R1 fails) | `mkdir -p .ml-metaopt` | Creating an existing directory is a no-op |
| B2 | Required `.ml-metaopt/` subdirectories missing (R3-R6 fail) | `mkdir -p .ml-metaopt/artifacts/{code,data,manifests,patches} .ml-metaopt/{handoffs,worker-results,tasks,executor-events}` | Creating existing directories is a no-op |
| B3 | Root `.gitignore` missing or lacks a valid `.ml-metaopt` exclude rule (R2 fails) | Create `.gitignore` if needed, or append `.ml-metaopt/` in the project root | Re-appending a covered rule is skipped; `.ml-metaopt/`, `.ml-metaopt`, and `.ml-metaopt/*` all count as already covered |

### Bootstrap constraints

- **Idempotent.** Re-running any mutation against an already-ready repo is a
  no-op.
- **Directory-only.** Preflight creates directories and modifies `.gitignore`
  only. It does not create, modify, or delete any files inside `.ml-metaopt/`
  other than the readiness artifact (which is always written in the Emit
  phase, not as a bootstrap mutation).
- **No file content.** Preflight does not write `state.json`, `AGENTS.md`,
  or any artifact content. Those are owned by `ml-metaoptimization`.
- **No git operations.** Preflight does not stage, commit, or push. It reads
  git state but does not modify git history.
- **Fail-fast.** If a bootstrap mutation fails (e.g., permission denied),
  preflight records the failure and emits `status: "FAILED"` — it does not
  retry.

After bootstrap, preflight re-evaluates the affected readiness checks. If
they now pass, the bootstrap is considered successful and is reflected in
`checks_summary.bootstrapped`.

---

## Orchestrator-owned repo concerns (NOT preflight's job)

The following repo-level operations belong exclusively to
`ml-metaoptimization`. Preflight must never perform them.

| Concern | Owner | Reference |
|---------|-------|-----------|
| Creating `.ml-metaopt/state.json` | `ml-metaoptimization` (`HYDRATE_STATE`) | `references/contracts.md` |
| Creating or modifying `AGENTS.md` resume hook | `ml-metaoptimization` | `SKILL.md` § Required Files |
| Creating and removing git worktrees | `ml-metaoptimization` (`MATERIALIZE_CHANGESET`) | `SKILL.md` § Orchestrator Actions |
| Applying patches and resolving merge conflicts | `ml-metaoptimization` | `SKILL.md` § Orchestrator Actions |
| Packaging immutable code/data artifacts | `ml-metaoptimization` (`ENQUEUE_REMOTE_BATCH`) | `references/contracts.md` |
| Writing batch manifests | `ml-metaoptimization` | `references/contracts.md` |
| Campaign schema/sentinel validation | `ml-metaoptimization` (`LOAD_CAMPAIGN`) | `references/contracts.md` |
| Experiment code changes | `ml-metaoptimization` (via `metaopt-materialization-worker`) | `references/worker-lanes.md` |

---

## Integration with the readiness artifact

Repo checks map to the readiness artifact as follows:

- **`checks_summary.total`** includes all repo checks evaluated. The current
  repo contract contributes 9 checks.
- **`checks_summary.passed`** / **`failed`** reflect final post-bootstrap
  results.
- **`checks_summary.bootstrapped`** counts checks that failed initially but
  passed after a scaffold mutation.
- **`failures[]`** entries for repo checks use `category: "repo"` and
  include `check_id`, a human-readable `message`, and a `remediation` hint.
- **`diagnostics`** may include notes on scaffold actions taken
  (e.g., "created `.ml-metaopt/artifacts/` subtree",
  "added `.ml-metaopt/` to `.gitignore`").

The campaign identity and runtime config hashes embedded in the readiness
artifact are computed using the canonicalization rules defined in
`ml-metaoptimization/references/contracts.md`. Preflight does not define its
own identity scheme.

Freshness considerations: the campaign fields used by repo checks R7-R9 are
partly covered by binding hashes, but local scaffold state is operational. If
`.ml-metaopt/` directories or `.gitignore` change after the artifact is
emitted, the artifact can become operationally stale without a campaign hash
change. Git operation state and dataset file presence are not current repo
checks.

---

## Out of scope

The following topics are explicitly outside this contract:

| Topic | Where it belongs |
|-------|-----------------|
| Full campaign schema validation (field values, sentinel detection) | `ml-metaoptimization` (`LOAD_CAMPAIGN`) |
| Backend connectivity and queue readiness | `references/backend-setup.md` |
| Runtime dependency checks (interpreters, libraries, tools) | Future environment-checks reference |
| Detailed check IDs and pass/fail criteria beyond R1-R9 | Future check-catalog reference |
| Preflight input contract (campaign path discovery, YAML load errors) | CLI input handling, not repo checks |
| Git repository detection and repo-operation hygiene | Deferred unless repo checks grow to cover it |
| Dataset path existence validation | Deferred unless repo checks grow to cover it |
| Code quality or test suite validation | Not planned - not a preflight concern |
| Execution of smoke test commands | `ml-metaoptimization` (`LOCAL_SANITY`) |
| Verification of remote/container-side paths | `references/backend-setup.md` for backend paths; `LOAD_CAMPAIGN` for command validation |

---

## References

- `references/boundary.md` — ownership boundary, lifecycle phases, mutation constraints
- `references/readiness-artifact.md` — artifact schema, freshness tiers, consumption protocol
- `references/backend-setup.md` — backend setup contract, readiness conditions, bootstrap actions
- `ml-metaoptimization/SKILL.md` — orchestrator contract, required files, orchestrator actions
- `ml-metaoptimization/references/contracts.md` — campaign spec schema, state file, identity hashes
- `ml-metaoptimization/references/dependencies.md` — orchestrator runtime dependencies
