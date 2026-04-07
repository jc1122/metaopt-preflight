# Ownership Boundary and Lifecycle

This is the authoritative reference for what `metaopt-preflight` owns, what it
explicitly does not own, and how a single invocation proceeds. All other
project docs (SKILL.md, README.md) must remain consistent with this document.

## Design rationale

`ml-metaoptimization` is a resumable deterministic state machine. Its entry
point (`LOAD_CAMPAIGN`) assumes the environment is already viable — backend
reachable, repository structure present, delegation infrastructure provisioned.
If those prerequisites are not met, the orchestrator transitions to
`BLOCKED_CONFIG` and halts, leaving the user to diagnose and fix the
environment manually.

`metaopt-preflight` exists to close that gap. It is a dedicated, separately
invocable skill that:

1. **Evaluates** whether the environment meets campaign prerequisites.
2. **Bootstraps** missing but provisionable prerequisites via bounded
   idempotent mutations.
3. **Signals** readiness (or actionable failure) through a persisted artifact
   that the orchestrator can gate on.

This keeps the orchestrator's entry path clean and deterministic: it either
sees a valid readiness artifact and proceeds, or it does not and blocks.

## Ownership: what preflight owns

### 1. Environment and backend readiness evaluation

Preflight verifies that the runtime environment can support a campaign:

- Backend connectivity — can the queue backend be reached and respond to
  basic commands?
- Delegation infrastructure — is the remote compute layer functional?
- Runtime dependencies — are required tools, interpreters, and libraries
  available?
- Network and credential prerequisites — can required services be
  authenticated against?

### 2. Repository readiness evaluation

Preflight verifies that the target repository is in a state compatible with
`ml-metaoptimization`:

- Required file presence — does `ml_metaopt_campaign.yaml` exist and parse?
- Directory structure — is the expected layout present or creatable?
- Git state — is the repository clean enough for worktree operations?

### 3. Bounded bootstrap mutations

When readiness checks fail due to missing but provisionable prerequisites,
preflight may perform **bounded idempotent mutations** to bring the
environment to a ready state. Examples include:

- Provisioning or verifying delegation/backend infrastructure
- Scaffolding the `.ml-metaopt/` directory structure
- Executing declared repo-preparation steps from the campaign spec

All bootstrap mutations must satisfy:

- **Idempotent** — re-applying a mutation to an already-ready environment is
  a safe no-op.
- **Bounded** — mutations are limited to environment/infrastructure setup.
  They must not modify experiment code, campaign state, or application logic.
- **Declared** — each mutation category will be enumerated in the detailed
  backend setup contract and repo setup contract (later tasks).

### 4. Persisted readiness signal

Preflight produces a readiness artifact that persists on disk. This artifact:

- Encodes a clear pass/fail signal.
- Includes actionable diagnostics on failure.
- Is consumed by `ml-metaoptimization` to gate campaign entry.
- Is overwritten on each preflight invocation (the latest is authoritative).

The detailed readiness artifact schema is defined in
`references/readiness-artifact.md`.

## Ownership: what preflight does NOT own

| Concern | Owner | Why it's excluded |
|---------|-------|-------------------|
| Campaign state machine (`LOAD_CAMPAIGN` → `COMPLETE`) | `ml-metaoptimization` | Preflight is one-shot; the resumable loop is the orchestrator's core |
| `.ml-metaopt/state.json` | `ml-metaoptimization` | Campaign state is created and managed exclusively by the orchestrator |
| `AGENTS.md` resume hook | `ml-metaoptimization` | The hook is an orchestrator lifecycle concern |
| Proposal lifecycle (ideation, selection, design, rollover) | `ml-metaoptimization` | These are campaign-phase operations |
| Experiment materialization (code changes, worktrees, patches) | `ml-metaoptimization` | Experiment-specific code changes are outside preflight scope |
| Local sanity and remote execution | `ml-metaoptimization` | Runtime execution belongs to the campaign loop |
| Result analysis and iteration scoring | `ml-metaoptimization` | Post-experiment analysis is an orchestrator concern |
| Worker/subagent dispatch | `ml-metaoptimization` | Preflight does not manage background or auxiliary workers |
| Campaign input validation (schema, sentinel detection) | `ml-metaoptimization` (`LOAD_CAMPAIGN`) | The orchestrator validates campaign semantics; preflight only checks that the file exists and parses |

