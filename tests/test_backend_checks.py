"""Tests for backend readiness checks.

All subprocess and filesystem interactions are mocked — no real
``sky``, ``git``, or WandB commands are executed.
"""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path
from unittest import mock

from scripts.checks.backend_checks import (
    check_repo_access,
    check_skypilot_installed,
    check_smoke_test_command_nonempty,
    check_vast_configured,
    check_wandb_credentials,
    run_all_backend_checks,
)

SAMPLE_CAMPAIGN: dict = {
    "project": {
        "repo": "git@github.com:my-org/dg_image.git",
        "smoke_test_command": "python train.py --smoke --max-steps 10",
    },
    "wandb": {"entity": "my-entity", "project": "my-project"},
}


def _completed_process(
    returncode: int = 0, stdout: bytes = b"", stderr: bytes = b""
) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr
    )


# ── SkyPilot installed ──────────────────────────────────────────────────


class TestCheckSkypilotInstalled(unittest.TestCase):
    @mock.patch("scripts.checks.backend_checks.subprocess.run")
    def test_passes_when_sky_version_succeeds(self, mock_run: mock.MagicMock) -> None:
        mock_run.return_value = _completed_process(returncode=0, stdout=b"0.7.0")
        result = check_skypilot_installed()
        self.assertTrue(result.passed)
        self.assertEqual(result.check_id, "skypilot_installed")

    @mock.patch("scripts.checks.backend_checks.subprocess.run")
    def test_fails_when_sky_not_found(self, mock_run: mock.MagicMock) -> None:
        mock_run.side_effect = FileNotFoundError("sky not found")
        result = check_skypilot_installed()
        self.assertFalse(result.passed)
        self.assertIn("not found", result.message.lower())

    @mock.patch("scripts.checks.backend_checks.subprocess.run")
    def test_fails_when_nonzero_returncode(self, mock_run: mock.MagicMock) -> None:
        mock_run.return_value = _completed_process(returncode=1)
        result = check_skypilot_installed()
        self.assertFalse(result.passed)


# ── Vast.ai configured ─────────────────────────────────────────────────


class TestCheckVastConfigured(unittest.TestCase):
    @mock.patch("scripts.checks.backend_checks.subprocess.run")
    def test_passes_when_vastai_in_output(self, mock_run: mock.MagicMock) -> None:
        mock_run.return_value = _completed_process(
            returncode=0, stdout=b"vastai: enabled"
        )
        result = check_vast_configured()
        self.assertTrue(result.passed)
        self.assertEqual(result.check_id, "vast_configured")

    @mock.patch("scripts.checks.backend_checks.subprocess.run")
    def test_fails_when_vastai_not_in_output(self, mock_run: mock.MagicMock) -> None:
        mock_run.return_value = _completed_process(
            returncode=0, stdout=b"aws: enabled"
        )
        result = check_vast_configured()
        self.assertFalse(result.passed)

    @mock.patch("scripts.checks.backend_checks.subprocess.run")
    def test_fails_when_nonzero_returncode(self, mock_run: mock.MagicMock) -> None:
        mock_run.return_value = _completed_process(
            returncode=1, stdout=b"vastai: error"
        )
        result = check_vast_configured()
        self.assertFalse(result.passed)


# ── WandB credentials ──────────────────────────────────────────────────


class TestCheckWandbCredentials(unittest.TestCase):
    @mock.patch.dict("os.environ", {"WANDB_API_KEY": "secret123"})
    def test_passes_when_env_var_set(self) -> None:
        result = check_wandb_credentials(SAMPLE_CAMPAIGN)
        self.assertTrue(result.passed)
        self.assertEqual(result.check_id, "wandb_credentials")

    @mock.patch.dict("os.environ", {}, clear=True)
    @mock.patch("scripts.checks.backend_checks.Path.home")
    def test_passes_when_netrc_has_wandb(self, mock_home: mock.MagicMock) -> None:
        fake_home = Path("/fake/home")
        mock_home.return_value = fake_home
        netrc = fake_home / ".netrc"
        with mock.patch.object(Path, "is_file", return_value=True):
            with mock.patch.object(
                Path,
                "read_text",
                return_value="machine api.wandb.ai\n  login user\n  password token\n",
            ):
                result = check_wandb_credentials(SAMPLE_CAMPAIGN)
        self.assertTrue(result.passed)

    @mock.patch.dict("os.environ", {}, clear=True)
    @mock.patch("scripts.checks.backend_checks.Path.home")
    def test_fails_when_neither_env_nor_netrc(
        self, mock_home: mock.MagicMock
    ) -> None:
        fake_home = Path("/fake/home")
        mock_home.return_value = fake_home
        with mock.patch.object(Path, "is_file", return_value=False):
            result = check_wandb_credentials(SAMPLE_CAMPAIGN)
        self.assertFalse(result.passed)
        self.assertIn("not found", result.message.lower())


