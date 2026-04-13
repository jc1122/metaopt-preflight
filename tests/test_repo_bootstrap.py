"""Tests for repo bootstrap mutations B1–B3."""

from __future__ import annotations

import stat
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.bootstrap.repo_bootstrap import (
    BootstrapResult,
    bootstrap_B1,
    bootstrap_B2,
    bootstrap_B3,
    run_all_repo_bootstrap,
)

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


# ── B1: .ml-metaopt/ directory ──────────────────────────────────────


def test_B1_creates_dir_when_missing(tmp_path: Path) -> None:
    result = bootstrap_B1(tmp_path)
    assert result.mutation_id == "B1"
    assert result.applied is True
    assert result.already_ok is False
    assert (tmp_path / _ML_DIR).is_dir()


def test_B1_idempotent_when_exists(tmp_path: Path) -> None:
    (tmp_path / _ML_DIR).mkdir()
    result = bootstrap_B1(tmp_path)
    assert result.mutation_id == "B1"
    assert result.applied is False
    assert result.already_ok is True


# ── B2: required subdirectories ─────────────────────────────────────


def test_B2_creates_all_8_subdirs(tmp_path: Path) -> None:
    (tmp_path / _ML_DIR).mkdir()
    result = bootstrap_B2(tmp_path)
    assert result.mutation_id == "B2"
    assert result.applied is True
    assert result.already_ok is False
    for subdir in _ALL_SUBDIRS:
        assert (tmp_path / _ML_DIR / subdir).is_dir(), f"{subdir} not created"


def test_B2_idempotent_when_all_exist(tmp_path: Path) -> None:
    for subdir in _ALL_SUBDIRS:
        (tmp_path / _ML_DIR / subdir).mkdir(parents=True, exist_ok=True)
    result = bootstrap_B2(tmp_path)
    assert result.mutation_id == "B2"
    assert result.applied is False
    assert result.already_ok is True


def test_B2_creates_only_missing_dirs(tmp_path: Path) -> None:
    base = tmp_path / _ML_DIR
    # Pre-create 3 of 8 subdirs
    for subdir in ("handoffs", "tasks", "artifacts/code"):
        (base / subdir).mkdir(parents=True, exist_ok=True)
    result = bootstrap_B2(tmp_path)
    assert result.applied is True
    assert result.already_ok is False
    assert "5" in result.message  # 5 created
    for subdir in _ALL_SUBDIRS:
        assert (base / subdir).is_dir()


# ── B3: .gitignore entry ────────────────────────────────────────


def test_B3_creates_gitignore_when_missing(tmp_path: Path) -> None:
    result = bootstrap_B3(tmp_path)
    assert result.mutation_id == "B3"
    assert result.applied is True
    assert result.already_ok is False
    gitignore = tmp_path / ".gitignore"
    assert gitignore.is_file()
    assert ".ml-metaopt/" in gitignore.read_text()


def test_B3_appends_to_existing_gitignore(tmp_path: Path) -> None:
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text("*.pyc\n__pycache__/\n")
    result = bootstrap_B3(tmp_path)
    assert result.applied is True
    assert result.already_ok is False
    content = gitignore.read_text()
    assert "*.pyc" in content
    assert ".ml-metaopt/" in content


def test_B3_idempotent_when_entry_present(tmp_path: Path) -> None:
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text("*.pyc\n.ml-metaopt/\n")
    result = bootstrap_B3(tmp_path)
    assert result.applied is False
    assert result.already_ok is True


def test_B3_matches_entry_without_trailing_slash(tmp_path: Path) -> None:
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text(".ml-metaopt\n")
    result = bootstrap_B3(tmp_path)
    assert result.applied is False
    assert result.already_ok is True


# ── B1/B3 error handling ────────────────────────────────────────


def test_B1_returns_error_when_ml_metaopt_is_file(tmp_path: Path) -> None:
    (tmp_path / ".ml-metaopt").write_text("not a directory")
    result = bootstrap_B1(tmp_path)
    assert result.mutation_id == "B1"
    assert result.applied is False
    assert result.already_ok is False
    assert "not a directory" in result.message


def test_B3_returns_error_on_permission_error(tmp_path: Path) -> None:
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text("*.pyc\n")
    gitignore.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)  # 444
    try:
        result = bootstrap_B3(tmp_path)
        assert result.mutation_id == "B3"
        assert result.applied is False
        assert result.already_ok is False
        assert "Cannot write .gitignore" in result.message
    finally:
        gitignore.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)


# ── run_all_repo_bootstrap ──────────────────────────────────────


def test_run_all_B1_fails_B3_still_runs(tmp_path: Path) -> None:
    with patch(
        "scripts.bootstrap.repo_bootstrap.bootstrap_B1",
        side_effect=PermissionError("cannot create dir"),
    ):
        results = run_all_repo_bootstrap(tmp_path)
    mutation_ids = [r.mutation_id for r in results]
    assert "B1" in mutation_ids
    assert "B2" not in mutation_ids  # skipped because B1 failed
    assert "B3" in mutation_ids
    b1 = [r for r in results if r.mutation_id == "B1"][0]
    assert b1.applied is False
    assert b1.already_ok is False


def test_B3_permission_error_when_creating_new_gitignore(tmp_path: Path) -> None:
    """B3 returns error when .gitignore doesn't exist and dir is read-only."""
    tmp_path.chmod(stat.S_IRUSR | stat.S_IXUSR)
    try:
        result = bootstrap_B3(tmp_path)
        assert result.mutation_id == "B3"
        assert result.applied is False
        assert result.already_ok is False
        assert "Cannot write .gitignore" in result.message
    finally:
        tmp_path.chmod(stat.S_IRWXU)


def test_run_all_B2_exception_caught(tmp_path: Path) -> None:
    """Exception in B2 is caught and B3 still runs."""
    (tmp_path / ".ml-metaopt").mkdir()
    with patch(
        "scripts.bootstrap.repo_bootstrap.bootstrap_B2",
        side_effect=RuntimeError("B2 exploded"),
    ):
        results = run_all_repo_bootstrap(tmp_path)
    mutation_ids = [r.mutation_id for r in results]
    assert "B1" in mutation_ids
    assert "B2" in mutation_ids
    assert "B3" in mutation_ids
    b2 = [r for r in results if r.mutation_id == "B2"][0]
    assert b2.applied is False
    assert "B2 failed" in b2.message


def test_run_all_B3_exception_caught(tmp_path: Path) -> None:
    """Exception in B3 is caught gracefully."""
    with patch(
        "scripts.bootstrap.repo_bootstrap.bootstrap_B3",
        side_effect=RuntimeError("B3 exploded"),
    ):
        results = run_all_repo_bootstrap(tmp_path)
    mutation_ids = [r.mutation_id for r in results]
    assert "B3" in mutation_ids
    b3 = [r for r in results if r.mutation_id == "B3"][0]
    assert b3.applied is False
    assert "B3 failed" in b3.message
