# metaopt-preflight

Codex-usable, one-shot preflight for [ml-metaoptimization](https://github.com/jc1122/ml-metaoptimization) campaigns.

## What it does

Run this once before starting an `ml-metaoptimization` campaign. It evaluates
repository, backend, and environment readiness; may scaffold the local
`.ml-metaopt/` workspace when repo prerequisites are missing; and emits the
readiness artifact consumed by `LOAD_CAMPAIGN`.

This is a one-shot invocation with no resume path. Re-run it from scratch when
the environment changes or the campaign configuration changes.

## Prerequisites

- Python 3.10+
- PyYAML ≥ 6.0 (installed via `requirements.txt`)
- [ml-metaoptimization](https://github.com/jc1122/ml-metaoptimization) campaign YAML
- SkyPilot with Vast.ai provider — `pip install 'skypilot[vast]'`
- WandB credentials — `WANDB_API_KEY` env var or `wandb login`
- `git` on PATH

## Installation / usage

Codex command shape from the repo root:

```bash
# Clone and install deps (no pip install needed — it's a script)
git clone https://github.com/jc1122/metaopt-preflight
cd metaopt-preflight
pip install -r requirements.txt

# Run preflight from the metaopt-preflight repo root:
python3 -m scripts.run_preflight \
  --campaign /absolute/path/to/ml_metaopt_campaign.yaml \
  --cwd /absolute/path/to/project-root

# Direct script form from the repo root, or with an absolute script path:
python3 scripts/run_preflight.py \
  --campaign /absolute/path/to/ml_metaopt_campaign.yaml \
  --cwd /absolute/path/to/project-root
```

For Codex, always pass both flags explicitly with absolute paths. The CLI
rejects a relative `--campaign` and rejects a relative `--cwd` when `--cwd` is
provided. If `--cwd` is omitted, the current process directory is used; reserve
that form for local shell use where the working directory is already known.

The module form (`python3 -m scripts.run_preflight`) must be run from the
`metaopt-preflight` repo root or with an equivalent `PYTHONPATH`. The direct
script form can be called by absolute script path from any shell cwd.

`--campaign` points to the campaign YAML to parse. `--cwd` points to the target
project root where preflight evaluates readiness, may scaffold `.ml-metaopt/`,
and writes `.ml-metaopt/preflight-readiness.json`.

### CLI flags

| Flag | Required | Default | Description |
|------|----------|---------|-------------|
| `--campaign` | Yes | — | Path to the campaign YAML file that preflight parses |
| `--cwd` | No | current process directory | Project root directory where readiness is evaluated and the artifact is written; if provided, it must be absolute |

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | READY — proceed with `ml-metaoptimization` |
| 1 | FAILED — fix reported issues and re-run; if the readiness artifact cannot be written, the error is printed to stderr |
| 2 | Usage/input error — bad args, missing campaign file, or malformed YAML |

Exit code `2` returns before the Emit phase, so no readiness artifact is
written for usage/input failures.

## What gets checked

### Repository checks (R1–R9)

| Check | Description | Scaffoldable |
|-------|-------------|:------------:|
| R1 | `.ml-metaopt/` directory exists | Yes |
| R2 | `.gitignore` contains `.ml-metaopt/` entry | Yes |
| R3 | `.ml-metaopt/handoffs/` subdir exists | Yes |
| R4 | `.ml-metaopt/worker-results/` subdir exists | Yes |
| R5 | `.ml-metaopt/tasks/` and `executor-events/` exist | Yes |
| R6 | All `artifacts/` subdirs exist (`code/`, `data/`, `manifests/`, `patches/`) | Yes |
| R7 | `project.smoke_test_command` is a non-empty string | No |
| R8 | Required top-level campaign YAML keys present | No |
| R9 | `project.repo` is a non-empty string | No |

### Backend checks (advisory — not auto-fixed)

| Check | Description |
|-------|-------------|
| `skypilot_installed` | `sky` CLI on PATH |
| `vast_configured` | Vast.ai enabled in SkyPilot (`sky check`) |
| `wandb_credentials` | `WANDB_API_KEY` set or `~/.netrc` has `api.wandb.ai` |
| `repo_access` | `git ls-remote` succeeds against `project.repo` |
| `smoke_test_command_nonempty` | `project.smoke_test_command` is non-empty (warning) |

## Filesystem effects and bootstrap

Repo bootstrap mutations (B1–B3) are auto-applied for fixable issues:

| ID | Trigger | Action |
|----|---------|--------|
| B1 | R1 fails | `mkdir -p .ml-metaopt` |
| B2 | R3–R6 fail | `mkdir -p` all 8 required subdirectories |
| B3 | R2 fails | Append `.ml-metaopt/` to `.gitignore` |

Current executable behavior keeps backend bootstrap advisory only: backend
failures produce remediation guidance in the emitted result, but the CLI does
not auto-install packages, mutate credentials, create remote backend resources,
or start runtime workers.

Preflight may:

- create `.ml-metaopt/` scaffolding under `--cwd`
- create or append the root `.gitignore` entry for `.ml-metaopt/`
- overwrite `.ml-metaopt/preflight-readiness.json` on each READY or FAILED run

Preflight must not write `.ml-metaopt/state.json`, `AGENTS.md`, experiment
code, commits, or remote backend resources.

All supported mutations are idempotent. The latest emitted readiness artifact
on disk is always authoritative.

## Output artifact

Written to `.ml-metaopt/preflight-readiness.json`:

```json
{
  "schema_version": 1,
  "status": "READY",
  "campaign_id": "my-campaign",
  "campaign_identity_hash": "sha256:…",
  "runtime_config_hash": "sha256:…",
  "emitted_at": "2025-01-15T12:00:00Z",
  "preflight_duration_seconds": 4.2,
  "checks_summary": { "total": 14, "passed": 12, "failed": 0, "bootstrapped": 2, "warnings": 0 },
  "failures": [],
  "next_action": "proceed",
  "diagnostics": "Created .ml-metaopt/ subtree."
}
```

Key fields: `status` (`READY` | `FAILED`), `campaign_identity_hash`,
`failures` (empty when READY), `next_action` (`proceed` or a short fix summary
derived from the remaining failures).

`checks_summary` counters:

| Field | Meaning |
|-------|---------|
| `total` | Number of checks evaluated |
| `passed` | Passed on initial evaluation |
| `failed` | Still failing after bootstrap |
| `bootstrapped` | Initially failed, fixed by bootstrap |
| `warnings` | Advisory issues that don't block readiness |

Invariant: `passed + failed + bootstrapped + warnings == total`.

Every preflight invocation that reaches Emit overwrites any previous
artifact at the same path. There is no append log and no resume state.

## Integration with ml-metaoptimization

The readiness artifact is the sole interface between the two projects.

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

- Re-run preflight whenever campaign config changes.
- `LOAD_CAMPAIGN` computes its own `campaign_identity_hash` and compares it
  to the artifact. If they don't match → `BLOCKED_CONFIG`.
- A `FAILED` artifact with matching hashes still blocks — the environment
  isn't ready.
- `runtime_config_hash` is emitted for forward compatibility, but v4 validates
  only `campaign_identity_hash` at campaign entry.

## Validation

```bash
python3 -m pytest -q
# or: python -m unittest discover -s tests -p 'test_*.py'
```

## References

- [SKILL.md](SKILL.md) — full skill contract (input/output, rules, phases)
- [references/boundary.md](references/boundary.md) — ownership boundary and lifecycle
- [references/readiness-artifact.md](references/readiness-artifact.md) — artifact schema and freshness rules
- [references/backend-setup.md](references/backend-setup.md) — backend readiness checks and bootstrap
- [references/repo-setup.md](references/repo-setup.md) — repo structure checks and scaffolding mutations
