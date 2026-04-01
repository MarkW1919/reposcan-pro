from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Launch a prepared RepoScan training run in a detached background process.")
    parser.add_argument("--run-manifest", required=True, help="Path to a prepared training run manifest JSON file.")
    parser.add_argument("--stdout-log", help="Optional stdout log path. Defaults to runtime/training/logs/<run>.stdout.log")
    parser.add_argument("--stderr-log", help="Optional stderr log path. Defaults to runtime/training/logs/<run>.stderr.log")
    parser.add_argument("--pid-file", help="Optional pid file path. Defaults to runtime/training/logs/<run>.pid")
    return parser.parse_args()


def _default_log_paths(repo_root: Path, run_name: str) -> tuple[Path, Path, Path]:
    logs_root = repo_root / "runtime" / "training" / "logs"
    logs_root.mkdir(parents=True, exist_ok=True)
    return (
        logs_root / f"{run_name}.stdout.log",
        logs_root / f"{run_name}.stderr.log",
        logs_root / f"{run_name}.pid",
    )


def _launch_command(command: list[str], *, cwd: Path, stdout_path: Path, stderr_path: Path) -> subprocess.Popen:
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    stdout_handle = stdout_path.open("ab")
    stderr_handle = stderr_path.open("ab")

    kwargs: dict[str, object] = {
        "cwd": str(cwd),
        "stdout": stdout_handle,
        "stderr": stderr_handle,
        "stdin": subprocess.DEVNULL,
        "close_fds": True,
        "env": {**os.environ, "PYTHONUNBUFFERED": "1"},
    }

    if sys.platform == "win32":
        kwargs["creationflags"] = (
            subprocess.CREATE_NEW_PROCESS_GROUP
            | subprocess.DETACHED_PROCESS
            | subprocess.CREATE_NO_WINDOW
        )
    else:
        kwargs["start_new_session"] = True

    try:
        return subprocess.Popen(command, **kwargs)
    except Exception:
        stdout_handle.close()
        stderr_handle.close()
        raise


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    run_manifest_path = Path(args.run_manifest)
    if not run_manifest_path.is_absolute():
        run_manifest_path = (repo_root / run_manifest_path).resolve()

    run_manifest = json.loads(run_manifest_path.read_text(encoding="utf-8"))
    run_name = str(run_manifest["run_name"])
    training_command = [str(token) for token in run_manifest.get("training_command", [])]
    if not training_command:
        raise ValueError(f"Run manifest '{run_manifest_path}' does not contain a training_command")

    default_stdout, default_stderr, default_pid = _default_log_paths(repo_root, run_name)
    stdout_path = Path(args.stdout_log) if args.stdout_log else default_stdout
    stderr_path = Path(args.stderr_log) if args.stderr_log else default_stderr
    pid_path = Path(args.pid_file) if args.pid_file else default_pid
    if not stdout_path.is_absolute():
        stdout_path = (repo_root / stdout_path).resolve()
    if not stderr_path.is_absolute():
        stderr_path = (repo_root / stderr_path).resolve()
    if not pid_path.is_absolute():
        pid_path = (repo_root / pid_path).resolve()

    process = _launch_command(training_command, cwd=repo_root, stdout_path=stdout_path, stderr_path=stderr_path)
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.write_text(str(process.pid), encoding="utf-8")

    print(f"Run name: {run_name}")
    print(f"PID: {process.pid}")
    print(f"Stdout: {stdout_path}")
    print(f"Stderr: {stderr_path}")
    print(f"PID file: {pid_path}")
    return 0


def _entrypoint() -> int:
    try:
        return main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(_entrypoint())
