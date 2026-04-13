"""Integration tests for scripts/run_preflight.py."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from unittest import mock

import pytest
import yaml

from scripts._artifact_utils import ARTIFACT_FILENAME
from scripts.checks.repo_checks import CheckResult
from scripts.run_preflight import main, run_preflight

_STATE_DIR = ".ml-metaopt"

_VALID_CAMPAIGN = {
    "campaign": {"name": "test-campaign", "description": "test"},
    "objective": {"metric": "val/accuracy", "direction": "maximize", "improvement_threshold": 0.005},
    "wandb": {"entity": "test-entity", "project": "test-project"},
    "compute": {
        "provider": "vast_ai",
        "accelerator": "A100:1",
        "num_sweep_agents": 4,
        "max_budget_usd": 10,
    },
    "project": {
        "repo": "git@github.com:org/repo.git",
        "smoke_test_command": "python train.py --smoke",
    },
}

_ALL_ML_SUBDIRS = [
    "handoffs",
    "worker-results",
    "tasks",
    "executor-events",
    "artifacts/code",
    "artifacts/data",
    "artifacts/manifests",
    "artifacts/patches",
]


def _write_campaign(path: Path, data: dict | None = None) -> Path:
    """Write campaign YAML and return the path."""
    campaign_file = path / "campaign.yaml"
    campaign_file.write_text(yaml.dump(data or _VALID_CAMPAIGN), encoding="utf-8")
    return campaign_file


def _scaffold_ready_state(cwd: Path) -> None:
    """Create all dirs and files so repo checks R1-R6 pass."""
    ml_dir = cwd / _STATE_DIR
    ml_dir.mkdir(exist_ok=True)
    gitignore = cwd / ".gitignore"
    gitignore.write_text(".ml-metaopt/\n")
    for subdir in _ALL_ML_SUBDIRS:
        (ml_dir / subdir).mkdir(parents=True, exist_ok=True)


def _mock_backend_all_pass(campaign):
    """Return backend CheckResults where all pass."""
    return [
        CheckResult("skypilot_installed", True, message="SkyPilot is installed", category="backend"),
        CheckResult("vast_configured", True, message="Vast.ai configured", category="backend"),
        CheckResult("wandb_credentials", True, message="WandB creds found", category="backend"),
        CheckResult("repo_access", True, message="Repo accessible", category="backend"),
        CheckResult(
            "smoke_test_command_nonempty", True, message="smoke_test_command set",
            category="warning",
        ),
    ]


def _mock_backend_sky_fails(campaign):
    """Return backend CheckResults where skypilot_installed fails."""
    return [
        CheckResult(
            "skypilot_installed", False,
            message="SkyPilot not found",
            category="backend",
            remediation="pip install 'skypilot[vast]'",
        ),
        CheckResult(
            "vast_configured", False, message="Vast.ai not configured",
            category="backend", remediation="Run sky check",
        ),
        CheckResult("wandb_credentials", True, message="WandB creds found", category="backend"),
        CheckResult("repo_access", True, message="Repo accessible", category="backend"),
        CheckResult(
            "smoke_test_command_nonempty", True, message="smoke_test_command set",
            category="warning",
        ),
    ]


# ── Test 1: Full happy path ─────────────────────────────────────────


@mock.patch("scripts.run_preflight.run_all_backend_checks")
def test_happy_path_all_pass(mock_backend, tmp_path: Path) -> None:
    """All dirs exist, campaign valid → READY, exit 0."""
    mock_backend.side_effect = _mock_backend_all_pass
    campaign_file = _write_campaign(tmp_path)
    _scaffold_ready_state(tmp_path)

    exit_code = run_preflight(campaign_file, tmp_path)

    assert exit_code == 0
    artifact_path = tmp_path / _STATE_DIR / ARTIFACT_FILENAME
    assert artifact_path.exists()
    artifact = json.loads(artifact_path.read_text())
    assert artifact["status"] == "READY"
    assert artifact["next_action"] == "proceed"
    assert artifact["failures"] == []
    assert artifact["campaign_id"] == "test-campaign"


# ── Test 2: Missing .ml-metaopt/ → bootstrap creates it → READY ─────


@mock.patch("scripts.run_preflight.run_all_backend_checks")
def test_bootstrap_creates_ml_dir(mock_backend, tmp_path: Path) -> None:
    """Missing subdirs: bootstrap creates them → READY after bootstrap."""
    mock_backend.side_effect = _mock_backend_all_pass
    campaign_file = _write_campaign(tmp_path)
    # Create .ml-metaopt/ and root .gitignore (R2 requires it) but NOT subdirs.
    # Bootstrap B2 will create the subdirs, fixing R3-R6.
    ml_dir = tmp_path / _STATE_DIR
    ml_dir.mkdir()
    (tmp_path / ".gitignore").write_text(".ml-metaopt/\n")

    exit_code = run_preflight(campaign_file, tmp_path)

    assert exit_code == 0
    assert (tmp_path / _STATE_DIR).is_dir()
    for subdir in _ALL_ML_SUBDIRS:
        assert (ml_dir / subdir).is_dir(), f"{subdir} should exist after bootstrap"
    artifact_path = tmp_path / _STATE_DIR / ARTIFACT_FILENAME
    artifact = json.loads(artifact_path.read_text())
    assert artifact["status"] == "READY"
    assert artifact["checks_summary"]["bootstrapped"] > 0


# ── Test 3: Hard backend failure → FAILED, exit 1 ───────────────────


@mock.patch("scripts.run_preflight.run_all_backend_checks")
def test_backend_failure_gives_failed(mock_backend, tmp_path: Path) -> None:
    """Hard backend failure (sky not installed) → FAILED, exit 1."""
    mock_backend.side_effect = _mock_backend_sky_fails
    campaign_file = _write_campaign(tmp_path)
    _scaffold_ready_state(tmp_path)

    exit_code = run_preflight(campaign_file, tmp_path)

    assert exit_code == 1
    artifact_path = tmp_path / _STATE_DIR / ARTIFACT_FILENAME
    artifact = json.loads(artifact_path.read_text())
    assert artifact["status"] == "FAILED"
    assert len(artifact["failures"]) > 0
    fail_ids = {f["check_id"] for f in artifact["failures"]}
    assert "skypilot_installed" in fail_ids


# ── Test 4: Invalid campaign YAML → exit 2 ──────────────────────────


def test_invalid_yaml_exit_2(tmp_path: Path) -> None:
    """Malformed YAML → exit 2."""
    bad_yaml = tmp_path / "bad.yaml"
    bad_yaml.write_text("{{{{not: valid: yaml::::", encoding="utf-8")

    exit_code = run_preflight(bad_yaml, tmp_path)

    assert exit_code == 2


# ── Test 5: Missing campaign file → exit 2 ──────────────────────────


def test_missing_campaign_exit_2(tmp_path: Path) -> None:
    """Non-existent campaign file → exit 2."""
    missing = tmp_path / "nonexistent.yaml"

    exit_code = run_preflight(missing, tmp_path)

    assert exit_code == 2


# ── Test 6: Artifact written to correct path ─────────────────────────


@mock.patch("scripts.run_preflight.run_all_backend_checks")
def test_artifact_written_to_correct_path(mock_backend, tmp_path: Path) -> None:
    """Artifact is written to .ml-metaopt/preflight-readiness.json."""
    mock_backend.side_effect = _mock_backend_all_pass
    campaign_file = _write_campaign(tmp_path)
    _scaffold_ready_state(tmp_path)

    run_preflight(campaign_file, tmp_path)

    artifact_path = tmp_path / _STATE_DIR / ARTIFACT_FILENAME
    assert artifact_path.is_file()
    artifact = json.loads(artifact_path.read_text())
    assert artifact["schema_version"] == 1
    assert "emitted_at" in artifact
    assert "campaign_identity_hash" in artifact
    assert artifact["campaign_identity_hash"].startswith("sha256:")
    assert artifact["runtime_config_hash"].startswith("sha256:")


# ── Test 7: bootstrapped > 0 when bootstrap fixed something ─────────


@mock.patch("scripts.run_preflight.run_all_backend_checks")
def test_bootstrapped_count_positive(mock_backend, tmp_path: Path) -> None:
    """checks_summary.bootstrapped > 0 when bootstrap fixed something."""
    mock_backend.side_effect = _mock_backend_all_pass
    campaign_file = _write_campaign(tmp_path)
    # Create .ml-metaopt/ and root .gitignore only; subdirs missing → bootstrap fixes them
    ml_dir = tmp_path / _STATE_DIR
    ml_dir.mkdir()
    (tmp_path / ".gitignore").write_text(".ml-metaopt/\n")

    exit_code = run_preflight(campaign_file, tmp_path)

    assert exit_code == 0
    artifact_path = tmp_path / _STATE_DIR / ARTIFACT_FILENAME
    artifact = json.loads(artifact_path.read_text())
    summary = artifact["checks_summary"]
    assert summary["bootstrapped"] > 0
    assert summary["total"] == summary["passed"] + summary["failed"] + summary["bootstrapped"] + summary.get("warnings", 0)


# ── Additional edge-case tests ───────────────────────────────────────


def test_campaign_yaml_empty_file_exit_2(tmp_path: Path) -> None:
    """Empty YAML file (parses to None) → exit 2."""
    empty = tmp_path / "empty.yaml"
    empty.write_text("", encoding="utf-8")

    exit_code = run_preflight(empty, tmp_path)

    assert exit_code == 2


def test_campaign_yaml_list_root_exit_2(tmp_path: Path) -> None:
    """YAML with list root (not dict) → exit 2."""
    list_yaml = tmp_path / "list.yaml"
    list_yaml.write_text("- item1\n- item2\n", encoding="utf-8")

    exit_code = run_preflight(list_yaml, tmp_path)

    assert exit_code == 2


@mock.patch("scripts.run_preflight.run_all_backend_checks")
def test_warnings_do_not_block_ready(mock_backend, tmp_path: Path) -> None:
    """Warning-category failures don't block READY status."""
    def backend_with_warning(campaign):
        return [
            CheckResult("skypilot_installed", True, message="SkyPilot is installed", category="backend"),
            CheckResult("vast_configured", True, message="Vast.ai configured", category="backend"),
            CheckResult("wandb_credentials", True, message="WandB creds found", category="backend"),
            CheckResult("repo_access", True, message="Repo accessible", category="backend"),
            CheckResult(
                "smoke_test_command_nonempty", False,
                message="smoke_test_command not set",
                category="warning",
                remediation="Set project.smoke_test_command",
            ),
        ]

    mock_backend.side_effect = backend_with_warning
    campaign_file = _write_campaign(tmp_path)
    _scaffold_ready_state(tmp_path)

    exit_code = run_preflight(campaign_file, tmp_path)

    assert exit_code == 0
    artifact = json.loads(
        (tmp_path / _STATE_DIR / ARTIFACT_FILENAME).read_text()
    )
    assert artifact["status"] == "READY"


@mock.patch("scripts.run_preflight.run_all_backend_checks")
def test_main_cli_interface(mock_backend, tmp_path: Path) -> None:
    """main() parses CLI args correctly."""
    mock_backend.side_effect = _mock_backend_all_pass
    campaign_file = _write_campaign(tmp_path)
    _scaffold_ready_state(tmp_path)

    exit_code = main(["--campaign", str(campaign_file), "--cwd", str(tmp_path)])

    assert exit_code == 0