# ── Repo access ─────────────────────────────────────────────────────────


class TestCheckRepoAccess(unittest.TestCase):
    @mock.patch("scripts.checks.backend_checks.subprocess.run")
    def test_passes_when_ls_remote_succeeds(self, mock_run: mock.MagicMock) -> None:
        mock_run.return_value = _completed_process(returncode=0)
        result = check_repo_access(SAMPLE_CAMPAIGN)
        self.assertTrue(result.passed)
        self.assertEqual(result.check_id, "repo_access")

    @mock.patch("scripts.checks.backend_checks.subprocess.run")
    def test_fails_when_ls_remote_returns_128(self, mock_run: mock.MagicMock) -> None:
        mock_run.return_value = _completed_process(returncode=128)
        result = check_repo_access(SAMPLE_CAMPAIGN)
        self.assertFalse(result.passed)
        self.assertIn("cannot access", result.message.lower())


# ── Smoke test command ──────────────────────────────────────────────────


class TestCheckSmokeTestCommand(unittest.TestCase):
    def test_passes_when_command_set(self) -> None:
        result = check_smoke_test_command_nonempty(SAMPLE_CAMPAIGN)
        self.assertTrue(result.passed)

    def test_fails_when_command_empty(self) -> None:
        campaign = {"project": {"smoke_test_command": ""}}
        result = check_smoke_test_command_nonempty(campaign)
        self.assertFalse(result.passed)
        self.assertEqual(result.category, "warning")

    def test_fails_when_command_missing(self) -> None:
        campaign = {"project": {"repo": "git@github.com:x/y.git"}}
        result = check_smoke_test_command_nonempty(campaign)
        self.assertFalse(result.passed)


# ── Timeout handling ────────────────────────────────────────────────────


class TestTimeoutHandling(unittest.TestCase):
    @mock.patch("scripts.checks.backend_checks.subprocess.run")
    def test_skypilot_timeout_returns_failed(self, mock_run: mock.MagicMock) -> None:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="sky", timeout=10)
        result = check_skypilot_installed()
        self.assertFalse(result.passed)
        self.assertIn("timed out", result.message.lower())

    @mock.patch("scripts.checks.backend_checks.subprocess.run")
    def test_vast_timeout_returns_failed(self, mock_run: mock.MagicMock) -> None:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="sky", timeout=30)
        result = check_vast_configured()
        self.assertFalse(result.passed)
        self.assertIn("timed out", result.message.lower())

    @mock.patch("scripts.checks.backend_checks.subprocess.run")
    def test_repo_access_timeout_returns_failed(
        self, mock_run: mock.MagicMock
    ) -> None:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=30)
        result = check_repo_access(SAMPLE_CAMPAIGN)
        self.assertFalse(result.passed)
        self.assertIn("timed out", result.message.lower())


# ── Aggregate runner ────────────────────────────────────────────────────


class TestCheckVastConfiguredFileNotFound(unittest.TestCase):
    @mock.patch("scripts.checks.backend_checks.subprocess.run")
    def test_fails_when_sky_binary_not_found(self, mock_run: mock.MagicMock) -> None:
        mock_run.side_effect = FileNotFoundError("sky not found")
        result = check_vast_configured()
        self.assertFalse(result.passed)
        self.assertEqual(result.check_id, "vast_configured")
        self.assertIn("not configured", result.message.lower())


