"""Integration tests: bootstrap mutations fix corresponding repo checks.

Verifies B1–B3 fix R1–R6, are idempotent on re-run, and handle edge cases.

Known bugs documented by these tests:
  - B1 raises OSError when .ml-metaopt exists as a file instead of returning
    a BootstrapResult with an error (test_14).
  - B3 raises PermissionError on a read-only .gitignore instead of returning
    a BootstrapResult with an error (test_15).
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from scripts.bootstrap.repo_bootstrap import (
    BootstrapResult,
    bootstrap_B1,
    bootstrap_B2,
    bootstrap_B3,
    run_all_repo_bootstrap,
)
from scripts.checks.repo_checks import (
    CheckResult,
    check_R1,
    check_R2,
    check_R3,
    check_R4,
    check_R5,
    check_R6,
)

_ML_DIR = ".ml-metaopt"
_EMPTY_CAMPAIGN: dict = {}


# ── Fixture ─────────────────────────────────────────────────────────────


@pytest.fixture()
def make_empty_project(tmp_path: Path) -> Path:
    """Bare project root — no .ml-metaopt/ dir, no .gitignore."""
    return tmp_path


# ── B1 → R1 loop ───────────────────────────────────────────────────────


def test_01_B1_fixes_R1(make_empty_project: Path) -> None:
    """Empty project: R1 fails, B1 fixes it, R1 now passes."""
    proj = make_empty_project
    assert check_R1(_EMPTY_CAMPAIGN, proj).passed is False

    bootstrap_B1(proj)

    assert check_R1(_EMPTY_CAMPAIGN, proj).passed is True


def test_02_B1_applied_true_on_first_run(make_empty_project: Path) -> None:
    """B1 applied=True, already_ok=False on first run."""
    result = bootstrap_B1(make_empty_project)
    assert result.applied is True
    assert result.already_ok is False


def test_03_B1_already_ok_on_second_run(make_empty_project: Path) -> None:
    """B1 applied=False, already_ok=True on second run."""
    proj = make_empty_project
    bootstrap_B1(proj)
    result = bootstrap_B1(proj)
    assert result.applied is False
    assert result.already_ok is True


# ── B2 → R3/R4/R5/R6 loop ──────────────────────────────────────────────


def test_04_B1_B2_fixes_R3_R4_R5_R6(make_empty_project: Path) -> None:
    """After B1+B2: R3, R4, R5, R6 all pass."""
    proj = make_empty_project
    bootstrap_B1(proj)
    bootstrap_B2(proj)

    assert check_R3(_EMPTY_CAMPAIGN, proj).passed is True
    assert check_R4(_EMPTY_CAMPAIGN, proj).passed is True
    assert check_R5(_EMPTY_CAMPAIGN, proj).passed is True
    assert check_R6(_EMPTY_CAMPAIGN, proj).passed is True


def test_05_B2_creates_only_missing_dirs(make_empty_project: Path) -> None:
    """Partial setup (only handoffs/ exists): B2 creates the 7 missing, not the 1 existing."""
    proj = make_empty_project
    base = proj / _ML_DIR
    (base / "handoffs").mkdir(parents=True)

    result = bootstrap_B2(proj)

    assert result.applied is True
    assert "7" in result.message, f"Expected 7 created dirs, got: {result.message}"
    # All 8 should exist now
    for subdir in (
        "handoffs",
        "worker-results",
        "tasks",
        "executor-events",
        "artifacts/code",
        "artifacts/data",
        "artifacts/manifests",
        "artifacts/patches",
    ):
        assert (base / subdir).is_dir(), f"{subdir} missing"


def test_06_B2_not_already_ok_when_one_dir_missing(make_empty_project: Path) -> None:
    """B2 already_ok=False when even one dir is missing."""
    proj = make_empty_project
    base = proj / _ML_DIR
    # Create 7 of 8 — leave out executor-events
    for subdir in (
        "handoffs",
        "worker-results",
        "tasks",
        "artifacts/code",
        "artifacts/data",
        "artifacts/manifests",
        "artifacts/patches",
    ):
        (base / subdir).mkdir(parents=True, exist_ok=True)

    result = bootstrap_B2(proj)
    assert result.already_ok is False
    assert result.applied is True


# ── B3 → R2 loop ───────────────────────────────────────────────────────


def test_07_B3_creates_gitignore_with_entry(make_empty_project: Path) -> None:
    """No .gitignore: B3 creates it with .ml-metaopt/ entry."""
    proj = make_empty_project
    result = bootstrap_B3(proj)
    assert result.applied is True
    assert result.already_ok is False
    content = (proj / ".gitignore").read_text()
    assert ".ml-metaopt/" in content


def test_08_B3_appends_to_existing_gitignore(make_empty_project: Path) -> None:
    """.gitignore exists without entry: B3 appends it."""
    proj = make_empty_project
    gitignore = proj / ".gitignore"
    gitignore.write_text("*.pyc\n__pycache__/\n")

    result = bootstrap_B3(proj)

    assert result.applied is True
    content = gitignore.read_text()
    assert "*.pyc" in content
    assert ".ml-metaopt/" in content


def test_09_B3_fixes_R2(make_empty_project: Path) -> None:
    """After B3: R2 passes (R2 checks root .gitignore for .ml-metaopt/ entry)."""
    proj = make_empty_project
    bootstrap_B1(proj)

    # Before B3, R2 fails — no .gitignore yet
    assert check_R2(_EMPTY_CAMPAIGN, proj).passed is False

    bootstrap_B3(proj)

    assert check_R2(_EMPTY_CAMPAIGN, proj).passed is True


# ── run_all_repo_bootstrap integration ──────────────────────────────────


def test_10_run_all_on_empty_project(make_empty_project: Path) -> None:
    """On a fully empty project: run_all_repo_bootstrap creates all dirs and gitignore."""
    proj = make_empty_project
    results = run_all_repo_bootstrap(proj)

    assert len(results) == 3
    assert (proj / _ML_DIR).is_dir()
    assert (proj / ".gitignore").is_file()
    for subdir in (
        "handoffs",
        "worker-results",
        "tasks",
        "executor-events",
        "artifacts/code",
        "artifacts/data",
        "artifacts/manifests",
        "artifacts/patches",
    ):
        assert (proj / _ML_DIR / subdir).is_dir(), f"{subdir} missing after run_all"


def test_11_second_run_all_already_ok(make_empty_project: Path) -> None:
    """Second call: all results are already_ok=True, none applied=True."""
    proj = make_empty_project
    run_all_repo_bootstrap(proj)
    results = run_all_repo_bootstrap(proj)

    for r in results:
        assert r.already_ok is True, f"{r.mutation_id} not already_ok on second run"
        assert r.applied is False, f"{r.mutation_id} applied on second run"


def test_12_B2_skipped_when_B1_already_created_dir(make_empty_project: Path) -> None:
    """B2 is already_ok when B1 first run already created the root dir (but not subdirs).

    Actually B1 only creates the root .ml-metaopt/ dir.
    B2 should still need to create subdirs, so B2.already_ok=False on first run.
    On second full run, B2 is already_ok because B2 first-run created them.
    """
    proj = make_empty_project
    # First run: B1 creates root, B2 creates subdirs
    results_first = run_all_repo_bootstrap(proj)
    b2_first = [r for r in results_first if r.mutation_id == "B2"][0]
    assert b2_first.applied is True

    # Second run: B2 is already_ok
    results_second = run_all_repo_bootstrap(proj)
    b2_second = [r for r in results_second if r.mutation_id == "B2"][0]
    assert b2_second.already_ok is True
    assert b2_second.applied is False


# ── Idempotency invariant ───────────────────────────────────────────────


def test_13_triple_run_idempotent(make_empty_project: Path) -> None:
    """Run run_all_repo_bootstrap 3 times; third run: all already_ok, none applied."""
    proj = make_empty_project
    run_all_repo_bootstrap(proj)
    run_all_repo_bootstrap(proj)
    results = run_all_repo_bootstrap(proj)

    for r in results:
        assert r.already_ok is True, f"{r.mutation_id} not already_ok on third run"
        assert r.applied is False, f"{r.mutation_id} applied on third run"

    # Verify no filesystem mutations occurred by checking directory listing is stable
    dirs_before = sorted(str(p) for p in (proj / _ML_DIR).rglob("*") if p.is_dir())
    run_all_repo_bootstrap(proj)
    dirs_after = sorted(str(p) for p in (proj / _ML_DIR).rglob("*") if p.is_dir())
    assert dirs_before == dirs_after


# ── Edge cases ──────────────────────────────────────────────────────────


def test_14_B1_raises_when_ml_metaopt_is_file(make_empty_project: Path) -> None:
    """.ml-metaopt exists as a FILE: B1 raises instead of returning error result.

    BUG: B1 should return BootstrapResult(applied=False, error=...) but currently
    raises OSError.  This test documents the current (broken) behavior.
    """
    proj = make_empty_project
    (proj / _ML_DIR).write_text("not a directory")

    with pytest.raises(OSError):
        bootstrap_B1(proj)


def test_15_B3_raises_on_readonly_gitignore(make_empty_project: Path) -> None:
    """.gitignore is not writable (chmod 444): B3 raises PermissionError.

    BUG: B3 should return BootstrapResult(applied=False, error=...) but currently
    raises PermissionError.  This test documents the current (broken) behavior.
    """
    proj = make_empty_project
    gitignore = proj / ".gitignore"
    gitignore.write_text("*.pyc\n")
    gitignore.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)  # 444

    try:
        with pytest.raises(PermissionError):
            bootstrap_B3(proj)
    finally:
        # Restore write permission so tmp_path cleanup succeeds
        gitignore.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
