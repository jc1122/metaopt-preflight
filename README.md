# metaopt-preflight

One-shot preflight check for [ml-metaoptimization](https://github.com/jc1122/ml-metaoptimization) campaigns.

## What it does

Runs before you start an `ml-metaoptimization` campaign to verify that your
repo structure, backend configuration, and environment are ready. It performs
bounded bootstrap fixes where possible and emits a readiness artifact.
`LOAD_CAMPAIGN` reads the artifact at startup — a stale or missing artifact
blocks the campaign with `BLOCKED_CONFIG`.

## Prerequisites

- Python 3.10+
- PyYAML ≥ 6.0 (installed via `requirements.txt`)
- [ml-metaoptimization](https://github.com/jc1122/ml-metaoptimization) campaign YAML
- SkyPilot with Vast.ai provider — `pip install 'skypilot[vast]'`
- WandB credentials — `WANDB_API_KEY` env var or `wandb login`
- `git` on PATH

## Installation / usage

```bash
# Clone and install deps (no pip install needed — it's a script)
git clone https://github.com/jc1122/metaopt-preflight
cd metaopt-preflight
pip install -r requirements.txt

# Run preflight (preferred — works from any directory):
python3 -m scripts.run_preflight --campaign /path/to/campaign.yaml [--cwd /project/root]

# Also works (must be run from repo root):
python3 scripts/run_preflight.py --campaign /path/to/campaign.yaml [--cwd /project/root]
```

### CLI flags

| Flag | Required | Default | Description |
|------|----------|---------|-------------|
| `--campaign` | Yes | — | Path to campaign YAML file |
| `--cwd` | No | `.` | Project root directory (must contain `ml_metaopt_campaign.yaml`) |

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | READY — proceed with `ml-metaoptimization` |
| 1 | FAILED — fix reported issues and re-run |
| 2 | Usage error — bad args or malformed YAML |

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

## What bootstrap does

Repo bootstrap mutations (B1–B3) are auto-applied for fixable issues:

| ID | Trigger | Action |
|----|---------|--------|
| B1 | R1 fails | `mkdir -p .ml-metaopt` |
| B2 | R3–R6 fail | `mkdir -p` all 8 required subdirectories |
| B3 | R2 fails | Append `.ml-metaopt/` to `.gitignore` |

All mutations are idempotent. Backend failures require manual remediation —
preflight emits guidance but never auto-installs packages or modifies
credentials.

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
`failures` (empty when READY), `next_action` (`proceed` or remediation text).

`checks_summary` counters:

| Field | Meaning |
|-------|---------|
| `total` | Number of checks evaluated |
| `passed` | Passed on initial evaluation |
| `failed` | Still failing after bootstrap |
| `bootstrapped` | Initially failed, fixed by bootstrap |
| `warnings` | Advisory issues that don't block readiness |

Invariant: `passed + failed + bootstrapped + warnings == total`.

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
