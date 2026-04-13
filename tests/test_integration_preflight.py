"""End-to-end integration tests for scripts/run_preflight.py.

14 scenarios covering happy path, bootstrap, failure, error, and hash
consistency.  Backend checks mocked to avoid network calls.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest
import yaml

from scripts._artifact_utils import ARTIFACT_FILENAME
from scripts._hash_utils import compute_campaign_identity_hash
from scripts.checks.repo_checks import CheckResult
from scripts.run_preflight import main

_STATE_DIR = ".ml-metaopt"
_REPO_ROOT = Path(__file__).resolve().parent.parent

_CAMPAIGN = {
    "campaign_name": "test-campaign",
    "objective": {
        "metric": "val_loss",
        "direction": "minimize",
    },
    "wandb": {
        "entity": "test-entity",
        "project": "test-project",
    },
    "compute": {
        "cloud": "vast",
        "instance_type": "A100",
    },
    "project": {
        "repo": "https://github.com/test/repo",
        "smoke_test_command": "python -c \"print('ok')\"",
    },
    "search_space": {
        "learning_rate": {
            "type": "log_uniform",
            "min": 1e-4,
            "max": 1e-2,
        },
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


# ── Mock helpers ─────────────────────────────────────────────────────


def _fresh_backend_pass(_campaign=None):
    """Return fresh passing backend results (avoids shared-state mutation)."""
    return [
        CheckResult(check_id="skypilot_installed", passed=True, message="ok"),
        CheckResult(check_id="vast_configured", passed=True, message="ok"),
        CheckResult(check_id="wandb_credentials", passed=True, message="ok"),
        CheckResult(check_id="repo_access", passed=True, message="ok"),
        CheckResult(
            check_id="smoke_test_command_nonempty",
            passed=True,
            message="ok",
            category="warning",
        ),
    ]


def _fresh_backend_fail(_campaign=None):
    """Return backend results with skypilot_installed failing."""
    return [
        CheckResult(
            check_id="skypilot_installed",
            passed=False,
            message="not found",
            remediation="pip install sky",
        ),
        CheckResult(check_id="vast_configured", passed=True, message="ok"),
        CheckResult(check_id="wandb_credentials", passed=True, message="ok"),
        CheckResult(check_id="repo_access", passed=True, message="ok"),
        CheckResult(
            check_id="smoke_test_command_nonempty",
            passed=True,
            message="ok",
            category="warning",
        ),
    ]


# ── Shared fixture ───────────────────────────────────────────────────


@pytest.fixture()
def make_project(tmp_path):
    """Factory fixture: create a minimal valid project directory.

    Returns ``(cwd, campaign_file)``.  By default every ``.ml-metaopt/``
    subdir, ``.ml-metaopt/.gitignore``, and root ``.gitignore`` are
    created so that all repo checks pass.
    """

    def _make(
        campaign: dict | None = None,
        *,
        skip_ml_dir: bool = False,
        skip_subdirs: bool = False,
        skip_ml_gitignore: bool = False,
        skip_root_gitignore: bool = False,
        omit_subdirs: list[str] | None = None,
    ) -> tuple[Path, Path]:
        cwd = tmp_path
        data = campaign if campaign is not None else dict(_CAMPAIGN)
        campaign_file = cwd / "campaign.yaml"
        campaign_file.write_text(yaml.dump(data), encoding="utf-8")

        if not skip_ml_dir:
            ml_dir = cwd / _STATE_DIR
            ml_dir.mkdir(exist_ok=True)

            if not skip_ml_gitignore:
                (ml_dir / ".gitignore").write_text(".ml-metaopt/\n")

            if not skip_subdirs:
                omit = set(omit_subdirs or [])
                for subdir in _ALL_ML_SUBDIRS:
                    if subdir not in omit:
                        (ml_dir / subdir).mkdir(parents=True, exist_ok=True)

        if not skip_root_gitignore:
            (cwd / ".gitignore").write_text(".ml-metaopt/\n")

        return cwd, campaign_file

    return _make


def _read_artifact(cwd: Path) -> dict:
    """Read and return the preflight readiness artifact."""
    path = cwd / _STATE_DIR / ARTIFACT_FILENAME
    return json.loads(path.read_text(encoding="utf-8"))


# ── Happy path (tests 1–4) ──────────────────────────────────────────


@mock.patch("scripts.run_preflight.run_all_backend_checks")
def test_happy_exit_0_status_ready(mock_backend, make_project):
    """1. All checks pass → exit 0, artifact status READY."""
    mock_backend.side_effect = _fresh_backend_pass
    cwd, cf = make_project()

    rc = main(["--campaign", str(cf), "--cwd", str(cwd)])

    assert rc == 0
    art = _read_artifact(cwd)
    assert art["status"] == "READY"


@mock.patch("scripts.run_preflight.run_all_backend_checks")
def test_artifact_written_to_state_dir(mock_backend, make_project):
    """2. Artifact written to <cwd>/.ml-metaopt/preflight-readiness.json."""
    mock_backend.side_effect = _fresh_backend_pass
    cwd, cf = make_project()

    main(["--campaign", str(cf), "--cwd", str(cwd)])

    artifact_path = cwd / _STATE_DIR / ARTIFACT_FILENAME
    assert artifact_path.is_file()
    assert artifact_path.name == "preflight-readiness.json"


@mock.patch("scripts.run_preflight.run_all_backend_checks")
def test_artifact_has_correct_identity_hash(mock_backend, make_project):
    """3. campaign_identity_hash matches compute_campaign_identity_hash."""
    mock_backend.side_effect = _fresh_backend_pass
    cwd, cf = make_project()

    main(["--campaign", str(cf), "--cwd", str(cwd)])

    art = _read_artifact(cwd)
    campaign_data = yaml.safe_load(cf.read_text())
    expected = compute_campaign_identity_hash(campaign_data)
    assert art["campaign_identity_hash"] == expected


@mock.patch("scripts.run_preflight.run_all_backend_checks")
def test_checks_summary_total_14(mock_backend, make_project):
    """4. checks_summary.total == 14 (9 repo + 5 backend)."""
    mock_backend.side_effect = _fresh_backend_pass
    cwd, cf = make_project()

    main(["--campaign", str(cf), "--cwd", str(cwd)])

    art = _read_artifact(cwd)
    assert art["checks_summary"]["total"] == 14


# ── Bootstrap path (tests 5–6) ──────────────────────────────────────


@mock.patch("scripts.run_preflight.run_all_backend_checks")
def test_bootstrap_missing_subdirs_becomes_ready(mock_backend, make_project):
    """5. Missing .ml-metaopt/ subdirs → bootstrap creates them → READY."""
    mock_backend.side_effect = _fresh_backend_pass
    cwd, cf = make_project(skip_subdirs=True)

    rc = main(["--campaign", str(cf), "--cwd", str(cwd)])

    assert rc == 0
    art = _read_artifact(cwd)
    assert art["status"] == "READY"
    assert art["checks_summary"]["bootstrapped"] > 0
    ml_dir = cwd / _STATE_DIR
    for subdir in _ALL_ML_SUBDIRS:
        assert (ml_dir / subdir).is_dir(), f"{subdir} should exist after bootstrap"


@mock.patch("scripts.run_preflight.run_all_backend_checks")
def test_bootstrap_creates_root_gitignore(mock_backend, make_project):
    """6. Bootstrap side-effect: creates root .gitignore when repo checks fail.

    When a subdir is missing, bootstrap (B1-B3) runs.  B3 creates
    root .gitignore as a side-effect even though the trigger was a
    missing subdir (R3).
    """
    mock_backend.side_effect = _fresh_backend_pass
    cwd, cf = make_project(skip_root_gitignore=True, omit_subdirs=["handoffs"])

    assert not (cwd / ".gitignore").exists()

    rc = main(["--campaign", str(cf), "--cwd", str(cwd)])

    assert rc == 0
    assert (cwd / ".gitignore").is_file()
    content = (cwd / ".gitignore").read_text()
    assert ".ml-metaopt/" in content


# ── Failure path (tests 7–9) ────────────────────────────────────────


@mock.patch("scripts.run_preflight.run_all_backend_checks")
def test_backend_hard_failure_exit_1(mock_backend, make_project):
    """7. Backend hard failure (sky not installed) → exit 1, FAILED."""
    mock_backend.side_effect = _fresh_backend_fail
    cwd, cf = make_project()

    rc = main(["--campaign", str(cf), "--cwd", str(cwd)])

    assert rc == 1
    art = _read_artifact(cwd)
    assert art["status"] == "FAILED"


@mock.patch("scripts.run_preflight.run_all_backend_checks")
def test_failed_artifact_has_failures(mock_backend, make_project):
    """8. FAILED artifact has non-empty failures list."""
    mock_backend.side_effect = _fresh_backend_fail
    cwd, cf = make_project()

    main(["--campaign", str(cf), "--cwd", str(cwd)])

    art = _read_artifact(cwd)
    assert art["status"] == "FAILED"
    assert len(art["failures"]) > 0
    fail_ids = {f["check_id"] for f in art["failures"]}
    assert "skypilot_installed" in fail_ids


@mock.patch("scripts.run_preflight.run_all_backend_checks")
def test_failed_next_action_not_proceed(mock_backend, make_project):
    """9. next_action in FAILED artifact is not 'proceed'."""
    mock_backend.side_effect = _fresh_backend_fail
    cwd, cf = make_project()

    main(["--campaign", str(cf), "--cwd", str(cwd)])

    art = _read_artifact(cwd)
    assert art["status"] == "FAILED"
    assert art["next_action"] != "proceed"


# ── Error path (tests 10–12) ────────────────────────────────────────


def test_missing_campaign_file_exit_2(tmp_path):
    """10. Missing campaign file → exit 2 (subprocess)."""
    missing = tmp_path / "nonexistent.yaml"
    result = subprocess.run(
        [
            sys.executable, "-m", "scripts.run_preflight",
            "--campaign", str(missing),
            "--cwd", str(tmp_path),
        ],
        capture_output=True,
        cwd=_REPO_ROOT,
    )
    assert result.returncode == 2


def test_malformed_yaml_exit_2(tmp_path):
    """11. Malformed YAML → exit 2 (subprocess)."""
    bad = tmp_path / "bad.yaml"
    bad.write_text("{{{{bad: yaml::::", encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable, "-m", "scripts.run_preflight",
            "--campaign", str(bad),
            "--cwd", str(tmp_path),
        ],
        capture_output=True,
        cwd=_REPO_ROOT,
    )
    assert result.returncode == 2


@mock.patch("scripts.run_preflight.run_all_backend_checks")
def test_missing_campaign_name_r8_fails_exit_1(mock_backend, make_project):
    """12. Campaign YAML missing campaign_name → R8 fails → exit 1 (not 2)."""
    mock_backend.side_effect = _fresh_backend_pass
    incomplete = {k: v for k, v in _CAMPAIGN.items() if k != "campaign_name"}
    cwd, cf = make_project(campaign=incomplete)

    rc = main(["--campaign", str(cf), "--cwd", str(cwd)])

    assert rc == 1
    art = _read_artifact(cwd)
    assert art["status"] == "FAILED"
    fail_ids = {f["check_id"] for f in art["failures"]}
    assert "R8" in fail_ids


# ── Hash path (tests 13–14) ─────────────────────────────────────────


def _scaffold_and_run(cwd: Path, campaign_data: dict) -> dict:
    """Set up a ready project in *cwd*, run preflight, return artifact."""
    ml_dir = cwd / _STATE_DIR
    ml_dir.mkdir(exist_ok=True)
    (ml_dir / ".gitignore").write_text(".ml-metaopt/\n")
    for subdir in _ALL_ML_SUBDIRS:
        (ml_dir / subdir).mkdir(parents=True, exist_ok=True)
    (cwd / ".gitignore").write_text(".ml-metaopt/\n")
    cf = cwd / "campaign.yaml"
    cf.write_text(yaml.dump(campaign_data), encoding="utf-8")
    main(["--campaign", str(cf), "--cwd", str(cwd)])
    return _read_artifact(cwd)


@mock.patch("scripts.run_preflight.run_all_backend_checks")
def test_same_campaign_same_hash(mock_backend, tmp_path):
    """13. Same campaign run twice → identical campaign_identity_hash."""
    mock_backend.side_effect = _fresh_backend_pass

    dir_a = tmp_path / "run_a"
    dir_a.mkdir()
    dir_b = tmp_path / "run_b"
    dir_b.mkdir()

    art_a = _scaffold_and_run(dir_a, dict(_CAMPAIGN))
    art_b = _scaffold_and_run(dir_b, dict(_CAMPAIGN))

    assert art_a["campaign_identity_hash"] == art_b["campaign_identity_hash"]


@mock.patch("scripts.run_preflight.run_all_backend_checks")
def test_changed_identity_field_different_hash(mock_backend, tmp_path):
    """14. Changed identity field → different campaign_identity_hash.

    NOTE: The identity hash uses objective.metric (via _get_nested),
    so changing it produces a different hash.  Flat ``campaign_name``
    is NOT in the identity hash (it uses ``campaign.name`` nested).
    """
    mock_backend.side_effect = _fresh_backend_pass

    dir_a = tmp_path / "run_a"
    dir_a.mkdir()
    dir_b = tmp_path / "run_b"
    dir_b.mkdir()

    campaign_a = dict(_CAMPAIGN)
    campaign_b = {**_CAMPAIGN, "objective": {"metric": "train_loss", "direction": "minimize"}}

    art_a = _scaffold_and_run(dir_a, campaign_a)
    art_b = _scaffold_and_run(dir_b, campaign_b)

    assert art_a["campaign_identity_hash"] != art_b["campaign_identity_hash"]
