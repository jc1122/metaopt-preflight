"""Cross-compatibility tests: preflight artifact consumed by orchestrator.

These tests import ``_evaluate_preflight`` and ``_identity_hash`` from the
sibling ``ml-metaoptimization`` repository.  They will only run in dev
environments where both repos are checked out side-by-side.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

# ── graceful skip when orchestrator repo is absent ───────────────────
_ORCHESTRATOR_ROOT = Path("/home/jakub/projects/ml-metaoptimization")
_HANDOFF_MODULE_PATH = _ORCHESTRATOR_ROOT / "scripts" / "load_campaign_handoff.py"
if not _HANDOFF_MODULE_PATH.exists():
    pytest.skip(
        "ml-metaoptimization repo not found; skipping cross-compat tests",
        allow_module_level=True,
    )


def _import_from_path(name: str, path: Path):
    """Import a module from an absolute file path without polluting sys.path."""
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# The orchestrator module imports _handoff_utils via a relative sys.path hack;
# pre-register it so the import inside load_campaign_handoff succeeds.
_ORCH_SCRIPTS = _ORCHESTRATOR_ROOT / "scripts"
_import_from_path("_guardrail_utils", _ORCH_SCRIPTS / "_guardrail_utils.py")
_import_from_path("_handoff_utils", _ORCH_SCRIPTS / "_handoff_utils.py")
_handoff_mod = _import_from_path("load_campaign_handoff", _HANDOFF_MODULE_PATH)

_evaluate_preflight = _handoff_mod._evaluate_preflight
_identity_hash = _handoff_mod._identity_hash

from scripts._artifact_utils import build_artifact, write_artifact  # noqa: E402
from scripts._hash_utils import compute_campaign_identity_hash  # noqa: E402

# ── helpers ──────────────────────────────────────────────────────────

SAMPLE_CAMPAIGN: dict = {
    "campaign": {"name": "test-campaign"},
    "objective": {"metric": "val_loss", "direction": "minimize", "improvement_threshold": 0.01},
    "wandb": {"entity": "test-entity", "project": "test-project"},
    "project": {"repo": "https://github.com/test/repo", "smoke_test_command": "echo ok"},
    "compute": {"provider": "vastai", "accelerator": "A100", "num_sweep_agents": 2, "max_budget_usd": 10},
    "proposal_policy": {"current_target": "bayesian"},
    "stop_conditions": {"max_iterations": 5, "max_no_improve_iterations": 3},
}

KNOWN_HASH = compute_campaign_identity_hash(SAMPLE_CAMPAIGN)

_CHECKS_SUMMARY = {"total": 3, "passed": 3, "failed": 0, "bootstrapped": 0, "warnings": 0}


def _make_artifact(status: str = "READY", campaign_hash: str = KNOWN_HASH) -> dict:
    return build_artifact(
        campaign_identity_hash=campaign_hash,
        runtime_config_hash="sha256:dummy",
        status=status,
        failures=[] if status == "READY" else [{"check_id": "smoke_test", "message": "boom"}],
        checks_summary=_CHECKS_SUMMARY,
        diagnostics=None,
        campaign_id="test-campaign",
        duration_seconds=1.5,
    )


# ── tests ────────────────────────────────────────────────────────────


class TestEvaluatePreflightCrossCompat:
    """Verify that preflight artifacts are correctly consumed by _evaluate_preflight."""

    def test_ready_artifact_returns_fresh_ready(self, tmp_path: Path) -> None:
        artifact = _make_artifact(status="READY")
        write_artifact(artifact, tmp_path)

        result = _evaluate_preflight(tmp_path, campaign_identity_hash=KNOWN_HASH)

        assert result["status"] == "fresh_ready"
        assert result["exists"] is True
        assert result["readable"] is True
        assert result["binding_fresh"] is True

    def test_failed_artifact_returns_fresh_failed(self, tmp_path: Path) -> None:
        artifact = _make_artifact(status="FAILED")
        write_artifact(artifact, tmp_path)

        result = _evaluate_preflight(tmp_path, campaign_identity_hash=KNOWN_HASH)

        assert result["status"] == "fresh_failed"
        assert result["exists"] is True
        assert result["readable"] is True
        assert result["binding_fresh"] is True
        assert len(result["failures"]) == 1

    def test_missing_artifact_returns_missing(self, tmp_path: Path) -> None:
        result = _evaluate_preflight(tmp_path, campaign_identity_hash=KNOWN_HASH)

        assert result["status"] == "missing"
        assert result["exists"] is False

    def test_hash_mismatch_returns_stale(self, tmp_path: Path) -> None:
        artifact = _make_artifact(status="READY", campaign_hash="sha256:aaaa")
        write_artifact(artifact, tmp_path)

        result = _evaluate_preflight(tmp_path, campaign_identity_hash="sha256:bbbb")

        assert result["status"] == "stale"
        assert result["binding_fresh"] is False

    def test_corrupt_json_returns_unreadable(self, tmp_path: Path) -> None:
        artifact_path = tmp_path / "preflight-readiness.json"
        artifact_path.write_text("NOT{{{VALID JSON", encoding="utf-8")

        result = _evaluate_preflight(tmp_path, campaign_identity_hash=KNOWN_HASH)

        assert result["status"] == "unreadable"
        assert result["exists"] is True
        assert result["readable"] is False

    def test_identity_hash_matches_orchestrator(self) -> None:
        preflight_hash = compute_campaign_identity_hash(SAMPLE_CAMPAIGN)
        orchestrator_hash = _identity_hash(SAMPLE_CAMPAIGN)

        assert preflight_hash == orchestrator_hash
