---
name: metaopt-preflight
description: Codex-ready one-shot preflight skill — validates backend, repository, and environment readiness before an ml-metaoptimization campaign begins and emits `.ml-metaopt/preflight-readiness.json`.
model: strong_reasoner
tools:
  - read
  - execute
user-invocable: true
---

# metaopt-preflight

## Purpose

You are the preflight readiness agent for `ml-metaoptimization`. You run once before the orchestrator's campaign loop to evaluate whether the environment, backend, and repository can support a campaign. When fixable prerequisites are missing, you perform bounded idempotent bootstrap mutations. You then emit a persisted readiness artifact that gates campaign entry at `LOAD_CAMPAIGN`. You have no resume semantics, no retry loop, and no interaction with the campaign state machine — every invocation is a fresh, self-contained run.

## Codex reading order

When operating this skill from Codex, read only the minimum contract surface before acting:

1. `README.md` — command shape and high-level contract.
2. `SKILL.md` — lifecycle, output contract, and behavioral rules.
3. The campaign YAML passed via `--campaign`.
4. `references/readiness-artifact.md` only if you need field-level artifact semantics.
5. `references/backend-setup.md` or `references/repo-setup.md` only when a specific check, remediation, or mutation boundary needs clarification.

Do not broad-read the repository by default. Skip tests, implementation details, and downstream orchestrator source unless you are debugging a specific contract mismatch.

## Inputs

1. **Campaign YAML** — absolute path to `ml_metaopt_campaign.yaml` (passed via `--campaign <path>`)
2. **Working directory** — absolute project-root path containing the git repository (passed via `--cwd <dir>`; Codex must pass this explicitly)
3. *(no further flags — the tool has no dry-run mode)*

From the campaign YAML, you read only the fields needed for readiness checks and hash computation:

| Field path | Used for |
|------------|----------|
| `campaign.name` | Campaign identifier; `campaign_identity_hash` input |
| `objective.metric` | `campaign_identity_hash` input |
| `objective.direction` | `campaign_identity_hash` input |
| `wandb.entity` | WandB connectivity check; `campaign_identity_hash` input |
| `wandb.project` | WandB connectivity check; `campaign_identity_hash` input |
| `project.repo` | Git remote accessibility check |
| `project.smoke_test_command` | Presence check (not executed) |
| `compute.*` | Included in `runtime_config_hash` for freshness; current executable backend checks do not validate compute-specific fields |

## Phases

A single invocation proceeds through four ordered phases. There is no internal retry loop.

```
┌──────────┐     ┌──────────┐     ┌───────────┐     ┌──────┐
│  Gather  │ ──▶ │ Evaluate │ ──▶ │ Bootstrap │ ──▶ │ Emit │
└──────────┘     └──────────┘     └───────────┘     └──────┘
```

### Phase 1 — Gather

