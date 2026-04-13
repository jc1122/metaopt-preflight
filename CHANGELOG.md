# Changelog

## [1.0.0] — 2026-04-13

### Added
- **R1–R9 repo checks** (`scripts/checks/repo_checks.py`)
  - R1: `.ml-metaopt/` directory exists
  - R2: `.gitignore` contains `.ml-metaopt/` entry
  - R3: `handoffs/` subdir exists
  - R4: `worker-results/` subdir exists
  - R5: `tasks/` and `executor-events/` subdirs exist
  - R6: 4 `artifacts/` subdirs exist (`code/`, `data/`, `manifests/`, `patches/`)
  - R7: `smoke_test_command` is a non-empty string
  - R8: required top-level campaign keys present (`campaign`, `project`, `wandb`, `compute`, `objective`)
  - R9: `project.repo` is a non-empty string
- **B1–B3 idempotent bootstrap mutations** (`scripts/bootstrap/repo_bootstrap.py`)
  - B1: create `.ml-metaopt/` directory
  - B2: create all 8 required subdirectories (`handoffs`, `worker-results`, `tasks`, `executor-events`, `artifacts/code`, `artifacts/data`, `artifacts/manifests`, `artifacts/patches`)
  - B3: create or append `.ml-metaopt/` to `.gitignore`
- **5 backend advisory checks** (`scripts/checks/backend_checks.py`)
  - `skypilot_installed`: `sky` CLI available on PATH
  - `vast_configured`: Vast.ai configured as SkyPilot cloud provider
  - `wandb_credentials`: W&B API key present and entity/project valid
  - `repo_access`: project repo SSH/HTTPS reachable
  - `smoke_test_command_nonempty`: smoke test command present in campaign YAML
- Main CLI entrypoint `scripts/run_preflight.py` (exit codes: 0=READY, 1=FAILED, 2=usage error)
- Both invocation styles: `python3 scripts/run_preflight.py` and `python3 -m scripts.run_preflight`
- 11-field readiness artifact at `.ml-metaopt/preflight-readiness.json` (schema version 1)
  - `schema_version`, `status`, `campaign_id`, `campaign_identity_hash`, `runtime_config_hash`, `emitted_at`, `preflight_duration_seconds`, `checks_summary`, `failures`, `next_action`, `diagnostics`
- `checks_summary` with 5 subfields: `total`, `passed`, `failed`, `bootstrapped`, `warnings`
- Campaign identity hash (`sha256:`) matching `_identity_hash()` in ml-metaoptimization — uses canonical JSON of `campaign_name`, `objective.{metric,direction}`, `wandb.{entity,project}`
- Runtime config hash (informational, not validated by v4 orchestrator) — covers `compute`, `wandb.{entity,project}`, `project.{repo,smoke_test_command}`
- Agent definition `.github/agents/metaopt-preflight.agent.md`
- Context window guide `references/context-window-guide.md`
- 199 tests at 98% coverage
- Cross-compat tests verifying integration with `_evaluate_preflight()` in ml-metaoptimization

### Notes
- Backend checks are advisory only — no auto-installation occurs
- `warnings` category checks do not block READY status
- B2 is skipped if B1 fails; B3 always runs regardless of B1 outcome
- All subprocess calls in backend checks are timeout-guarded
- Exceptions in individual checks are caught and recorded as failed `CheckResult` entries
- Compatible with ml-metaoptimization v4 orchestrator
