"""Tests for repository readiness checks R1–R9."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.checks.repo_checks import (
    CheckResult,
    check_R1,
    check_R2,
    check_R3,
    check_R4,
    check_R5,
    check_R6,
    check_R7,
    check_R8,
    check_R9,
    run_all_repo_checks,
)

# ── Helpers ──────────────────────────────────────────────────────────

_MINIMAL_CAMPAIGN: dict = {
    "campaign": {"name": "test-campaign"},
    "objective": {"metric": "val/accuracy", "direction": "maximize"},
    "wandb": {"entity": "test", "project": "test"},
    "compute": {"provider": "vast_ai"},
    "project": {
        "repo": "git@github.com:org/repo.git",
        "smoke_test_command": "python train.py --smoke",
    },
}

_ML_DIR = ".ml-metaopt"

_ALL_SUBDIRS = [
    "handoffs",
    "worker-results",
    "tasks",
    "executor-events",
    "artifacts/code",
    "artifacts/data",
    "artifacts/manifests",
    "artifacts/patches",
]


@pytest.fixture()
def fully_setup(tmp_path: Path) -> Path:
    """Create a fully ready repo structure + minimal campaign YAML."""
    ml = tmp_path / _ML_DIR
    for subdir in _ALL_SUBDIRS:
        (ml / subdir).mkdir(parents=True, exist_ok=True)
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text(".ml-metaopt/\n")
    return tmp_path


# ── All-pass scenario ───────────────────────────────────────────────


def test_all_checks_pass(fully_setup: Path) -> None:
    results = run_all_repo_checks(_MINIMAL_CAMPAIGN, fully_setup)
    for r in results:
        assert r.passed, f"{r.check_id} failed: {r.message}"


# ── R1: .ml-metaopt/ directory ───────────────────────────────────────


def test_R1_fails_when_dir_missing(tmp_path: Path) -> None:
    result = check_R1(_MINIMAL_CAMPAIGN, tmp_path)
    assert not result.passed
    assert result.check_id == "R1"
    assert result.remediation


def test_R1_passes(fully_setup: Path) -> None:
    result = check_R1(_MINIMAL_CAMPAIGN, fully_setup)
    assert result.passed


# ── R2: .ml-metaopt/.gitignore ──────────────────────────────────────


def test_R2_fails_when_gitignore_missing(fully_setup: Path) -> None:
    (fully_setup / ".gitignore").unlink()
    result = check_R2(_MINIMAL_CAMPAIGN, fully_setup)
    assert not result.passed
    assert result.check_id == "R2"


def test_R2_fails_when_entry_missing(fully_setup: Path) -> None:
    (fully_setup / ".gitignore").write_text("*.pyc\n")
    result = check_R2(_MINIMAL_CAMPAIGN, fully_setup)
    assert not result.passed


def test_R2_passes(fully_setup: Path) -> None:
    result = check_R2(_MINIMAL_CAMPAIGN, fully_setup)
    assert result.passed


# ── R3: handoffs/ ────────────────────────────────────────────────────


def test_R3_fails_when_handoffs_missing(fully_setup: Path) -> None:
    (fully_setup / _ML_DIR / "handoffs").rmdir()
    result = check_R3(_MINIMAL_CAMPAIGN, fully_setup)
    assert not result.passed
    assert result.check_id == "R3"


# ── R4: worker-results/ ─────────────────────────────────────────────


def test_R4_fails_when_worker_results_missing(fully_setup: Path) -> None:
    (fully_setup / _ML_DIR / "worker-results").rmdir()
    result = check_R4(_MINIMAL_CAMPAIGN, fully_setup)
    assert not result.passed
    assert result.check_id == "R4"


# ── R5: tasks/ and executor-events/ ─────────────────────────────────


def test_R5_fails_when_tasks_missing(fully_setup: Path) -> None:
    (fully_setup / _ML_DIR / "tasks").rmdir()
    result = check_R5(_MINIMAL_CAMPAIGN, fully_setup)
    assert not result.passed
    assert "tasks" in result.message


def test_R5_fails_when_executor_events_missing(fully_setup: Path) -> None:
    (fully_setup / _ML_DIR / "executor-events").rmdir()
    result = check_R5(_MINIMAL_CAMPAIGN, fully_setup)
    assert not result.passed
    assert "executor-events" in result.message


def test_R5_fails_when_both_missing(fully_setup: Path) -> None:
    (fully_setup / _ML_DIR / "tasks").rmdir()
    (fully_setup / _ML_DIR / "executor-events").rmdir()
    result = check_R5(_MINIMAL_CAMPAIGN, fully_setup)
    assert not result.passed
    assert "tasks" in result.message
    assert "executor-events" in result.message


# ── R6: artifacts subdirs ────────────────────────────────────────────


@pytest.mark.parametrize("subdir", ["code", "data", "manifests", "patches"])
def test_R6_fails_when_artifact_subdir_missing(fully_setup: Path, subdir: str) -> None:
    (fully_setup / _ML_DIR / "artifacts" / subdir).rmdir()
    result = check_R6(_MINIMAL_CAMPAIGN, fully_setup)
    assert not result.passed
    assert subdir in result.message


# ── R7: smoke_test_command ───────────────────────────────────────────


def test_R7_fails_when_smoke_test_command_missing(fully_setup: Path) -> None:
    campaign = {**_MINIMAL_CAMPAIGN, "project": {"repo": "git@github.com:org/repo.git"}}
    result = check_R7(campaign, fully_setup)
    assert not result.passed
    assert result.check_id == "R7"


def test_R7_fails_when_smoke_test_command_empty(fully_setup: Path) -> None:
    campaign = {
        **_MINIMAL_CAMPAIGN,
        "project": {**_MINIMAL_CAMPAIGN["project"], "smoke_test_command": ""},
    }
    result = check_R7(campaign, fully_setup)
    assert not result.passed


def test_R7_fails_when_smoke_test_command_whitespace(fully_setup: Path) -> None:
    campaign = {
        **_MINIMAL_CAMPAIGN,
        "project": {**_MINIMAL_CAMPAIGN["project"], "smoke_test_command": "   "},
    }
    result = check_R7(campaign, fully_setup)
    assert not result.passed


def test_R7_fails_when_project_section_missing(fully_setup: Path) -> None:
    campaign = {k: v for k, v in _MINIMAL_CAMPAIGN.items() if k != "project"}
    result = check_R7(campaign, fully_setup)
    assert not result.passed


# ── R8: required top-level keys ──────────────────────────────────────


@pytest.mark.parametrize(
    "missing_key",
    ["campaign", "objective", "wandb", "compute", "project"],
)
def test_R8_fails_when_key_absent(fully_setup: Path, missing_key: str) -> None:
    campaign = {k: v for k, v in _MINIMAL_CAMPAIGN.items() if k != missing_key}
    result = check_R8(campaign, fully_setup)
    assert not result.passed
    assert missing_key in result.message


# ── R9: project.repo ────────────────────────────────────────────────


def test_R9_fails_when_repo_empty(fully_setup: Path) -> None:
    campaign = {**_MINIMAL_CAMPAIGN, "project": {**_MINIMAL_CAMPAIGN["project"], "repo": ""}}
    result = check_R9(campaign, fully_setup)
    assert not result.passed
    assert result.check_id == "R9"


def test_R9_fails_when_repo_missing(fully_setup: Path) -> None:
    campaign = {**_MINIMAL_CAMPAIGN, "project": {"smoke_test_command": "echo hi"}}
    result = check_R9(campaign, fully_setup)
    assert not result.passed


def test_R9_fails_when_project_section_missing(fully_setup: Path) -> None:
    campaign = {k: v for k, v in _MINIMAL_CAMPAIGN.items() if k != "project"}
    result = check_R9(campaign, fully_setup)
    assert not result.passed


# ── run_all_repo_checks ─────────────────────────────────────────────


def test_run_all_returns_9_results(fully_setup: Path) -> None:
    results = run_all_repo_checks(_MINIMAL_CAMPAIGN, fully_setup)
    assert len(results) == 9
    ids = [r.check_id for r in results]
    assert ids == [f"R{i}" for i in range(1, 10)]


def test_run_all_catches_exceptions(tmp_path: Path) -> None:
    """If a check raises, it becomes a failed CheckResult."""

    def _bad_campaign() -> dict:
        return None  # type: ignore[return-value]

    # Pass None as campaign to trigger AttributeError inside dict-accessing checks
    results = run_all_repo_checks(None, tmp_path)  # type: ignore[arg-type]
    assert len(results) == 9
    # Filesystem checks (R1-R6) should still work with None campaign
    # Dict-accessing checks (R7-R9) should be caught as exceptions or handle gracefully
    for r in results:
        assert isinstance(r, CheckResult)