class TestCheckWandbNetrcOSError(unittest.TestCase):
    @mock.patch.dict("os.environ", {}, clear=True)
    @mock.patch("scripts.checks.backend_checks.Path.home")
    def test_falls_through_on_oserror_reading_netrc(
        self, mock_home: mock.MagicMock
    ) -> None:
        fake_home = Path("/fake/home")
        mock_home.return_value = fake_home
        with mock.patch.object(Path, "is_file", side_effect=OSError("disk error")):
            result = check_wandb_credentials(SAMPLE_CAMPAIGN)
        self.assertFalse(result.passed)
        self.assertIn("not found", result.message.lower())


class TestCheckRepoAccessMissingUrl(unittest.TestCase):
    def test_fails_when_repo_url_empty(self) -> None:
        campaign: dict = {"project": {"repo": ""}}
        result = check_repo_access(campaign)
        self.assertFalse(result.passed)
        self.assertIn("not specified", result.message.lower())

    def test_fails_when_project_missing(self) -> None:
        campaign: dict = {"wandb": {"entity": "e"}}
        result = check_repo_access(campaign)
        self.assertFalse(result.passed)
        self.assertIn("not specified", result.message.lower())


class TestCheckRepoAccessFileNotFound(unittest.TestCase):
    @mock.patch("scripts.checks.backend_checks.subprocess.run")
    def test_fails_when_git_binary_not_found(self, mock_run: mock.MagicMock) -> None:
        mock_run.side_effect = FileNotFoundError("git not found")
        result = check_repo_access(SAMPLE_CAMPAIGN)
        self.assertFalse(result.passed)
        self.assertIn("cannot access", result.message.lower())


# ── Aggregate runner ────────────────────────────────────────────────────


class TestRunAllBackendChecks(unittest.TestCase):
    @mock.patch("scripts.checks.backend_checks.subprocess.run")
    @mock.patch.dict("os.environ", {"WANDB_API_KEY": "key"})
    def test_returns_five_results(self, mock_run: mock.MagicMock) -> None:
        mock_run.return_value = _completed_process(
            returncode=0, stdout=b"vastai: enabled"
        )
        results = run_all_backend_checks(SAMPLE_CAMPAIGN)
        self.assertEqual(len(results), 5)
        ids = [r.check_id for r in results]
        self.assertIn("skypilot_installed", ids)
        self.assertIn("vast_configured", ids)
        self.assertIn("wandb_credentials", ids)
        self.assertIn("repo_access", ids)
        self.assertIn("smoke_test_command_nonempty", ids)

    @mock.patch("scripts.checks.backend_checks.check_smoke_test_command_nonempty")
    @mock.patch("scripts.checks.backend_checks.check_repo_access")
    @mock.patch("scripts.checks.backend_checks.check_wandb_credentials")
    @mock.patch("scripts.checks.backend_checks.check_vast_configured")
    @mock.patch("scripts.checks.backend_checks.check_skypilot_installed")
    def test_catches_unexpected_exception(
        self,
        mock_sky: mock.MagicMock,
        mock_vast: mock.MagicMock,
        mock_wandb: mock.MagicMock,
        mock_repo: mock.MagicMock,
        mock_smoke: mock.MagicMock,
    ) -> None:
        from scripts.checks.backend_checks import CheckResult as CR

        mock_sky.side_effect = RuntimeError("boom")
        mock_vast.return_value = CR("vast_configured", True, message="ok", category="backend")
        mock_wandb.return_value = CR("wandb_credentials", True, message="ok", category="backend")
        mock_repo.return_value = CR("repo_access", True, message="ok", category="backend")
        mock_smoke.return_value = CR("smoke_test_command_nonempty", True, message="ok", category="warning")

        results = run_all_backend_checks(SAMPLE_CAMPAIGN)
        self.assertEqual(len(results), 5)
        sky_result = [r for r in results if r.check_id == "skypilot_installed"][0]
        self.assertFalse(sky_result.passed)
        self.assertIn("unexpected error", sky_result.message.lower())


if __name__ == "__main__":
    unittest.main()
