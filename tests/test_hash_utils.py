"""Tests for scripts/_hash_utils.py.

Validates that our hash computation matches the v4 orchestrator exactly,
handles edge cases defensively, and that the verify helper works.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import unittest
from typing import Any

# Make scripts importable
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

from _hash_utils import (
    compute_campaign_identity_hash,
    compute_runtime_config_hash,
    verify_hashes_match,
)

EXAMPLE_CAMPAIGN_PATH = os.path.join(
    os.sep, "home", "jakub", "projects",
    "ml-metaoptimization", "ml_metaopt_campaign.example.yaml",
)


# ── Inline replica of orchestrator logic (golden reference) ──────────

def _orchestrator_canonical_json(payload: Any) -> bytes:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def _orchestrator_sha256(payload: Any) -> str:
    return f"sha256:{hashlib.sha256(_orchestrator_canonical_json(payload)).hexdigest()}"


def _orchestrator_get_nested(data: dict[str, Any], path: tuple[str, ...]) -> Any:
    node: Any = data
    for key in path:
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    return node


def _orchestrator_identity_hash(campaign: dict[str, Any]) -> str:
    """Exact copy of ml-metaoptimization _identity_hash()."""
    payload = {
        "campaign_name": _orchestrator_get_nested(campaign, ("campaign", "name")),
        "objective": {
            "metric": _orchestrator_get_nested(campaign, ("objective", "metric")),
            "direction": _orchestrator_get_nested(campaign, ("objective", "direction")),
        },
        "wandb": {
            "entity": _orchestrator_get_nested(campaign, ("wandb", "entity")),
            "project": _orchestrator_get_nested(campaign, ("wandb", "project")),
        },
    }
    return _orchestrator_sha256(payload)


# ── Helpers ──────────────────────────────────────────────────────────

SAMPLE_CAMPAIGN: dict[str, Any] = {
    "campaign": {"name": "gnn-mnist-optimization", "description": "test"},
    "project": {
        "repo": "git@github.com:my-org/dg_image.git",
        "smoke_test_command": "python train.py --smoke --max-steps 10",
    },
    "wandb": {"entity": "my-wandb-entity", "project": "gnn-mnist-metaopt"},
    "compute": {
        "provider": "vast_ai",
        "accelerator": "A100:1",
        "num_sweep_agents": 4,
        "idle_timeout_minutes": 15,
        "max_budget_usd": 10,
    },
    "objective": {
        "metric": "val/accuracy",
        "direction": "maximize",
        "improvement_threshold": 0.005,
    },
    "proposal_policy": {"current_target": 5},
    "stop_conditions": {
        "max_iterations": 20,
        "target_metric": 0.990,
        "max_no_improve_iterations": 5,
    },
}


class TestCampaignIdentityHash(unittest.TestCase):
    """compute_campaign_identity_hash must match orchestrator exactly."""

    def test_matches_orchestrator_on_sample(self) -> None:
        ours = compute_campaign_identity_hash(SAMPLE_CAMPAIGN)
        theirs = _orchestrator_identity_hash(SAMPLE_CAMPAIGN)
        self.assertEqual(ours, theirs)

    def test_matches_orchestrator_on_example_yaml(self) -> None:
        try:
            import yaml
        except ImportError:
            self.skipTest("PyYAML not installed")
        if not os.path.exists(EXAMPLE_CAMPAIGN_PATH):
            self.skipTest("example campaign YAML not found")
        with open(EXAMPLE_CAMPAIGN_PATH) as fh:
            campaign = yaml.safe_load(fh)
        ours = compute_campaign_identity_hash(campaign)
        theirs = _orchestrator_identity_hash(campaign)
        self.assertEqual(ours, theirs)

    def test_different_names_produce_different_hashes(self) -> None:
        camp_a = {**SAMPLE_CAMPAIGN, "campaign": {"name": "alpha"}}
        camp_b = {**SAMPLE_CAMPAIGN, "campaign": {"name": "beta"}}
        self.assertNotEqual(
            compute_campaign_identity_hash(camp_a),
            compute_campaign_identity_hash(camp_b),
        )

    def test_hash_format(self) -> None:
        h = compute_campaign_identity_hash(SAMPLE_CAMPAIGN)
        self.assertTrue(h.startswith("sha256:"))
        hex_part = h.split(":", 1)[1]
        self.assertEqual(len(hex_part), 64)
        int(hex_part, 16)  # must be valid hex

    def test_missing_fields_no_crash(self) -> None:
        h = compute_campaign_identity_hash({})
        self.assertTrue(h.startswith("sha256:"))

    def test_non_dict_no_crash(self) -> None:
        for bad in (None, 42, [], "string"):
            h = compute_campaign_identity_hash(bad)  # type: ignore[arg-type]
            self.assertTrue(h.startswith("sha256:"))

    def test_compute_fields_do_not_affect_identity(self) -> None:
        base = compute_campaign_identity_hash(SAMPLE_CAMPAIGN)
        modified = {**SAMPLE_CAMPAIGN, "compute": {"provider": "aws", "accelerator": "T4:1"}}
        self.assertEqual(compute_campaign_identity_hash(modified), base)


class TestRuntimeConfigHash(unittest.TestCase):

    def test_basic_format(self) -> None:
        h = compute_runtime_config_hash(SAMPLE_CAMPAIGN)
        self.assertTrue(h.startswith("sha256:"))
        self.assertEqual(len(h.split(":", 1)[1]), 64)

    def test_compute_change_alters_hash(self) -> None:
        modified = {**SAMPLE_CAMPAIGN, "compute": {"provider": "aws"}}
        self.assertNotEqual(
            compute_runtime_config_hash(SAMPLE_CAMPAIGN),
            compute_runtime_config_hash(modified),
        )

    def test_missing_fields_no_crash(self) -> None:
        h = compute_runtime_config_hash({})
        self.assertTrue(h.startswith("sha256:"))

    def test_non_dict_no_crash(self) -> None:
        h = compute_runtime_config_hash(None)  # type: ignore[arg-type]
        self.assertTrue(h.startswith("sha256:"))

    def test_identity_vs_runtime_differ(self) -> None:
        self.assertNotEqual(
            compute_campaign_identity_hash(SAMPLE_CAMPAIGN),
            compute_runtime_config_hash(SAMPLE_CAMPAIGN),
        )


class TestVerifyHashesMatch(unittest.TestCase):

    def test_matching(self) -> None:
        h = compute_campaign_identity_hash(SAMPLE_CAMPAIGN)
        self.assertTrue(verify_hashes_match(h, h))

    def test_mismatch(self) -> None:
        self.assertFalse(verify_hashes_match("sha256:aaa", "sha256:bbb"))

    def test_non_string_inputs(self) -> None:
        self.assertFalse(verify_hashes_match(None, "sha256:abc"))  # type: ignore[arg-type]
        self.assertFalse(verify_hashes_match("sha256:abc", 123))  # type: ignore[arg-type]
        self.assertFalse(verify_hashes_match(None, None))  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
