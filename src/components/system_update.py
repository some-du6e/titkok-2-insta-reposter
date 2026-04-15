from __future__ import annotations

import subprocess
import sys
import threading
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
REQUIREMENTS_PATH = REPO_ROOT / "requirements.txt"
RESTART_COMMAND = ["sudo", "systemctl", "restart", "tiktok2instagram"]
_UPDATE_LOCK = threading.Lock()


class SystemUpdateError(Exception):
    def __init__(
        self,
        message: str,
        *,
        stage: str,
        stdout: str = "",
        stderr: str = "",
        status_code: int = 500,
    ) -> None:
        super().__init__(message)
        self.stage = stage
        self.stdout = stdout
        self.stderr = stderr
        self.status_code = status_code


def _run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _normalize_output(value: str | None) -> str:
    return value.strip() if isinstance(value, str) else ""


def _build_git_status_failure_message(stdout: str, stderr: str) -> str:
    combined = f"{stdout}\n{stderr}".lower()

    if "dubious ownership" in combined and "safe.directory" in combined:
        return (
            "Failed to inspect git status before updating. "
            f"Git does not trust this repo path. Run "
            f'`git config --global --add safe.directory "{REPO_ROOT}"` and try again.'
        )

    if "index.lock" in combined:
        return (
            "Failed to inspect git status before updating. "
            "A stale git lock file is blocking access. Close any other git process and remove `.git/index.lock` if it is left behind."
        )

    if "not a git repository" in combined:
        return (
            "Failed to inspect git status before updating. "
            "This app is not running from a git clone, so in-app updates are unavailable."
        )

    return "Failed to inspect git status before updating."


def _raise_command_error(
    *,
    message: str,
    stage: str,
    completed_process: subprocess.CompletedProcess[str] | None = None,
    stderr: str = "",
) -> None:
    stdout = _normalize_output(completed_process.stdout) if completed_process else ""
    final_stderr = _normalize_output(stderr) or (
        _normalize_output(completed_process.stderr) if completed_process else ""
    )
    raise SystemUpdateError(
        message,
        stage=stage,
        stdout=stdout,
        stderr=final_stderr,
    )


def _launch_restart() -> dict:
    creationflags = 0
    for flag_name in ("DETACHED_PROCESS", "CREATE_NEW_PROCESS_GROUP"):
        creationflags |= int(getattr(subprocess, flag_name, 0))

    try:
        subprocess.Popen(
            RESTART_COMMAND,
            cwd=REPO_ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=creationflags,
        )
    except FileNotFoundError as exc:
        raise SystemUpdateError(
            "Restart command failed: pyker was not found on PATH.",
            stage="restart",
            stderr=str(exc),
        ) from exc
    except OSError as exc:
        raise SystemUpdateError(
            "Restart command failed to launch.",
            stage="restart",
            stderr=str(exc),
        ) from exc

    return {
        "command": " ".join(RESTART_COMMAND),
        "started": True,
    }


def _pull_updated(stdout: str, stderr: str) -> bool:
    combined = f"{stdout}\n{stderr}".lower()
    return "already up to date" not in combined and "already up-to-date" not in combined


def _install_requirements() -> subprocess.CompletedProcess[str]:
    command = [sys.executable, "-m", "pip", "install", "-r", str(REQUIREMENTS_PATH)]
    return _run_command(command)


def run_system_restart() -> dict:
    restart = _launch_restart()
    return {
        "ok": True,
        "restart": restart,
        "message": "Restart requested.",
    }


def run_system_update() -> dict:
    if not _UPDATE_LOCK.acquire(blocking=False):
        raise SystemUpdateError(
            "An update is already in progress.",
            stage="status",
            status_code=409,
        )

    try:
        try:
            status_result = _run_command(["git", "status", "--porcelain"])
        except FileNotFoundError as exc:
            raise SystemUpdateError(
                "Git is not installed or not available on PATH.",
                stage="status",
                stderr=str(exc),
            ) from exc

        if status_result.returncode != 0:
            _raise_command_error(
                message=_build_git_status_failure_message(
                    _normalize_output(status_result.stdout),
                    _normalize_output(status_result.stderr),
                ),
                stage="status",
                completed_process=status_result,
            )

        if _normalize_output(status_result.stdout):
            try:
                reset_result = _run_command(["git", "reset", "--hard", "HEAD"])
            except FileNotFoundError as exc:
                raise SystemUpdateError(
                    "Git is not installed or not available on PATH.",
                    stage="reset",
                    stderr=str(exc),
                ) from exc

            if reset_result.returncode != 0:
                _raise_command_error(
                    message="Failed to hard reset local changes before pulling.",
                    stage="reset",
                    completed_process=reset_result,
                )

        try:
            pull_result = _run_command(["git", "pull"])
        except FileNotFoundError as exc:
            raise SystemUpdateError(
                "Git is not installed or not available on PATH.",
                stage="pull",
                stderr=str(exc),
            ) from exc

        if pull_result.returncode != 0:
            _raise_command_error(
                message="Git pull failed.",
                stage="pull",
                completed_process=pull_result,
            )

        install_result = _install_requirements()
        if install_result.returncode != 0:
            _raise_command_error(
                message="Failed to install Python dependencies from requirements.txt.",
                stage="install",
                completed_process=install_result,
            )

        restart = _launch_restart()
        pull_stdout = _normalize_output(pull_result.stdout)
        pull_stderr = _normalize_output(pull_result.stderr)
        install_stdout = _normalize_output(install_result.stdout)
        install_stderr = _normalize_output(install_result.stderr)
        return {
            "ok": True,
            "pull": {
                "updated": _pull_updated(pull_stdout, pull_stderr),
                "stdout": pull_stdout,
                "stderr": pull_stderr,
            },
            "install": {
                "command": f"{sys.executable} -m pip install -r {REQUIREMENTS_PATH}",
                "stdout": install_stdout,
                "stderr": install_stderr,
            },
            "restart": restart,
            "message": "Update pulled, dependencies installed. Restart requested.",
        }
    finally:
        _UPDATE_LOCK.release()
