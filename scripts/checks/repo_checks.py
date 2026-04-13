"""Repository readiness checks R1–R9 for metaopt-preflight."""

from __future__ import annotations

import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass
class CheckResult:
    check_id: str
    passed: bool
    message: str
    category: str = "backend"
    remediation: str = ""
    bootstrapped: bool = False


REQUIRED_TOP_LEVEL_KEYS = frozenset(
    {"campaign_name", "objective", "wandb", "compute", "project", "search_space"}
)

_ML_METAOPT_DIR = ".ml-metaopt"


# ── Individual checks ────────────────────────────────────────────────


def check_R1(campaign: dict, cwd: Path) -> CheckResult:
    """.ml-metaopt/ directory exists."""
    path = cwd / _ML_METAOPT_DIR
    if path.is_dir():
        return CheckResult("R1", True, f"{_ML_METAOPT_DIR}/ directory exists")
    return CheckResult(
        "R1",
        False,
        f"{_ML_METAOPT_DIR}/ directory is missing",
        f"Create the directory: mkdir -p {_ML_METAOPT_DIR}",
    )


def check_R2(campaign: dict, cwd: Path) -> CheckResult:
    """.ml-metaopt/.gitignore exists and contains '.ml-metaopt/'."""
    gitignore = cwd / _ML_METAOPT_DIR / ".gitignore"
    if not gitignore.is_file():
        return CheckResult(
            "R2",
            False,
            f"{_ML_METAOPT_DIR}/.gitignore is missing",
            f"Create {_ML_METAOPT_DIR}/.gitignore containing '{_ML_METAOPT_DIR}/'",
        )
    content = gitignore.read_text()
    # Check that at least one non-comment, non-blank line matches
    for line in content.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and _ML_METAOPT_DIR + "/" in stripped:
            return CheckResult(
                "R2", True, f"{_ML_METAOPT_DIR}/.gitignore exists and contains required entry"
            )
    return CheckResult(
        "R2",
        False,
        f"{_ML_METAOPT_DIR}/.gitignore exists but does not contain '{_ML_METAOPT_DIR}/'",
        f"Add '{_ML_METAOPT_DIR}/' to {_ML_METAOPT_DIR}/.gitignore",
    )


def check_R3(campaign: dict, cwd: Path) -> CheckResult:
    """handoffs/ subdir exists inside .ml-metaopt/."""
    path = cwd / _ML_METAOPT_DIR / "handoffs"
    if path.is_dir():
        return CheckResult("R3", True, f"{_ML_METAOPT_DIR}/handoffs/ exists")
    return CheckResult(
        "R3",
        False,
        f"{_ML_METAOPT_DIR}/handoffs/ is missing",
        f"Create the directory: mkdir -p {_ML_METAOPT_DIR}/handoffs",
    )


def check_R4(campaign: dict, cwd: Path) -> CheckResult:
    """worker-results/ subdir exists inside .ml-metaopt/."""
    path = cwd / _ML_METAOPT_DIR / "worker-results"
    if path.is_dir():
        return CheckResult("R4", True, f"{_ML_METAOPT_DIR}/worker-results/ exists")
    return CheckResult(
        "R4",
        False,
        f"{_ML_METAOPT_DIR}/worker-results/ is missing",
        f"Create the directory: mkdir -p {_ML_METAOPT_DIR}/worker-results",
    )


def check_R5(campaign: dict, cwd: Path) -> CheckResult:
    """tasks/ and executor-events/ exist inside .ml-metaopt/."""
    missing: list[str] = []
    for subdir in ("tasks", "executor-events"):
        if not (cwd / _ML_METAOPT_DIR / subdir).is_dir():
            missing.append(subdir)
    if not missing:
        return CheckResult("R5", True, f"{_ML_METAOPT_DIR}/tasks/ and executor-events/ exist")
    return CheckResult(
        "R5",
        False,
        f"Missing subdirectories in {_ML_METAOPT_DIR}/: {', '.join(missing)}",
        "Create missing directories: "
        + " ".join(f"mkdir -p {_ML_METAOPT_DIR}/{d}" for d in missing),
    )


