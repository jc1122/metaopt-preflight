"""Cross-compatibility tests for the readiness artifact contract.

Local artifact-shape checks always run so schema drift is visible even when the
sibling ``ml-metaoptimization`` repository is absent. Direct consumption tests
against the orchestrator import lazily and skip explicitly only when the
required sibling checkout is unavailable.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


def _import_from_path(name: str, path: Path):
    """Import a module from an absolute file path without polluting sys.path."""
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot import {name} from {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


from scripts._artifact_utils import build_artifact, write_artifact  # noqa: E402
from scripts._hash_utils import compute_campaign_identity_hash  # noqa: E402

# ── helpers ──────────────────────────────────────────────────────────

_ORCHESTRATOR_ROOT = Path("/home/jakub/projects/ml-metaoptimization")
_ORCH_SCRIPTS = _ORCHESTRATOR_ROOT / "scripts"
_ORCHESTRATOR_REQUIRED_PATHS = (
    _ORCH_SCRIPTS / "_guardrail_utils.py",
    _ORCH_SCRIPTS / "_handoff_utils.py",
    _ORCH_SCRIPTS / "load_campaign_handoff.py",
)
_MISSING_ORCHESTRATOR_PATHS = [
    path for path in _ORCHESTRATOR_REQUIRED_PATHS if not path.exists()
]
_ORCHESTRATOR_SKIP_REASON = (
    "ml-metaoptimization checkout not available for orchestrator cross-compat tests; "
    f"missing: {', '.join(str(path) for path in _MISSING_ORCHESTRATOR_PATHS)}"
)
_FIXTURE_ARTIFACT_PATH = Path(__file__).parent / "fixtures" / "example-readiness-artifact.json"
_REQUIRED_ARTIFACT_KEYS = {
    "schema_version",
    "status",
    "campaign_id",
    "campaign_identity_hash",
    "runtime_config_hash",
    "emitted_at",
    "preflight_duration_seconds",
    "checks_summary",
    "failures",
    "next_action",
    "diagnostics",
}
_REQUIRED_CHECK_SUMMARY_KEYS = {
    "total",
    "passed",
    "failed",
    "bootstrapped",
    "warnings",
}

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


def _load_fixture_artifact() -> dict:
    return json.loads(_FIXTURE_ARTIFACT_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def orchestrator_api():
    """Import sibling orchestrator helpers only when the checkout is present."""
    if _MISSING_ORCHESTRATOR_PATHS:
        pytest.skip(_ORCHESTRATOR_SKIP_REASON)

    # The orchestrator module imports _handoff_utils via a relative sys.path hack;
    # pre-register it so the import inside load_campaign_handoff succeeds.
    _import_from_path("_guardrail_utils", _ORCH_SCRIPTS / "_guardrail_utils.py")
    _import_from_path("_handoff_utils", _ORCH_SCRIPTS / "_handoff_utils.py")
    handoff_mod = _import_from_path(
        "load_campaign_handoff",
        _ORCH_SCRIPTS / "load_campaign_handoff.py",
    )
    return handoff_mod._evaluate_preflight, handoff_mod._identity_hash


# ── tests ────────────────────────────────────────────────────────────


class TestLocalArtifactSchemaCompatibility:
    """Schema-sensitive checks that must run even without the sibling repo."""

    def test_example_fixture_matches_required_artifact_shape(self) -> None:
        artifact = _load_fixture_artifact()

        assert artifact["schema_version"] == 1
        assert artifact["status"] in {"READY", "FAILED"}
        assert _REQUIRED_ARTIFACT_KEYS <= set(artifact)
        assert _REQUIRED_CHECK_SUMMARY_KEYS <= set(artifact["checks_summary"])

    def test_build_artifact_matches_fixture_shape(self) -> None:
        fixture = _load_fixture_artifact()
        artifact = _make_artifact()

        assert set(artifact) == set(fixture)
        assert set(artifact["checks_summary"]) == set(fixture["checks_summary"])


class TestEvaluatePreflightCrossCompat:
    """Verify that preflight artifacts are correctly consumed by _evaluate_preflight."""

    def test_ready_artifact_returns_fresh_ready(
        self,
        tmp_path: Path,
        orchestrator_api,
    ) -> None:
        evaluate_preflight, _ = orchestrator_api
        artifact = _make_artifact(status="READY")
        write_artifact(artifact, tmp_path)

        result = evaluate_preflight(tmp_path, campaign_identity_hash=KNOWN_HASH)

        assert result["status"] == "fresh_ready"
        assert result["exists"] is True
        assert result["readable"] is True
        assert result["binding_fresh"] is True

    def test_failed_artifact_returns_fresh_failed(
        self,
        tmp_path: Path,
        orchestrator_api,
    ) -> None:
        evaluate_preflight, _ = orchestrator_api
        artifact = _make_artifact(status="FAILED")
        write_artifact(artifact, tmp_path)

        result = evaluate_preflight(tmp_path, campaign_identity_hash=KNOWN_HASH)

        assert result["status"] == "fresh_failed"
        assert result["exists"] is True
        assert result["readable"] is True
        assert result["binding_fresh"] is True
        assert len(result["failures"]) == 1

    def test_missing_artifact_returns_missing(
        self,
        tmp_path: Path,
        orchestrator_api,
    ) -> None:
        evaluate_preflight, _ = orchestrator_api
        result = evaluate_preflight(tmp_path, campaign_identity_hash=KNOWN_HASH)

        assert result["status"] == "missing"
        assert result["exists"] is False

    def test_hash_mismatch_returns_stale(
        self,
        tmp_path: Path,
        orchestrator_api,
    ) -> None:
        evaluate_preflight, _ = orchestrator_api
        artifact = _make_artifact(status="READY", campaign_hash="sha256:aaaa")
        write_artifact(artifact, tmp_path)

        result = evaluate_preflight(tmp_path, campaign_identity_hash="sha256:bbbb")

        assert result["status"] == "stale"
        assert result["binding_fresh"] is False

    def test_corrupt_json_returns_unreadable(
        self,
        tmp_path: Path,
        orchestrator_api,
    ) -> None:
        evaluate_preflight, _ = orchestrator_api
        artifact_path = tmp_path / "preflight-readiness.json"
        artifact_path.write_text("NOT{{{VALID JSON", encoding="utf-8")

        result = evaluate_preflight(tmp_path, campaign_identity_hash=KNOWN_HASH)

        assert result["status"] == "unreadable"
        assert result["exists"] is True
        assert result["readable"] is False

    def test_identity_hash_matches_orchestrator(self, orchestrator_api) -> None:
        _, identity_hash = orchestrator_api
        preflight_hash = compute_campaign_identity_hash(SAMPLE_CAMPAIGN)
        orchestrator_hash = identity_hash(SAMPLE_CAMPAIGN)

        assert preflight_hash == orchestrator_hash
