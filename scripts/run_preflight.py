#!/usr/bin/env python3
"""CLI entrypoint for metaopt-preflight: Gather → Evaluate → Bootstrap → Emit.

Usage:
    python scripts/run_preflight.py --campaign path/to/campaign.yaml [--cwd /project/root]

Exit codes: 0 = READY, 1 = FAILED, 2 = usage/input error.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

import yaml

try:
    from scripts._artifact_utils import build_artifact, write_artifact
    from scripts._hash_utils import (
        compute_campaign_identity_hash,
        compute_runtime_config_hash,
    )
    from scripts.bootstrap.backend_bootstrap import run_all_backend_bootstrap
    from scripts.bootstrap.repo_bootstrap import run_all_repo_bootstrap
    from scripts.checks.backend_checks import run_all_backend_checks
    from scripts.checks.repo_checks import CheckResult, run_all_repo_checks
except ImportError:
    # Direct script invocation: python3 scripts/run_preflight.py
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from scripts._artifact_utils import build_artifact, write_artifact
    from scripts._hash_utils import (
        compute_campaign_identity_hash,
        compute_runtime_config_hash,
    )
    from scripts.bootstrap.backend_bootstrap import run_all_backend_bootstrap
    from scripts.bootstrap.repo_bootstrap import run_all_repo_bootstrap
    from scripts.checks.backend_checks import run_all_backend_checks
    from scripts.checks.repo_checks import CheckResult, run_all_repo_checks

_STATE_DIR_NAME = ".ml-metaopt"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run metaopt-preflight readiness checks.",
    )
    parser.add_argument(
        "--campaign", required=True, help="Path to campaign YAML file"
    )
    parser.add_argument(
        "--cwd",
        default=".",
        help="Project root directory (default: current directory)",
    )
    return parser.parse_args(argv)


def _is_hard_failure(cr: CheckResult) -> bool:
    return not cr.passed and cr.category != "warning"


def _is_warning(cr: CheckResult) -> bool:
    return not cr.passed and cr.category == "warning"


def _extract_campaign_id(campaign: dict[str, Any]) -> str:
    """Extract campaign_id from campaign.name (nested) or campaign_name (flat)."""
    camp_block = campaign.get("campaign")
    if isinstance(camp_block, dict):
        name = camp_block.get("name")
        if name:
            return str(name)
    flat = campaign.get("campaign_name")
    if flat:
        return str(flat)
    return "unknown"


def _failure_record(cr: CheckResult) -> dict[str, str]:
    return {
        "check_id": cr.check_id,
        "category": cr.category,
        "message": cr.message,
        "remediation": cr.remediation,
    }


def run_preflight(
    campaign_path: Path,
    cwd: Path,
) -> int:
    """Execute the 4-phase preflight flow. Returns exit code."""
    start = time.monotonic()

    # ── Phase 1: Gather ──────────────────────────────────────────────
    if not campaign_path.is_file():
        print(f"Error: campaign file not found: {campaign_path}", file=sys.stderr)
        return 2

    try:
        raw = campaign_path.read_text(encoding="utf-8")
        campaign = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        print(f"Error: malformed campaign YAML: {exc}", file=sys.stderr)
        return 2

    if not isinstance(campaign, dict):
        print("Error: campaign YAML root must be a mapping", file=sys.stderr)
        return 2

    campaign_id = _extract_campaign_id(campaign)
    identity_hash = compute_campaign_identity_hash(campaign)
    runtime_hash = compute_runtime_config_hash(campaign)
    state_dir = cwd / _STATE_DIR_NAME

    # ── Phase 2: Evaluate ────────────────────────────────────────────
    repo_results = run_all_repo_checks(campaign, cwd)
    backend_results = run_all_backend_checks(campaign)

    repo_hard_fail_ids = {r.check_id for r in repo_results if _is_hard_failure(r)}
    backend_hard_fail_ids = {r.check_id for r in backend_results if _is_hard_failure(r)}
    warnings = [r for r in repo_results + backend_results if _is_warning(r)]

    # ── Phase 3: Bootstrap ───────────────────────────────────────────
    diagnostics_parts: list[str] = []
    bootstrapped_count = 0

    if repo_hard_fail_ids:
        try:
            bootstrap_results = run_all_repo_bootstrap(cwd)
            for br in bootstrap_results:
                if br.applied:
                    diagnostics_parts.append(br.message)
        except Exception as exc:
            diagnostics_parts.append(f"Repo bootstrap error: {exc}")

        # Re-run repo checks to see what got fixed
        repo_results = run_all_repo_checks(campaign, cwd)
        for r in repo_results:
            if r.check_id in repo_hard_fail_ids and r.passed:
                r.bootstrapped = True
                bootstrapped_count += 1

    # Backend bootstrap: advisory only (no auto-fix)
    if backend_hard_fail_ids:
        backend_guidance = run_all_backend_bootstrap(backend_results)
        for bg in backend_guidance:
            if bg.actionable:
                diagnostics_parts.append(f"{bg.action_id}: {bg.guidance}")

    # ── Phase 4: Emit ────────────────────────────────────────────────
    all_results = repo_results + backend_results

    remaining_hard_failures = [r for r in all_results if _is_hard_failure(r)]
    status = "READY" if not remaining_hard_failures else "FAILED"
    failures = [_failure_record(r) for r in remaining_hard_failures]

    total = len(all_results)
    passed_count = sum(1 for r in all_results if r.passed and not r.bootstrapped)
    failed_count = len(remaining_hard_failures)
    warning_count = len(warnings)

    if warnings:
        w_msgs = [f"{w.check_id}: {w.message}" for w in warnings]
        diagnostics_parts.append("Warnings: " + "; ".join(w_msgs))

    checks_summary = {
        "total": total,
        "passed": passed_count,
        "failed": failed_count,
        "bootstrapped": bootstrapped_count,
        "warnings": warning_count,
    }

    diagnostics = "; ".join(diagnostics_parts) if diagnostics_parts else None
    duration = time.monotonic() - start

    artifact = build_artifact(
        campaign_identity_hash=identity_hash,
        runtime_config_hash=runtime_hash,
        status=status,
        failures=failures,
        checks_summary=checks_summary,
        diagnostics=diagnostics,
        campaign_id=campaign_id,
        duration_seconds=round(duration, 2),
    )
    artifact_path = write_artifact(artifact, state_dir)

    # Summary output
    print(f"campaign_id: {campaign_id}")
    print(f"status:      {status}")
    print(f"total:       {total}")
    print(f"passed:      {passed_count}")
    print(f"failed:      {failed_count}")
    print(f"warnings:    {warning_count}")
    print(f"bootstrapped: {bootstrapped_count}")
    print(f"artifact:    {artifact_path}")

    return 0 if status == "READY" else 1


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    campaign_path = Path(args.campaign)
    cwd = Path(args.cwd).resolve()
    return run_preflight(campaign_path, cwd)


if __name__ == "__main__":
    raise SystemExit(main())