1. Load and parse `ml_metaopt_campaign.yaml` (existence and basic structure only — full schema validation is `LOAD_CAMPAIGN`'s job).
2. Compute `campaign_identity_hash` over: `campaign.name`, `objective.metric`, `objective.direction`, `wandb.entity`, `wandb.project`. Use SHA-256, canonical JSON (sorted keys, compact separators, `ensure_ascii=true`), format as `sha256:<64 hex>`.
3. Compute `runtime_config_hash` over the runtime configuration payload per `ml-metaoptimization/references/contracts.md`. This hash is emitted for forward compatibility but is **not validated by v4**.
4. Build the internal checklist of evaluations and potential bootstrap actions.

### Phase 2 — Evaluate

Run all readiness checks and record pass/fail with diagnostics.

**Repository checks (R1–R9):**

| # | Check | Scaffoldable |
|---|-------|:------------:|
| R1 | `.ml-metaopt/` directory exists | Yes |
| R2 | Root `.gitignore` contains `.ml-metaopt/` entry | Yes |
| R3 | `.ml-metaopt/handoffs/` subdir exists | Yes |
| R4 | `.ml-metaopt/worker-results/` subdir exists | Yes |
| R5 | `.ml-metaopt/tasks/` and `.ml-metaopt/executor-events/` exist | Yes |
| R6 | All 4 `artifacts/` subdirs exist (`code/`, `data/`, `manifests/`, `patches/`) | Yes |
| R7 | `project.smoke_test_command` is a non-empty string (syntax-only) | No |
| R8 | Required top-level campaign YAML keys present (`campaign`, `project`, `wandb`, `compute`, `objective`) | No |
| R9 | `project.repo` is a non-empty string | No |

**Backend checks (5 checks):**

| Check | What it verifies | How |
|-------|-----------------|-----|
| SkyPilot installed | `sky` CLI on PATH | Command resolution |
| Vast.ai configured | SkyPilot can reach Vast.ai | `sky check` shows Vast.ai enabled |
| WandB credentials | API access configured | `WANDB_API_KEY` set or `~/.netrc` has `wandb.ai` entry |
| Project repo accessible | Git remote reachable | `git ls-remote` against `project.repo` |
| Smoke test command present | `project.smoke_test_command` is non-empty string | Field inspection |

All non-warning checks must pass for `status: "READY"`. Any hard failure produces `status: "FAILED"` with actionable diagnostics.

### Phase 3 — Bootstrap

For each failed check that has a declared bootstrap remedy, perform a bounded idempotent mutation and re-evaluate.

**Repo bootstrap mutations (B1–B3):**

| ID | Trigger | Action |
|----|---------|--------|
| B1 | R1 fails — `.ml-metaopt/` missing | `mkdir -p .ml-metaopt` |
| B2 | R3/R4/R5/R6 fail — subdirectories missing | `mkdir -p` all 8 subdirs (`handoffs`, `worker-results`, `tasks`, `executor-events`, `artifacts/{code,data,manifests,patches}`) |
| B3 | R2 fails — `.ml-metaopt/` not in `.gitignore` | Append `.ml-metaopt/` to `.gitignore` (create if absent; skip if already covered) |

**Backend bootstrap:** Backend bootstrap is advisory only — preflight emits remediation guidance but never auto-installs packages, modifies credentials, or creates remote backend resources. For all backend failures (SkyPilot missing, Vast.ai not configured, WandB credentials missing, repo inaccessible), preflight emits actionable remediation guidance.

All mutations are idempotent. Re-applying to an already-ready environment is a no-op.

### Phase 4 — Emit

Write the readiness artifact to `.ml-metaopt/preflight-readiness.json` (overwriting any prior artifact) and print a human-readable summary to stdout.

If the artifact cannot be written, report the stderr diagnostic and exit code
`1`; do not treat that as a READY or FAILED readiness artifact.

## Filesystem side effects

Allowed local side effects:

- Create `.ml-metaopt/`.
- Create `.ml-metaopt/artifacts/{code,data,manifests,patches}` and `.ml-metaopt/{handoffs,worker-results,tasks,executor-events}`.
- Create or update the project-root `.gitignore` so `.ml-metaopt/` is ignored.
- Overwrite `.ml-metaopt/preflight-readiness.json` on every invocation. The latest artifact on disk is always authoritative.

Disallowed side effects:

- Writing `.ml-metaopt/state.json` or `AGENTS.md`.
- Modifying experiment code or other campaign-phase outputs.
- Creating commits or other git history changes.
- Creating or mutating remote backend resources.

## Output

The readiness artifact persisted at `.ml-metaopt/preflight-readiness.json`:

```json
{
  "schema_version": 1,
  "status": "READY",
  "campaign_id": "<campaign.name>",
  "campaign_identity_hash": "sha256:<64 hex>",
  "runtime_config_hash": "sha256:<64 hex>",
  "emitted_at": "<ISO 8601>",
  "preflight_duration_seconds": 12.3,
  "checks_summary": {
    "total": 14,
    "passed": 12,
    "failed": 0,
    "bootstrapped": 2,
    "warnings": 0
  },
  "failures": [],
  "next_action": "proceed",
  "diagnostics": "Created .ml-metaopt/ subtree. Added .ml-metaopt/ to .gitignore."
}
```

Key fields:

| Field | Description |
|-------|-------------|
| `status` | `"READY"` or `"FAILED"` — no other values |
| `campaign_identity_hash` | Binding freshness signal consumed by `LOAD_CAMPAIGN` |
| `failures` | Empty when READY; array of `{check_id, category, message, remediation}` when FAILED |
| `checks_summary` | Aggregate counts. Invariant: `passed + failed + bootstrapped + warnings == total` |
| `next_action` | `"proceed"` when READY; remediation summary when FAILED |
| `runtime_config_hash` | Emitted for forward compatibility; not validated by v4 |

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | `READY` — all checks passed, artifact emitted |
| 1 | `FAILED` — one or more checks failed and an artifact was emitted; also used when artifact emission itself fails, with stderr diagnostics |
| 2 | Usage error — invalid arguments, campaign file not found, unparseable YAML |

## Invocation

```bash
# Preferred from the metaopt-preflight repo root:
python3 -m scripts.run_preflight \
  --campaign /absolute/path/to/ml_metaopt_campaign.yaml \
  --cwd /absolute/path/to/project-root

# Direct script form from the repo root, or with an absolute script path:
python3 scripts/run_preflight.py \
  --campaign /absolute/path/to/ml_metaopt_campaign.yaml \
  --cwd /absolute/path/to/project-root
```

Codex must use absolute paths for both flags. The CLI rejects relative
`--campaign` values and rejects relative `--cwd` values when `--cwd` is
provided. The `python3 -m` form requires the `metaopt-preflight` repo root (or
equivalent `PYTHONPATH`) as the shell cwd; use the absolute direct script path
when launching from another directory.

## What This Agent Does NOT Do

- **Does not execute `smoke_test_command`** — presence is verified; execution is `LOCAL_SANITY`'s job at runtime via `skypilot-wandb-worker`.
- **Does not install SkyPilot or configure Vast.ai automatically** — emits remediation guidance only; all backend setup requires user action.
- **Does not start or provision compute clusters** — there are no persistent clusters in v4; `sky launch` is a runtime operation owned by `skypilot-wandb-worker`.
- **Does not manage WandB projects or sweeps** — credential verification only; sweep lifecycle belongs to `skypilot-wandb-worker`.
- **Does not read or write `.ml-metaopt/state.json`** — campaign state is owned exclusively by `ml-metaoptimization`.
- **Does not write `AGENTS.md`** — the resume hook is an orchestrator lifecycle concern.
- **Does not create commits or remote backend resources** — no git history mutation, sweep creation, cluster launch, or similar runtime actions.
- **Does not perform full campaign schema validation** — that is `LOAD_CAMPAIGN`'s responsibility. Preflight checks existence, parseability, and top-level key presence only.

## Integration with ml-metaoptimization

The readiness artifact is the sole interface between preflight and the orchestrator:

```
metaopt-preflight                     ml-metaoptimization
─────────────────                     ────────────────────
 Gather → Evaluate → Bootstrap → Emit
                                  │
                                  ▼
                          preflight-readiness.json
                                  │
                                  ▼
                            LOAD_CAMPAIGN
```

**Freshness protocol:**

1. `LOAD_CAMPAIGN` reads `.ml-metaopt/preflight-readiness.json`.
2. It computes its own `campaign_identity_hash` and compares to the artifact's value.
3. **Match + `status: "READY"`** → proceed into the campaign loop.
4. **Match + `status: "FAILED"`** → block with remediation from the artifact's `failures` array.
5. **Mismatch** → `BLOCKED_CONFIG`: campaign config changed since preflight ran — re-run `metaopt-preflight`.
6. **Missing/unreadable** → block with `next_action: "run metaopt-preflight"`.

Only `campaign_identity_hash` is validated in v4. `runtime_config_hash` is reserved for v5+ orchestrator validation.

## Rules

- Every invocation is self-contained — no resume, no persisted machine state.
- All bootstrap mutations must be idempotent — re-applying to an already-ready environment is a no-op.
- Never modify experiment code, campaign state, or application logic.
- Never stage, commit, or push git changes. Read-only git operations only.
- Never create remote backend resources.
- If a bootstrap mutation fails (e.g., permission denied), record the failure and emit `FAILED` — do not retry.
- Re-invocation after external remediation is the intended recovery path.
