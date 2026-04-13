"""Backend bootstrap — advisory-only remediation guidance.

Backend bootstrap never auto-installs SkyPilot, configures Vast.ai, or
stores credentials.  It maps each failed backend check to human-readable
guidance the operator can follow to reach a ready state.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from scripts.checks.repo_checks import CheckResult


@dataclass
class BackendBootstrapResult:
    action_id: str
    actionable: bool
    message: str
    guidance: str
    automated: bool = False  # Always False — backend bootstrap is advisory only


# ── Guidance helpers (one per backend check) ────────────────────────────


_GUIDANCE = {
    "skypilot_installed": (
        "ENV_SKYPILOT_GUIDANCE",
        "Install SkyPilot: pip install 'skypilot[vast]' then run: sky check",
    ),
    "vast_configured": (
        "ENV_VAST_GUIDANCE",
        "Get a Vast.ai API key, run: vast set api-key <YOUR_KEY>, then run: sky check",
    ),
    "wandb_credentials": (
        "ENV_WANDB_GUIDANCE",
        "Set WANDB_API_KEY env var or run: wandb login",
    ),
    "repo_access": (
        "ENV_REPO_GUIDANCE",
        "Ensure repo URL is correct and SSH keys or HTTPS tokens are configured",
    ),
    "smoke_test_command_nonempty": (
        "ENV_SMOKE_CMD_GUIDANCE",
        "Set project.smoke_test_command in the campaign YAML",
    ),
}


def _guidance_for(check_result: CheckResult) -> BackendBootstrapResult:
    """Generic dispatcher — returns pass-through or guidance."""
    action_id, guidance_text = _GUIDANCE.get(
        check_result.check_id,
        (f"ENV_{check_result.check_id.upper()}_GUIDANCE", check_result.remediation),
    )
    if check_result.passed:
        return BackendBootstrapResult(
            action_id=action_id,
            actionable=False,
            message=f"{check_result.check_id} OK",
            guidance="No action needed",
            automated=False,
        )
    return BackendBootstrapResult(
        action_id=action_id,
        actionable=True,
        message=check_result.message,
        guidance=guidance_text,
        automated=False,
    )


def guidance_skypilot(check_result: CheckResult) -> BackendBootstrapResult:
    """Emit guidance for SkyPilot installation."""
    return _guidance_for(check_result)


def guidance_vast(check_result: CheckResult) -> BackendBootstrapResult:
    """Emit guidance for Vast.ai configuration."""
    return _guidance_for(check_result)


def guidance_wandb(check_result: CheckResult) -> BackendBootstrapResult:
    """Emit guidance for WandB credentials."""
    return _guidance_for(check_result)


def guidance_repo_access(check_result: CheckResult) -> BackendBootstrapResult:
    """Emit guidance for project repo access."""
    return _guidance_for(check_result)


_GUIDANCE_DISPATCH: dict[str, Callable[[CheckResult], BackendBootstrapResult]] = {
    "skypilot_installed": guidance_skypilot,
    "vast_configured": guidance_vast,
    "wandb_credentials": guidance_wandb,
    "repo_access": guidance_repo_access,
}


# ── Aggregate runner ────────────────────────────────────────────────────


def run_all_backend_bootstrap(
    check_results: list[CheckResult],
) -> list[BackendBootstrapResult]:
    """Map every backend check result to advisory guidance.

    Returns one ``BackendBootstrapResult`` per input ``CheckResult``,
    in the same order.
    """
    return [
        _GUIDANCE_DISPATCH.get(cr.check_id, _guidance_for)(cr)
        for cr in check_results
    ]
