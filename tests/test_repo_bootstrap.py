"""Tests for repo bootstrap mutations B1–B3."""

from __future__ import annotations

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


# ── B3: .gitignore entry ────────────────────────────────────────────


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


# ── run_all_repo_bootstrap ──────────────────────────────────────────


def test_run_all_skips_B2_if_B1_raises(tmp_path: Path) -> None:
    with patch(
        "scripts.bootstrap.repo_bootstrap.bootstrap_B1",
        side_effect=PermissionError("cannot create dir"),
    ):
        with pytest.raises(PermissionError):
            run_all_repo_bootstrap(tmp_path)
