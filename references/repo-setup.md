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

## Prerequisite: the target project must be a git repository

Preflight **requires** that the target project already be a git repository
with at least one commit. It does not run `git init` or create initial
commits.

**Rationale:** `ml-metaoptimization` depends on git worktrees, which require
a repository with history. Initializing git in an arbitrary directory is a
destructive assumption that does not belong in a readiness check.

If the target directory is not a git repository, preflight emits
`status: "FAILED"` with a remediation message directing the user to
initialize the repository themselves.

---

## Minimal repo ready state

These conditions must all hold before the orchestrator can start its campaign
loop. Preflight evaluates each one and may bootstrap those marked as
scaffoldable.

### Required conditions

| # | Condition | Scaffoldable | Verification method |
|---|-----------|:------------:|---------------------|
| R1 | Target directory is a git repository with ≥1 commit | No | `git rev-parse --git-dir` succeeds and `git rev-list -1 HEAD` succeeds |
| R2 | `ml_metaopt_campaign.yaml` exists and is parseable YAML | No | File exists at `{project_root}/ml_metaopt_campaign.yaml` and parses without error |
| R3 | Campaign file has basic structure (required top-level keys present) | No | Top-level keys `version`, `campaign_id`, `objective`, `datasets`, `sanity`, `artifacts`, `remote_queue`, `execution` are present. No deep value validation — that is `LOAD_CAMPAIGN`'s job. |
| R4 | `.ml-metaopt/` directory exists | **Yes** | Directory exists at `{project_root}/.ml-metaopt/` |
| R5 | `.ml-metaopt/artifacts/` subtree exists (`code/`, `data/`, `manifests/`, `patches/`) | **Yes** | All four subdirectories exist under `.ml-metaopt/artifacts/` |
| R6 | Dataset paths declared in campaign spec exist (local paths only) | No | For each `datasets[].local_path`, verify the file exists. Paths are relative to project root. |
| R7 | Sanity command is syntactically non-empty | No | `sanity.command` is a non-empty string. Preflight does not execute it. |
| R8 | Git working tree is in a clean-enough state for worktree operations | No | `git status --porcelain` output does not indicate uncommitted changes that would block worktree creation. Untracked files are acceptable. |
| R9 | `.ml-metaopt/` is git-ignored (or ignorable) | **Yes** | `.ml-metaopt` appears in an active gitignore rule. If not, preflight may add it. |

### What "basic structure" means (R3)

Preflight checks for the *presence* of required top-level keys, not for the
validity of their values. For example:

- ✅ `objective:` key exists → passes R3
- ❌ `objective:` key missing → fails R3
- ✅ `objective.metric: rmse` vs `objective.metric: mae` → not preflight's concern
- ❌ `objective.metric` contains a sentinel placeholder → not preflight's concern (caught by `LOAD_CAMPAIGN`)

This keeps the boundary clean: preflight confirms the campaign file is
structurally present and plausibly complete; the orchestrator validates
semantics.

### What "clean-enough" means (R8)

The orchestrator creates isolated worktrees for experiment materialization.
Worktree creation requires a resolvable HEAD and no conflicting index state.
Preflight checks:

- `HEAD` resolves to a valid commit.
- No merge/rebase in progress (`git status` does not report merge conflict state).
- The index is not locked (no `.git/index.lock`).

Untracked files and unstaged changes to tracked files do **not** block
worktree creation and are acceptable. Preflight does not require a fully
clean working tree.

### Command path note (R7, and remote_queue/execution paths)

Some paths in the campaign spec (e.g., `execution.entrypoint`,
`remote_queue.enqueue_command`) are **container-side or backend-side paths**
that do not resolve in the local repository. Preflight does not attempt to
verify that these paths exist locally.

Repo-level checks (R7) only confirm that command strings are non-empty and
syntactically present. Backend-side command availability (verifying that
queue commands resolve to executable paths on the head node) is a backend
readiness concern covered by `references/backend-setup.md` § Queue commands
available. Full command semantic validation is `LOAD_CAMPAIGN`'s
responsibility.

---

## Allowed bootstrap mutations

When a scaffoldable condition fails, preflight may perform a bounded
idempotent mutation to satisfy it. All mutations must conform to the
constraints in `references/boundary.md` § Bootstrap mutations.

### Mutation catalog

| ID | Trigger | Action | Idempotency |
|----|---------|--------|-------------|
| B1 | `.ml-metaopt/` directory missing (R4 fails) | `mkdir -p .ml-metaopt` | Creating an existing directory is a no-op |
| B2 | Artifact subdirectories missing (R5 fails) | `mkdir -p .ml-metaopt/artifacts/{code,data,manifests,patches}` | Creating existing directories is a no-op |
| B3 | `.ml-metaopt` not in gitignore (R9 fails) | Append `.ml-metaopt/` to the project-root `.gitignore` (create the file if absent) | Re-appending a line already present is skipped; only adds if not already covered by an existing rule |

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

- **`checks_summary.total`** includes all repo checks evaluated.
- **`checks_summary.passed`** / **`failed`** reflect final post-bootstrap
  results.
- **`checks_summary.bootstrapped`** counts checks that failed initially but
  passed after a scaffold mutation.
- **`failures[]`** entries for repo checks use `category: "repository"` and
  include `check_id`, a human-readable `message`, and a `remediation` hint.
- **`diagnostics`** may include notes on scaffold actions taken
  (e.g., "created `.ml-metaopt/artifacts/` subtree",
  "added `.ml-metaopt/` to `.gitignore`").

The campaign identity and runtime config hashes embedded in the readiness
artifact are computed using the canonicalization rules defined in
`ml-metaoptimization/references/contracts.md`. Preflight does not define its
own identity scheme.

Freshness considerations: repo structural readiness is primarily a
**Tier 1 (binding)** signal — if the campaign file changes, hash mismatches
will invalidate the artifact. However, some repo conditions (git cleanliness,
dataset file presence) are **Tier 2 (operational)** — they can change after
the artifact is emitted. See `references/readiness-artifact.md` § Freshness
tiers.

---

## Out of scope

The following topics are explicitly outside this contract:

| Topic | Where it belongs |
|-------|-----------------|
| Full campaign schema validation (field values, sentinel detection) | `ml-metaoptimization` (`LOAD_CAMPAIGN`) |
| Backend connectivity and queue readiness | `references/backend-setup.md` |
| Runtime dependency checks (interpreters, libraries, tools) | Future environment-checks reference |
| Detailed check IDs and pass/fail criteria | Future check-catalog reference |
| Preflight input contract (configuration sources) | Future input-contract reference |
| Deep semantic validation of dataset content | Not planned — preflight checks file presence only |
| Code quality or test suite validation | Not planned — not a preflight concern |
| Execution of sanity commands | `ml-metaoptimization` (`LOCAL_SANITY`) |
| Verification of remote/container-side paths | `references/backend-setup.md` for backend paths; `LOAD_CAMPAIGN` for command validation |

---

## References

- `references/boundary.md` — ownership boundary, lifecycle phases, mutation constraints
- `references/readiness-artifact.md` — artifact schema, freshness tiers, consumption protocol
- `references/backend-setup.md` — backend setup contract, readiness conditions, bootstrap actions
- `ml-metaoptimization/SKILL.md` — orchestrator contract, required files, orchestrator actions
- `ml-metaoptimization/references/contracts.md` — campaign spec schema, state file, identity hashes
- `ml-metaoptimization/references/dependencies.md` — orchestrator runtime dependencies
