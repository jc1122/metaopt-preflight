"""Tests for scripts/_artifact_utils.py."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

# Allow importing scripts package from project root.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts._artifact_utils import (  # noqa: E402
    ARTIFACT_FILENAME,
    build_artifact,
    read_artifact,
    summarize_failures,
    write_artifact,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

# Shared test constants
_IDENTITY_HASH = "sha256:a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"
_RUNTIME_HASH = "sha256:f6e5d4c3b2a1f6e5d4c3b2a1f6e5d4c3b2a1f6e5d4c3b2a1f6e5d4c3b2a1f6e5"
_CAMPAIGN_ID = "test-campaign"


def _ready_artifact() -> dict:
    return build_artifact(
        campaign_identity_hash=_IDENTITY_HASH,
        runtime_config_hash=_RUNTIME_HASH,
        status="READY",
        failures=[],
        checks_summary={"total": 3, "passed": 2, "failed": 0, "bootstrapped": 1},
        diagnostics=None,
        campaign_id=_CAMPAIGN_ID,
        duration_seconds=5.2,
    )


def _failed_artifact() -> dict:
    failures = [
        {
            "check_id": "skypilot_installed",
            "category": "environment",
            "message": "SkyPilot CLI not found",
            "remediation": "pip install skypilot",
        },
        {
            "check_id": "wandb_credentials",
            "category": "environment",
            "message": "WANDB_API_KEY not set",
            "remediation": "export WANDB_API_KEY=...",
        },
    ]
    return build_artifact(
        campaign_identity_hash=_IDENTITY_HASH,
        runtime_config_hash=_RUNTIME_HASH,
        status="FAILED",
        failures=failures,
        checks_summary={"total": 3, "passed": 1, "failed": 2, "bootstrapped": 0},
        diagnostics="environment not ready",
        campaign_id=_CAMPAIGN_ID,
        duration_seconds=1.8,
    )


class TestBuildArtifact(unittest.TestCase):
    """build_artifact produces a correct artifact dict."""

    def test_schema_version(self) -> None:
        art = _ready_artifact()
        self.assertEqual(art["schema_version"], 1)

    def test_status_ready(self) -> None:
        art = _ready_artifact()
        self.assertEqual(art["status"], "READY")

    def test_status_failed(self) -> None:
        art = _failed_artifact()
        self.assertEqual(art["status"], "FAILED")

    def test_ready_next_action_is_proceed(self) -> None:
        art = _ready_artifact()
        self.assertEqual(art["next_action"], "proceed")

    def test_ready_failures_empty(self) -> None:
        art = _ready_artifact()
        self.assertEqual(art["failures"], [])

    def test_failed_next_action_not_proceed(self) -> None:
        art = _failed_artifact()
        self.assertNotEqual(art["next_action"], "proceed")
        self.assertIn("skypilot_installed", art["next_action"])
        self.assertIn("wandb_credentials", art["next_action"])

    def test_failed_failures_non_empty(self) -> None:
        art = _failed_artifact()
        self.assertEqual(len(art["failures"]), 2)

    def test_emitted_at_is_iso8601(self) -> None:
        art = _ready_artifact()
        self.assertTrue(art["emitted_at"].endswith("Z"))
        self.assertIn("T", art["emitted_at"])

    def test_checks_summary_fields(self) -> None:
        art = _ready_artifact()
        for key in ("total", "passed", "failed", "bootstrapped"):
            self.assertIn(key, art["checks_summary"])

    def test_invalid_status_raises(self) -> None:
        with self.assertRaises(ValueError):
            build_artifact(
                campaign_identity_hash=_IDENTITY_HASH,
                runtime_config_hash=_RUNTIME_HASH,
                status="INVALID",
                failures=[],
                checks_summary={"total": 0, "passed": 0, "failed": 0, "bootstrapped": 0},
                diagnostics=None,
                campaign_id=_CAMPAIGN_ID,
                duration_seconds=0.0,
            )

    def test_defensive_checks_summary(self) -> None:
        """Missing keys in checks_summary default to 0."""
        art = build_artifact(
            campaign_identity_hash=_IDENTITY_HASH,
            runtime_config_hash=_RUNTIME_HASH,
            status="READY",
            failures=[],
            checks_summary={},
            diagnostics=None,
            campaign_id=_CAMPAIGN_ID,
            duration_seconds=0.1,
        )
        self.assertEqual(art["checks_summary"]["total"], 0)


class TestWriteArtifact(unittest.TestCase):
    """write_artifact creates the file at the correct path."""

    def test_creates_file(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            state_dir = Path(td) / ".ml-metaopt"
            art = _ready_artifact()
            path = write_artifact(art, state_dir)
            self.assertTrue(path.exists())
            self.assertEqual(path.name, ARTIFACT_FILENAME)
            self.assertEqual(path.parent, state_dir)

    def test_creates_parent_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            state_dir = Path(td) / "nested" / "dir"
            path = write_artifact(_ready_artifact(), state_dir)
            self.assertTrue(path.exists())

    def test_overwrites_existing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            state_dir = Path(td)
            write_artifact(_ready_artifact(), state_dir)
            write_artifact(_failed_artifact(), state_dir)
            data = json.loads((state_dir / ARTIFACT_FILENAME).read_text(encoding="utf-8"))
            self.assertEqual(data["status"], "FAILED")


class TestReadArtifact(unittest.TestCase):
    """read_artifact reads and parses the artifact file."""

    def test_returns_none_for_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            self.assertIsNone(read_artifact(Path(td)))

    def test_returns_none_for_corrupt_json(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / ARTIFACT_FILENAME
            path.write_text("NOT JSON {{{", encoding="utf-8")
            self.assertIsNone(read_artifact(Path(td)))

    def test_returns_none_for_non_dict_json(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / ARTIFACT_FILENAME
            path.write_text("[1, 2, 3]", encoding="utf-8")
            self.assertIsNone(read_artifact(Path(td)))

    def test_round_trip(self) -> None:
        """write_artifact followed by read_artifact returns identical data."""
        with tempfile.TemporaryDirectory() as td:
            state_dir = Path(td)
            original = _ready_artifact()
            write_artifact(original, state_dir)
            loaded = read_artifact(state_dir)
            self.assertEqual(original, loaded)


class TestSummarizeFailures(unittest.TestCase):
    """summarize_failures produces human-readable guidance."""

    def test_empty_failures(self) -> None:
        self.assertEqual(summarize_failures([]), "proceed")

    def test_single_failure(self) -> None:
        result = summarize_failures([{"check_id": "foo"}])
        self.assertIn("1 failure", result)
        self.assertIn("foo", result)

    def test_multiple_failures(self) -> None:
        failures = [{"check_id": "a"}, {"check_id": "b"}, {"check_id": "c"}]
        result = summarize_failures(failures)
        self.assertIn("3 failures", result)

    def test_missing_check_id(self) -> None:
        result = summarize_failures([{}])
        self.assertIn("unknown", result)


class TestArtifactShapeMatchesFixture(unittest.TestCase):
    """Built artifact has the same top-level keys as the canonical fixture."""

    FIXTURE_PATH = FIXTURES_DIR / "example-readiness-artifact.json"

    def test_top_level_keys_match(self) -> None:
        fixture = json.loads(self.FIXTURE_PATH.read_text(encoding="utf-8"))
        art = _ready_artifact()
        self.assertEqual(sorted(fixture.keys()), sorted(art.keys()))

    def test_checks_summary_keys_match(self) -> None:
        fixture = json.loads(self.FIXTURE_PATH.read_text(encoding="utf-8"))
        art = _ready_artifact()
        self.assertEqual(
            sorted(fixture["checks_summary"].keys()),
            sorted(art["checks_summary"].keys()),
        )


if __name__ == "__main__":
    unittest.main()