def check_R6(campaign: dict, cwd: Path) -> CheckResult:
    """artifacts/code/, artifacts/data/, artifacts/manifests/, artifacts/patches/ all exist."""
    subdirs = ("artifacts/code", "artifacts/data", "artifacts/manifests", "artifacts/patches")
    missing: list[str] = []
    for subdir in subdirs:
        if not (cwd / _ML_METAOPT_DIR / subdir).is_dir():
            missing.append(subdir)
    if not missing:
        return CheckResult("R6", True, f"All {_ML_METAOPT_DIR}/artifacts/ subdirectories exist")
    return CheckResult(
        "R6",
        False,
        f"Missing artifact subdirectories in {_ML_METAOPT_DIR}/: {', '.join(missing)}",
        "Create missing directories: "
        + " ".join(f"mkdir -p {_ML_METAOPT_DIR}/{d}" for d in missing),
    )


def check_R7(campaign: dict, cwd: Path) -> CheckResult:
    """smoke_test_command in campaign YAML is a non-empty string (syntax only)."""
    project = campaign.get("project")
    if not isinstance(project, dict):
        return CheckResult(
            "R7",
            False,
            "Campaign YAML missing 'project' section (needed for smoke_test_command)",
            "Add a 'project' section with a 'smoke_test_command' string to the campaign YAML",
        )
    cmd = project.get("smoke_test_command")
    if isinstance(cmd, str) and cmd.strip():
        return CheckResult("R7", True, "smoke_test_command is present and non-empty")
    return CheckResult(
        "R7",
        False,
        "smoke_test_command is missing or empty",
        "Set project.smoke_test_command to a valid shell command string",
    )


def check_R8(campaign: dict, cwd: Path) -> CheckResult:
    """Campaign YAML has required top-level keys."""
    present = set(campaign.keys())
    missing = REQUIRED_TOP_LEVEL_KEYS - present
    if not missing:
        return CheckResult("R8", True, "All required top-level campaign keys are present")
    sorted_missing = sorted(missing)
    return CheckResult(
        "R8",
        False,
        f"Missing required top-level keys: {', '.join(sorted_missing)}",
        f"Add the following keys to the campaign YAML: {', '.join(sorted_missing)}",
    )


def check_R9(campaign: dict, cwd: Path) -> CheckResult:
    """project.repo is a non-empty string."""
    project = campaign.get("project")
    if not isinstance(project, dict):
        return CheckResult(
            "R9",
            False,
            "Campaign YAML missing 'project' section (needed for project.repo)",
            "Add a 'project' section with a 'repo' string to the campaign YAML",
        )
    repo = project.get("repo")
    if isinstance(repo, str) and repo.strip():
        return CheckResult("R9", True, "project.repo is present and non-empty")
    return CheckResult(
        "R9",
        False,
        "project.repo is missing or empty",
        "Set project.repo to the repository URL or path",
    )


# ── Runner ───────────────────────────────────────────────────────────

_ALL_CHECKS: list[Callable[[dict, Path], CheckResult]] = [
    check_R1,
    check_R2,
    check_R3,
    check_R4,
    check_R5,
    check_R6,
    check_R7,
    check_R8,
    check_R9,
]


def run_all_repo_checks(campaign: dict, cwd: Path) -> list[CheckResult]:
    """Run R1–R9 in order. Returns all results (not just failures).

    If a check raises an exception it becomes a failed CheckResult
    with the exception message.
    """
    results: list[CheckResult] = []
    for check_fn in _ALL_CHECKS:
        check_id = check_fn.__name__.replace("check_", "")
        try:
            results.append(check_fn(campaign, cwd))
        except Exception as exc:
            results.append(
                CheckResult(
                    check_id=check_id,
                    passed=False,
                    message=f"Check {check_id} raised an exception: {exc}",
                    remediation="Investigate the exception and fix the underlying issue",
                )
            )
    return results
