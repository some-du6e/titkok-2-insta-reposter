from __future__ import annotations

import json
import subprocess
import unittest
from unittest.mock import patch

from src.components.api import app
from src.components.system_update import SystemUpdateError, run_system_restart, run_system_update


def _completed_process(command: list[str], returncode: int = 0, stdout: str = "", stderr: str = ""):
    return subprocess.CompletedProcess(command, returncode, stdout=stdout, stderr=stderr)


class SystemUpdateServiceTestCase(unittest.TestCase):
    @patch("src.components.system_update.subprocess.Popen")
    def test_restart_only_requests_restart(self, mock_popen):
        result = run_system_restart()

        self.assertTrue(result["ok"])
        self.assertEqual(result["restart"]["command"], "sudo systemctl restart tiktok2instagram")
        mock_popen.assert_called_once()

    @patch("src.components.system_update.subprocess.Popen")
    @patch("src.components.system_update.subprocess.run")
    def test_clean_repo_pull_and_restart_succeed(self, mock_run, mock_popen):
        mock_run.side_effect = [
            _completed_process(["git", "status", "--porcelain"], stdout=""),
            _completed_process(["git", "pull"], stdout="Updating 123..456"),
        ]

        result = run_system_update()

        self.assertTrue(result["ok"])
        self.assertTrue(result["pull"]["updated"])
        self.assertEqual(result["restart"]["command"], "sudo systemctl restart tiktok2instagram")
        mock_popen.assert_called_once()

    @patch("src.components.system_update.subprocess.Popen")
    @patch("src.components.system_update.subprocess.run")
    def test_dirty_repo_hard_resets_before_pull(self, mock_run, mock_popen):
        mock_run.side_effect = [
            _completed_process(["git", "status", "--porcelain"], stdout=" M src/components/api.py\n"),
            _completed_process(["git", "reset", "--hard", "HEAD"], stdout="HEAD is now at abc123"),
            _completed_process(["git", "pull"], stdout="Already up to date."),
        ]

        result = run_system_update()

        self.assertTrue(result["ok"])
        self.assertFalse(result["pull"]["updated"])
        self.assertEqual(mock_run.call_args_list[1].args[0], ["git", "reset", "--hard", "HEAD"])
        mock_popen.assert_called_once()

    @patch("src.components.system_update.subprocess.run")
    def test_dirty_repo_reset_failure_returns_reset_stage(self, mock_run):
        mock_run.side_effect = [
            _completed_process(["git", "status", "--porcelain"], stdout=" M src/components/api.py\n"),
            _completed_process(["git", "reset", "--hard", "HEAD"], returncode=1, stderr="fatal: reset failed"),
        ]

        with self.assertRaises(SystemUpdateError) as error:
            run_system_update()

        self.assertEqual(error.exception.stage, "reset")
        self.assertIn("reset failed", error.exception.stderr)

    @patch("src.components.system_update.subprocess.run")
    def test_pull_failure_returns_pull_stage(self, mock_run):
        mock_run.side_effect = [
            _completed_process(["git", "status", "--porcelain"], stdout=""),
            _completed_process(["git", "pull"], returncode=1, stderr="fatal: no remote repository configured"),
        ]

        with self.assertRaises(SystemUpdateError) as error:
            run_system_update()

        self.assertEqual(error.exception.stage, "pull")
        self.assertIn("no remote repository", error.exception.stderr)

    @patch("src.components.system_update.subprocess.Popen", side_effect=FileNotFoundError("systemctl"))
    @patch("src.components.system_update.subprocess.run")
    def test_missing_systemctl_raises_restart_error_after_successful_pull(self, mock_run, _mock_popen):
        mock_run.side_effect = [
            _completed_process(["git", "status", "--porcelain"], stdout=""),
            _completed_process(["git", "pull"], stdout="Updating 123..456"),
        ]

        with self.assertRaises(SystemUpdateError) as error:
            run_system_update()

        self.assertEqual(error.exception.stage, "restart")
        self.assertIn("systemctl", error.exception.stderr)

    @patch("src.components.system_update.subprocess.run", side_effect=FileNotFoundError("git"))
    def test_missing_git_raises_status_error(self, mock_run):
        with self.assertRaises(SystemUpdateError) as error:
            run_system_update()

        self.assertEqual(error.exception.stage, "status")
        self.assertIn("git", error.exception.stderr)
        mock_run.assert_called_once()

    @patch("src.components.system_update.subprocess.Popen")
    @patch("src.components.system_update.subprocess.run")
    def test_already_up_to_date_still_requests_restart(self, mock_run, mock_popen):
        mock_run.side_effect = [
            _completed_process(["git", "status", "--porcelain"], stdout=""),
            _completed_process(["git", "pull"], stdout="Already up to date."),
        ]

        result = run_system_update()

        self.assertFalse(result["pull"]["updated"])
        mock_popen.assert_called_once()

    def test_second_update_attempt_is_rejected_while_lock_is_held(self):
        from src.components import system_update

        acquired = system_update._UPDATE_LOCK.acquire(blocking=False)
        self.assertTrue(acquired)
        self.addCleanup(system_update._UPDATE_LOCK.release)

        with self.assertRaises(SystemUpdateError) as error:
            run_system_update()

        self.assertEqual(error.exception.stage, "status")
        self.assertEqual(error.exception.status_code, 409)


class SystemUpdateApiTestCase(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    @patch("src.components.api.run_system_update")
    def test_update_endpoint_returns_success_payload(self, mock_run_system_update):
        mock_run_system_update.return_value = {
            "ok": True,
            "pull": {"updated": True, "stdout": "Updating", "stderr": ""},
            "restart": {"command": "sudo systemctl restart tiktok2instagram", "started": True},
            "message": "Update pulled. Restart requested.",
        }

        response = self.client.post(
            "/api/system/update",
            data=json.dumps({}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["restart"]["command"], "sudo systemctl restart tiktok2instagram")

    @patch("src.components.api.run_system_restart")
    def test_restart_endpoint_returns_success_payload(self, mock_run_system_restart):
        mock_run_system_restart.return_value = {
            "ok": True,
            "restart": {"command": "sudo systemctl restart tiktok2instagram", "started": True},
            "message": "Restart requested.",
        }

        response = self.client.post(
            "/api/system/restart",
            data=json.dumps({}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["restart"]["command"], "sudo systemctl restart tiktok2instagram")

    @patch("src.components.api.run_system_update")
    def test_update_endpoint_returns_structured_error(self, mock_run_system_update):
        mock_run_system_update.side_effect = SystemUpdateError(
            "Git pull failed.",
            stage="pull",
            stdout="",
            stderr="fatal: no remote repository configured",
        )

        response = self.client.post("/api/system/update")

        self.assertEqual(response.status_code, 500)
        payload = response.get_json()
        self.assertEqual(payload["stage"], "pull")
        self.assertIn("no remote repository", payload["stderr"])

    @patch("src.components.api.run_system_restart")
    def test_restart_endpoint_returns_structured_error(self, mock_run_system_restart):
        mock_run_system_restart.side_effect = SystemUpdateError(
            "Restart command failed to launch.",
            stage="restart",
            stdout="",
            stderr="permission denied",
        )

        response = self.client.post("/api/system/restart")

        self.assertEqual(response.status_code, 500)
        payload = response.get_json()
        self.assertEqual(payload["stage"], "restart")
        self.assertIn("permission denied", payload["stderr"])


if __name__ == "__main__":
    unittest.main()
