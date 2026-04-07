"""Validation tests for metaopt-preflight public contract docs.

These tests verify that the project's reference docs, SKILL.md, README.md,
and example fixtures stay aligned on the core public contract.
"""

import json
import os
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REFERENCES_DIR = os.path.join(PROJECT_ROOT, "references")
FIXTURES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")

CANONICAL_ARTIFACT_PATH = ".ml-metaopt/preflight-readiness.json"

REQUIRED_ARTIFACT_FIELDS = [
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
]

REQUIRED_CHECKS_SUMMARY_FIELDS = ["total", "passed", "failed", "bootstrapped"]


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


# ── Artifact path consistency ───────────────────────────────────────────


class TestArtifactPathConsistency(unittest.TestCase):
    """The canonical artifact path must appear in all relevant docs."""

    def test_readiness_artifact_doc_mentions_path(self):
        text = _read(os.path.join(REFERENCES_DIR, "readiness-artifact.md"))
        self.assertIn(
            CANONICAL_ARTIFACT_PATH,
            text,
            "readiness-artifact.md must reference the canonical artifact path",
        )

    def test_skill_md_mentions_artifact_path(self):
        text = _read(os.path.join(PROJECT_ROOT, "SKILL.md"))
        self.assertIn(
            CANONICAL_ARTIFACT_PATH,
            text,
            "SKILL.md must reference the canonical artifact path",
        )

    def test_boundary_md_mentions_artifact_path(self):
        text = _read(os.path.join(REFERENCES_DIR, "boundary.md"))
        self.assertIn(
            "readiness artifact",
            text.lower(),
            "boundary.md must mention the readiness artifact",
        )


# ── Hash field presence in contract docs ────────────────────────────────


class TestHashFieldsInContracts(unittest.TestCase):
    """campaign_identity_hash and runtime_config_hash must be documented."""

    def test_readiness_artifact_doc_has_campaign_identity_hash(self):
        text = _read(os.path.join(REFERENCES_DIR, "readiness-artifact.md"))
        self.assertIn("campaign_identity_hash", text)

    def test_readiness_artifact_doc_has_runtime_config_hash(self):
        text = _read(os.path.join(REFERENCES_DIR, "readiness-artifact.md"))
        self.assertIn("runtime_config_hash", text)

    def test_skill_md_has_campaign_identity_hash(self):
        text = _read(os.path.join(PROJECT_ROOT, "SKILL.md"))
        self.assertIn("campaign_identity_hash", text)

    def test_skill_md_has_runtime_config_hash(self):
        text = _read(os.path.join(PROJECT_ROOT, "SKILL.md"))
        self.assertIn("runtime_config_hash", text)


# ── One-shot lifecycle consistency ──────────────────────────────────────


class TestOneShotLifecycleConsistency(unittest.TestCase):
    """README, SKILL, and boundary docs must agree on one-shot semantics."""

    _ONE_SHOT_PHRASES = ["one-shot", "single invocation", "no resume"]

    def _assert_mentions_one_shot(self, path: str, label: str):
        text = _read(path).lower()
        found = any(phrase in text for phrase in self._ONE_SHOT_PHRASES)
        self.assertTrue(
            found,
            f"{label} must mention one-shot lifecycle "
            f"(looked for any of {self._ONE_SHOT_PHRASES})",
        )

    def test_readme_mentions_one_shot(self):
        self._assert_mentions_one_shot(
            os.path.join(PROJECT_ROOT, "README.md"), "README.md"
        )

    def test_skill_md_mentions_one_shot(self):
        self._assert_mentions_one_shot(
            os.path.join(PROJECT_ROOT, "SKILL.md"), "SKILL.md"
        )

    def test_boundary_md_mentions_one_shot(self):
        self._assert_mentions_one_shot(
            os.path.join(REFERENCES_DIR, "boundary.md"), "boundary.md"
        )

    def _assert_mentions_readiness_artifact(self, path: str, label: str):
        text = _read(path).lower()
        self.assertIn(
            "readiness artifact",
            text,
            f"{label} must mention the readiness artifact role",
        )

    def test_readme_mentions_readiness_artifact(self):
        self._assert_mentions_readiness_artifact(
            os.path.join(PROJECT_ROOT, "README.md"), "README.md"
        )

    def test_skill_mentions_readiness_artifact(self):
        self._assert_mentions_readiness_artifact(
            os.path.join(PROJECT_ROOT, "SKILL.md"), "SKILL.md"
        )

    def test_boundary_mentions_readiness_artifact(self):
        self._assert_mentions_readiness_artifact(
            os.path.join(REFERENCES_DIR, "boundary.md"), "boundary.md"
        )


# ── Reference set completeness ──────────────────────────────────────────


