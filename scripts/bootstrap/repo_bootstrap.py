"""Idempotent repo bootstrap mutations B1–B3 for metaopt-preflight."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

_ML_METAOPT_DIR = ".ml-metaopt"

_REQUIRED_SUBDIRS = (
    "handoffs",
    "worker-results",
    "tasks",
    "executor-events",
    "artifacts/code",
    "artifacts/data",
    "artifacts/manifests",
    "artifacts/patches",
)


@dataclass
class BootstrapResult:
    mutation_id: str  # "B1", "B2", "B3"
    applied: bool  # True if mutation was performed
    already_ok: bool  # True if pre-condition already satisfied
    message: str


def bootstrap_B1(cwd: Path) -> BootstrapResult:
    """Create ``.ml-metaopt/`` directory (idempotent)."""
    target = cwd / _ML_METAOPT_DIR
    if target.exists() and not target.is_dir():
        return BootstrapResult(
            mutation_id="B1",
            applied=False,
            already_ok=False,
            message=f".ml-metaopt exists but is not a directory: {target}",
        )
    if target.is_dir():
        return BootstrapResult(
            mutation_id="B1",
            applied=False,
            already_ok=True,
            message=f"{_ML_METAOPT_DIR}/ already exists",
        )
    target.mkdir(parents=True, exist_ok=True)
    return BootstrapResult(
        mutation_id="B1",
        applied=True,
        already_ok=False,
        message=f"Created {_ML_METAOPT_DIR}/",
    )


def bootstrap_B2(cwd: Path) -> BootstrapResult:
    """Create all 8 required subdirectories inside ``.ml-metaopt/`` (idempotent)."""
    base = cwd / _ML_METAOPT_DIR
    created: list[str] = []
    for subdir in _REQUIRED_SUBDIRS:
        path = base / subdir
        if not path.is_dir():
            path.mkdir(parents=True, exist_ok=True)
            created.append(subdir)

    if not created:
        return BootstrapResult(
            mutation_id="B2",
            applied=False,
            already_ok=True,
            message="All 8 required subdirectories already exist",
        )
    return BootstrapResult(
        mutation_id="B2",
        applied=True,
        already_ok=False,
        message=f"Created {len(created)} subdirectories: {', '.join(created)}",
    )


def _gitignore_has_entry(content: str) -> bool:
    """Return True if any non-comment line matches ``.ml-metaopt/`` or ``.ml-metaopt``."""
    for line in content.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            if stripped in (_ML_METAOPT_DIR + "/", _ML_METAOPT_DIR):
                return True
    return False


def bootstrap_B3(cwd: Path) -> BootstrapResult:
    """Ensure ``.gitignore`` in *cwd* root contains ``.ml-metaopt/`` (idempotent)."""
    gitignore = cwd / ".gitignore"
    entry = f"{_ML_METAOPT_DIR}/\n"

    if not gitignore.is_file():
        try:
            gitignore.write_text(entry)
        except PermissionError as exc:
            return BootstrapResult(
                mutation_id="B3",
                applied=False,
                already_ok=False,
                message=f"Cannot write .gitignore: {exc}",
            )
        return BootstrapResult(
            mutation_id="B3",
            applied=True,
            already_ok=False,
            message="Created .gitignore with .ml-metaopt/ entry",
        )

    content = gitignore.read_text()
    if _gitignore_has_entry(content):
        return BootstrapResult(
            mutation_id="B3",
            applied=False,
            already_ok=True,
            message=".gitignore already contains .ml-metaopt/ entry",
        )

    try:
        with gitignore.open("a") as f:
            f.write(f"\n{entry}")
    except PermissionError as exc:
        return BootstrapResult(
            mutation_id="B3",
            applied=False,
            already_ok=False,
            message=f"Cannot write .gitignore: {exc}",
        )
    return BootstrapResult(
        mutation_id="B3",
        applied=True,
        already_ok=False,
        message="Appended .ml-metaopt/ to existing .gitignore",
    )


def run_all_repo_bootstrap(cwd: Path) -> list[BootstrapResult]:
    """Run B1, B2, B3 in order. Skips B2 if B1 failed. B3 always runs."""
    results: list[BootstrapResult] = []

    b1_ok = False
    try:
        r1 = bootstrap_B1(cwd)
        results.append(r1)
        b1_ok = r1.applied or r1.already_ok
    except Exception as exc:
        results.append(BootstrapResult("B1", applied=False, already_ok=False, message=f"B1 failed: {exc}"))

    if b1_ok:
        try:
            results.append(bootstrap_B2(cwd))
        except Exception as exc:
            results.append(BootstrapResult("B2", applied=False, already_ok=False, message=f"B2 failed: {exc}"))

    try:
        results.append(bootstrap_B3(cwd))
    except Exception as exc:
        results.append(BootstrapResult("B3", applied=False, already_ok=False, message=f"B3 failed: {exc}"))

    return results
