"""Tests for backend bootstrap — advisory-only guidance layer."""

from __future__ import annotations

from scripts.bootstrap.backend_bootstrap import (
    BackendBootstrapResult,
    guidance_skypilot,
    guidance_vast,
    guidance_wandb,
    guidance_repo_access,
    run_all_backend_bootstrap,
)
from scripts.checks.repo_checks import CheckResult


# ── Fixtures ────────────────────────────────────────────────────────────


def _passed(check_id: str = "skypilot_installed") -> CheckResult:
    return CheckResult(check_id=check_id, passed=True, message="OK")


def _failed(check_id: str = "skypilot_installed") -> CheckResult:
    return CheckResult(
        check_id=check_id,
        passed=False,
        message="not found",
        remediation="fix it",
    )


# ── guidance_skypilot ───────────────────────────────────────────────────


def test_guidance_skypilot_passed_not_actionable():
    result = guidance_skypilot(_passed("skypilot_installed"))
    assert result.actionable is False
    assert result.automated is False


def test_guidance_skypilot_failed_actionable_not_automated():
    result = guidance_skypilot(_failed("skypilot_installed"))
    assert result.actionable is True
    assert result.automated is False
    assert "skypilot" in result.guidance.lower() or "SkyPilot" in result.guidance


# ── guidance_wandb ──────────────────────────────────────────────────────


def test_guidance_wandb_always_not_automated():
    for cr in [_passed("wandb_credentials"), _failed("wandb_credentials")]:
        result = guidance_wandb(cr)
        assert result.automated is False


# ── run_all_backend_bootstrap ───────────────────────────────────────────


def test_run_all_returns_one_per_check():
    checks = [
        _passed("skypilot_installed"),
        _failed("vast_configured"),
        _passed("wandb_credentials"),
        _failed("repo_access"),
        _passed("smoke_test_command_nonempty"),
    ]
    results = run_all_backend_bootstrap(checks)
    assert len(results) == len(checks)
    assert all(isinstance(r, BackendBootstrapResult) for r in results)


def test_run_all_passed_checks_not_actionable():
    checks = [_passed("skypilot_installed"), _passed("wandb_credentials")]
    results = run_all_backend_bootstrap(checks)
    assert all(r.actionable is False for r in results)


def test_all_automated_fields_are_false():
    checks = [
        _passed("skypilot_installed"),
        _failed("vast_configured"),
        _passed("wandb_credentials"),
        _failed("repo_access"),
        _failed("smoke_test_command_nonempty"),
    ]
    results = run_all_backend_bootstrap(checks)
    assert all(r.automated is False for r in results)