## Lifecycle of a single invocation

Preflight runs exactly once per invocation and proceeds through four ordered
phases. There is no internal retry loop and no persisted machine state.

```
┌──────────┐     ┌──────────┐     ┌───────────┐     ┌──────┐
│  Gather  │ ──▶ │ Evaluate │ ──▶ │ Bootstrap │ ──▶ │ Emit │
└──────────┘     └──────────┘     └───────────┘     └──────┘
                                        │
                                        ▼
                                  re-evaluate
                                  affected checks
```

### Phase 1 — Gather

Read configuration sources to determine the scope of readiness checks:

- Parse `ml_metaopt_campaign.yaml` (existence and basic structure only — full
  schema validation is `LOAD_CAMPAIGN`'s job).
- Read backend declarations from the campaign spec.
- Inspect the environment for runtime tool availability.

Output: an internal checklist of evaluations and potential bootstrap actions.

### Phase 2 — Evaluate

Run each readiness check and record pass/fail with diagnostics:

- Backend reachability (e.g., connectivity probe against declared commands).
- Repository structure checks.
- Environment dependency checks.

Output: a checklist with pass/fail results and failure diagnostics.

### Phase 3 — Bootstrap

For each failed check that has a declared bootstrap remedy:

1. Execute the bounded idempotent mutation.
2. Re-evaluate the affected check.
3. Record whether the bootstrap succeeded.

Checks that fail without a bootstrap remedy remain as failures in the final
result. Bootstrap is optional — if all checks pass in Phase 2, this phase is
a no-op.

Output: updated checklist with post-bootstrap results.

### Phase 4 — Emit

Produce the persisted readiness artifact:

- **Pass:** all checks passed (possibly after bootstrap). The artifact
  confirms readiness for `ml-metaoptimization`.
- **Fail:** one or more checks remain failed. The artifact contains
  actionable diagnostics for each failure.

The skill exits after this phase regardless of outcome.

## Idempotency guarantees

| Property | Guarantee |
|----------|-----------|
| Evaluation | Stateless — always evaluates from scratch, never reads prior artifacts to decide behavior |
| Bootstrap mutations | Individually idempotent — applying to an already-ready environment is a no-op |
| Readiness artifact | Overwritten on each run — latest is authoritative |
| Campaign state | Never touched — preflight does not read or write `.ml-metaopt/state.json` |
| Side effects | Limited to bootstrap mutations and the readiness artifact |

Re-invocation after external remediation or environment changes is the
intended recovery path. There is no "resume" — every invocation is a fresh
run.

## Integration point with ml-metaoptimization

The readiness artifact is the sole interface between the two skills:

```
metaopt-preflight                     ml-metaoptimization
─────────────────                     ────────────────────
 Gather → Evaluate → Bootstrap → Emit
                                  │
                                  ▼
                          readiness artifact
                          (persisted on disk)
                                  │
                                  ▼
                            LOAD_CAMPAIGN
                                  │
                                  ▼
                            HYDRATE_STATE
                                  │
                                  ▼
                              … loop …
```

- Preflight produces the artifact; the orchestrator consumes it.
- The orchestrator never invokes preflight.
- Preflight never invokes the orchestrator.
- There is no runtime coupling beyond the artifact file.

## Deferred specifications

The following are referenced in this document but intentionally deferred to
later tasks:

| Topic | Deferred to |
|-------|-------------|
| Readiness artifact schema (fields, format, versioning) | `references/readiness-artifact.md` (**defined**) |
| Backend setup contract (which bootstrap mutations are allowed, how backend readiness is probed) | Backend setup contract task |
| Repo setup contract (which repository mutations are allowed, structural requirements) | Repo setup contract task |
| Input contract (what configuration preflight reads and how) | Input contract task |
| Detailed check catalog (enumerated readiness checks) | Implementation task |

These will be defined as refinements of the boundary established here.