class TestReferenceSetCompleteness(unittest.TestCase):
    """Backend and repo setup contracts must exist in the references dir."""

    def test_backend_setup_reference_exists(self):
        path = os.path.join(REFERENCES_DIR, "backend-setup.md")
        self.assertTrue(os.path.isfile(path), "references/backend-setup.md must exist")

    def test_repo_setup_reference_exists(self):
        path = os.path.join(REFERENCES_DIR, "repo-setup.md")
        self.assertTrue(os.path.isfile(path), "references/repo-setup.md must exist")

    def test_readiness_artifact_reference_exists(self):
        path = os.path.join(REFERENCES_DIR, "readiness-artifact.md")
        self.assertTrue(
            os.path.isfile(path), "references/readiness-artifact.md must exist"
        )

    def test_boundary_reference_exists(self):
        path = os.path.join(REFERENCES_DIR, "boundary.md")
        self.assertTrue(os.path.isfile(path), "references/boundary.md must exist")

    def test_readme_references_backend_setup(self):
        text = _read(os.path.join(PROJECT_ROOT, "README.md"))
        self.assertIn("backend-setup.md", text)

    def test_readme_references_repo_setup(self):
        text = _read(os.path.join(PROJECT_ROOT, "README.md"))
        self.assertIn("repo-setup.md", text)


# ── Fixture validation ──────────────────────────────────────────────────


class TestReadinessArtifactFixture(unittest.TestCase):
    """Validate the example readiness artifact fixture has required fields."""

    FIXTURE_PATH = os.path.join(FIXTURES_DIR, "example-readiness-artifact.json")

    def test_fixture_exists(self):
        self.assertTrue(
            os.path.isfile(self.FIXTURE_PATH),
            "tests/fixtures/example-readiness-artifact.json must exist",
        )

    def test_fixture_is_valid_json(self):
        data = json.loads(_read(self.FIXTURE_PATH))
        self.assertIsInstance(data, dict)

    def test_fixture_has_all_required_top_level_fields(self):
        data = json.loads(_read(self.FIXTURE_PATH))
        for field in REQUIRED_ARTIFACT_FIELDS:
            self.assertIn(
                field,
                data,
                f"Fixture missing required field '{field}'",
            )

    def test_fixture_has_campaign_identity_hash(self):
        data = json.loads(_read(self.FIXTURE_PATH))
        value = data["campaign_identity_hash"]
        self.assertTrue(
            value.startswith("sha256:"),
            "campaign_identity_hash must start with 'sha256:'",
        )
        hex_part = value.split(":", 1)[1]
        self.assertEqual(len(hex_part), 64, "hash hex portion must be 64 chars")

    def test_fixture_has_runtime_config_hash(self):
        data = json.loads(_read(self.FIXTURE_PATH))
        value = data["runtime_config_hash"]
        self.assertTrue(
            value.startswith("sha256:"),
            "runtime_config_hash must start with 'sha256:'",
        )
        hex_part = value.split(":", 1)[1]
        self.assertEqual(len(hex_part), 64, "hash hex portion must be 64 chars")

    def test_fixture_checks_summary_fields(self):
        data = json.loads(_read(self.FIXTURE_PATH))
        summary = data["checks_summary"]
        for field in REQUIRED_CHECKS_SUMMARY_FIELDS:
            self.assertIn(field, summary, f"checks_summary missing '{field}'")

    def test_fixture_checks_summary_invariant(self):
        data = json.loads(_read(self.FIXTURE_PATH))
        s = data["checks_summary"]
        self.assertEqual(
            s["passed"] + s["failed"] + s["bootstrapped"],
            s["total"],
            "passed + failed + bootstrapped must equal total",
        )

    def test_fixture_status_is_valid(self):
        data = json.loads(_read(self.FIXTURE_PATH))
        self.assertIn(data["status"], ("READY", "FAILED"))

    def test_fixture_ready_has_empty_failures(self):
        data = json.loads(_read(self.FIXTURE_PATH))
        if data["status"] == "READY":
            self.assertEqual(data["failures"], [])

    def test_fixture_schema_version(self):
        data = json.loads(_read(self.FIXTURE_PATH))
        self.assertEqual(data["schema_version"], 1)


# ── README validation section ───────────────────────────────────────────


class TestReadmeValidationSection(unittest.TestCase):
    """README must include a validation section explaining how to run tests."""

    def test_readme_has_validation_section(self):
        text = _read(os.path.join(PROJECT_ROOT, "README.md"))
        self.assertIn(
            "## Validation",
            text,
            "README.md must contain a '## Validation' section",
        )

    def test_readme_mentions_test_command(self):
        text = _read(os.path.join(PROJECT_ROOT, "README.md"))
        self.assertIn(
            "python -m unittest",
            text,
            "README.md validation section must mention how to run tests",
        )


if __name__ == "__main__":
    unittest.main()
