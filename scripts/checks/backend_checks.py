"""Backend readiness checks for metaopt-preflight.

Verifies SkyPilot + Vast.ai availability, WandB credentials,
project repo SSH/HTTPS access, and smoke_test_command presence.
All subprocess calls are timeout-guarded.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from scripts.checks.repo_checks import CheckResult


# ── Individual checks ───────────────────────────────────────────────────


def check_skypilot_installed() -> CheckResult:
    """Verify the ``sky`` CLI is available on PATH."""
    check_id = "skypilot_installed"
    try:
        result = subprocess.run(
            ["sky", "version"],
            capture_output=True,
            timeout=10,
        )
        if result.returncode == 0:
            return CheckResult(
                check_id=check_id,
                passed=True,
                message="SkyPilot is installed",
            )
        return CheckResult(
            check_id=check_id,
            passed=False,
            message="SkyPilot not found. Install with: pip install skypilot[vast]",
            remediation="pip install 'skypilot[vast]'",
        )
    except FileNotFoundError:
        return CheckResult(
            check_id=check_id,
            passed=False,
            message="SkyPilot not found. Install with: pip install skypilot[vast]",
            remediation="pip install 'skypilot[vast]'",
        )
    except subprocess.TimeoutExpired:
        return CheckResult(
            check_id=check_id,
            passed=False,
            message="SkyPilot version check timed out",
            remediation="pip install 'skypilot[vast]'",
        )


def check_vast_configured() -> CheckResult:
    """Verify Vast.ai is configured as a SkyPilot cloud provider."""
    check_id = "vast_configured"
    try:
        result = subprocess.run(
            ["sky", "check", "--cloud", "vast"],
            capture_output=True,
            timeout=30,
        )
        stdout = result.stdout.decode("utf-8", errors="replace")
        if result.returncode == 0 and "vastai" in stdout.lower():
            return CheckResult(
                check_id=check_id,
                passed=True,
                message="Vast.ai configured in SkyPilot",
            )
        return CheckResult(
            check_id=check_id,
            passed=False,
            message="Vast.ai cloud not configured in SkyPilot",
            remediation="Run: vast set api-key <your_key> && sky check",
        )
    except FileNotFoundError:
        return CheckResult(
            check_id=check_id,
            passed=False,
            message="Vast.ai cloud not configured in SkyPilot",
            remediation="Run: vast set api-key <your_key> && sky check",
        )
    except subprocess.TimeoutExpired:
        return CheckResult(
            check_id=check_id,
            passed=False,
            message="Vast.ai configuration check timed out",
            remediation="Run: vast set api-key <your_key> && sky check",
        )


def check_wandb_credentials(campaign: dict[str, Any]) -> CheckResult:
    """Verify WandB API credentials are available."""
    check_id = "wandb_credentials"

    # Check WANDB_API_KEY environment variable
    if os.environ.get("WANDB_API_KEY"):
        return CheckResult(
            check_id=check_id,
            passed=True,
            message="WandB credentials found (WANDB_API_KEY)",
        )

    # Check ~/.netrc for wandb entry
    netrc_path = Path.home() / ".netrc"
    try:
        if netrc_path.is_file():
            content = netrc_path.read_text(encoding="utf-8")
            if "api.wandb.ai" in content:
                return CheckResult(
                    check_id=check_id,
                    passed=True,
                    message="WandB credentials found (~/.netrc)",
                )
    except OSError:
        pass

    return CheckResult(
        check_id=check_id,
        passed=False,
        message="WandB credentials not found",
        remediation="Set WANDB_API_KEY or run: wandb login",
    )


def check_repo_access(campaign: dict[str, Any]) -> CheckResult:
    """Verify the project git repo is accessible."""
    check_id = "repo_access"

    repo_url = ""
    if isinstance(campaign, dict):
        project = campaign.get("project", {})
        if isinstance(project, dict):
            repo_url = project.get("repo", "") or ""

    if not repo_url:
        return CheckResult(
            check_id=check_id,
            passed=False,
            message="Cannot access git repo: project.repo not specified in campaign",
            remediation="Ensure repo URL is correct and SSH keys or tokens are configured",
        )

    try:
        result = subprocess.run(
            ["git", "ls-remote", "--exit-code", repo_url],
            capture_output=True,
            timeout=30,
        )
        if result.returncode == 0:
            return CheckResult(
                check_id=check_id,
                passed=True,
                message=f"Git repo accessible: {repo_url}",
            )
        return CheckResult(
            check_id=check_id,
            passed=False,
            message=f"Cannot access git repo: {repo_url}",
            remediation="Ensure repo URL is correct and SSH keys or tokens are configured",
        )
    except FileNotFoundError:
        return CheckResult(
            check_id=check_id,
            passed=False,
            message=f"Cannot access git repo: {repo_url}",
            remediation="Ensure repo URL is correct and SSH keys or tokens are configured",
        )
    except subprocess.TimeoutExpired:
        return CheckResult(
            check_id=check_id,
            passed=False,
            message=f"Git repo access check timed out: {repo_url}",
            remediation="Ensure repo URL is correct and SSH keys or tokens are configured",
        )


def check_smoke_test_command_nonempty(campaign: dict[str, Any]) -> CheckResult:
    """Verify smoke_test_command is a non-empty string (soft/warning check)."""
    check_id = "smoke_test_command_nonempty"

    smoke_cmd = ""
    if isinstance(campaign, dict):
        project = campaign.get("project", {})
        if isinstance(project, dict):
            smoke_cmd = project.get("smoke_test_command", "") or ""

    if isinstance(smoke_cmd, str) and smoke_cmd.strip():
        return CheckResult(
            check_id=check_id,
            passed=True,
            message="smoke_test_command is set",
            category="warning",
        )

    return CheckResult(
        check_id=check_id,
        passed=False,
        message="smoke_test_command not set — LOCAL_SANITY phase will skip validation",
        category="warning",
        remediation="Set project.smoke_test_command in the campaign YAML",
    )


# ── Aggregate runner ────────────────────────────────────────────────────


def run_all_backend_checks(campaign: dict[str, Any]) -> list[CheckResult]:
    """Run all backend readiness checks and return results.

    Catches exceptions per check so one failure does not prevent
    subsequent checks from running.
    """
    checks: list[tuple[str, Any]] = [
        ("skypilot_installed", lambda: check_skypilot_installed()),
        ("vast_configured", lambda: check_vast_configured()),
        ("wandb_credentials", lambda: check_wandb_credentials(campaign)),
        ("repo_access", lambda: check_repo_access(campaign)),
        ("smoke_test_command_nonempty", lambda: check_smoke_test_command_nonempty(campaign)),
    ]

    results: list[CheckResult] = []
    for check_id, fn in checks:
        try:
            results.append(fn())
        except Exception as exc:
            results.append(
                CheckResult(
                    check_id=check_id,
                    passed=False,
                    message=f"Check raised unexpected error: {exc}",
                    remediation="Review the error and retry",
                )
            )
    return results
