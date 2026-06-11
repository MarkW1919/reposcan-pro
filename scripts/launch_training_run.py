from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Launch a prepared RepoScan training run, streaming to this terminal by default."
    )
    parser.add_argument("--run-manifest", required=True, help="Path to a prepared training run manifest JSON file.")
    parser.add_argument("--stdout-log", help="Optional stdout log path. Defaults to runtime/training/logs/<run>.stdout.log")
    parser.add_argument("--stderr-log", help="Optional stderr log path. Defaults to runtime/training/logs/<run>.stderr.log")
    parser.add_argument("--pid-file", help="Optional pid file path. Defaults to runtime/training/logs/<run>.pid")
    parser.add_argument(
        "--detached",
        action="store_true",
        help="Launch the training command in the background instead of streaming it in this terminal.",
    )
    parser.add_argument("--monitor-run", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args()


def _default_log_paths(repo_root: Path, run_name: str) -> tuple[Path, Path, Path]:
    logs_root = repo_root / "runtime" / "training" / "logs"
    logs_root.mkdir(parents=True, exist_ok=True)
    return (
        logs_root / f"{run_name}.stdout.log",
        logs_root / f"{run_name}.stderr.log",
        logs_root / f"{run_name}.pid",
    )


def _utc_now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _common_popen_kwargs(*, cwd: Path) -> dict[str, object]:
    return {
        "cwd": str(cwd),
        "stdin": subprocess.DEVNULL,
        "close_fds": True,
        "env": {**os.environ, "PYTHONUNBUFFERED": "1"},
    }


def _launch_detached_command(command: list[str], *, cwd: Path, stdout_path: Path, stderr_path: Path) -> subprocess.Popen:
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    stdout_handle = stdout_path.open("ab")
    stderr_handle = stderr_path.open("ab")

    kwargs = _common_popen_kwargs(cwd=cwd)
    kwargs.update(
        {
            "stdout": stdout_handle,
            "stderr": stderr_handle,
        }
    )

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
    finally:
        stdout_handle.close()
        stderr_handle.close()


def _tee_pipe(stream, terminal_stream, log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8", buffering=1) as log_handle:
        for line in iter(stream.readline, ""):
            if terminal_stream is not None:
                terminal_stream.write(line)
                terminal_stream.flush()
            log_handle.write(line)
            log_handle.flush()
    stream.close()


def _launch_attached_command(
    command: list[str],
    *,
    cwd: Path,
    pid_path: Path,
) -> subprocess.Popen:
    kwargs = _common_popen_kwargs(cwd=cwd)
    kwargs.update(
        {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
            "bufsize": 1,
        }
    )

    process = subprocess.Popen(command, **kwargs)
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.write_text(str(process.pid), encoding="utf-8")
    return process


def _stream_attached_process(process: subprocess.Popen, *, stdout_path: Path, stderr_path: Path) -> int:
    assert process.stdout is not None
    assert process.stderr is not None
    stdout_thread = threading.Thread(
        target=_tee_pipe,
        args=(process.stdout, sys.stdout, stdout_path),
        daemon=True,
    )
    stderr_thread = threading.Thread(
        target=_tee_pipe,
        args=(process.stderr, sys.stderr, stderr_path),
        daemon=True,
    )
    stdout_thread.start()
    stderr_thread.start()

    return_code = process.wait()
    stdout_thread.join()
    stderr_thread.join()
    return return_code


def _stream_background_process(process: subprocess.Popen, *, stdout_path: Path, stderr_path: Path) -> int:
    assert process.stdout is not None
    assert process.stderr is not None
    stdout_thread = threading.Thread(
        target=_tee_pipe,
        args=(process.stdout, None, stdout_path),
        daemon=True,
    )
    stderr_thread = threading.Thread(
        target=_tee_pipe,
        args=(process.stderr, None, stderr_path),
        daemon=True,
    )
    stdout_thread.start()
    stderr_thread.start()

    return_code = process.wait()
    stdout_thread.join()
    stderr_thread.join()
    return return_code


def _resolve_workspace_dir(run_manifest_path: Path, run_manifest: dict[str, object]) -> Path:
    raw_workspace_dir = run_manifest.get("workspace_dir")
    if isinstance(raw_workspace_dir, str) and raw_workspace_dir.strip():
        workspace_dir = Path(raw_workspace_dir)
        if workspace_dir.is_absolute():
            return workspace_dir
        return (run_manifest_path.parent / workspace_dir).resolve()
    return run_manifest_path.parent.resolve()


def _append_training_event(path: Path, message: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{_utc_now_utc()} {message}\n")


def _read_last_nonempty_line(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return None
    for line in reversed(lines):
        stripped = line.strip()
        if stripped:
            return stripped
    return None


def _read_pid_file(path: Path) -> int | None:
    if not path.exists():
        return None
    try:
        raw_value = path.read_text(encoding="utf-8").strip()
    except Exception:
        return None
    if not raw_value:
        return None
    try:
        pid = int(raw_value)
    except ValueError:
        return None
    return pid if pid > 0 else None


def _pid_is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _load_training_status(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_training_status(path: Path, status: dict[str, object]) -> None:
    path.write_text(json.dumps(status, indent=2), encoding="utf-8")


def _reconcile_stale_run_state_before_launch(
    *,
    run_manifest_path: Path,
    run_manifest: dict[str, object],
    pid_path: Path,
    stderr_path: Path,
) -> None:
    workspace_dir = _resolve_workspace_dir(run_manifest_path, run_manifest)
    status_path = workspace_dir / "training_status.json"
    status = _load_training_status(status_path)
    state = status.get("state") if isinstance(status, dict) else None
    pid_file_exists = pid_path.exists()
    pid = _read_pid_file(pid_path)
    pid_running = pid is not None and _pid_is_running(pid)

    if pid_running:
        raise RuntimeError(f"run '{run_manifest['run_name']}' already appears active with pid {pid}")

    if pid is not None and pid_path.exists():
        pid_path.unlink(missing_ok=True)

    if state != "running":
        return

    if not pid_file_exists:
        return

    error_parts: list[str] = ["training launcher found stale running state before launch"]
    error_parts.append("recorded pid file was stale before relaunch")
    if pid is not None:
        error_parts.append(f"recorded pid {pid} was not running")
    last_stderr_line = _read_last_nonempty_line(stderr_path)
    if last_stderr_line:
        error_parts.append(f"last_stderr={last_stderr_line}")

    status["state"] = "interrupted"
    status["updated_at_utc"] = _utc_now_utc()
    status["error_message"] = "; ".join(error_parts)
    _write_training_status(status_path, status)
    _append_training_event(
        workspace_dir / "training_events.log",
        "run_interrupted reason=stale_running_state_before_launch",
    )


def _reconcile_training_status_after_exit(
    *,
    run_manifest_path: Path,
    run_manifest: dict[str, object],
    return_code: int,
    stderr_path: Path,
) -> None:
    if return_code == 0:
        return

    workspace_dir = _resolve_workspace_dir(run_manifest_path, run_manifest)
    status_path = workspace_dir / "training_status.json"
    if not status_path.exists():
        return

    try:
        status = json.loads(status_path.read_text(encoding="utf-8"))
    except Exception:
        return
    if not isinstance(status, dict) or status.get("state") != "running":
        return

    error_message = f"training process exited with code {return_code} before final status update"
    last_stderr_line = _read_last_nonempty_line(stderr_path)
    if last_stderr_line:
        error_message = f"{error_message}; last_stderr={last_stderr_line}"

    status["state"] = "interrupted"
    status["updated_at_utc"] = _utc_now_utc()
    status["error_message"] = error_message
    status_path.write_text(json.dumps(status, indent=2), encoding="utf-8")

    _append_training_event(
        workspace_dir / "training_events.log",
        f"run_interrupted exit_code={return_code}",
    )


def _build_monitor_command(
    *,
    run_manifest_path: Path,
    stdout_path: Path,
    stderr_path: Path,
    pid_path: Path,
) -> list[str]:
    return [
        str(Path(sys.executable).resolve()),
        "-u",
        str(Path(__file__).resolve()),
        "--run-manifest",
        str(run_manifest_path),
        "--stdout-log",
        str(stdout_path),
        "--stderr-log",
        str(stderr_path),
        "--pid-file",
        str(pid_path),
        "--monitor-run",
    ]


def _monitor_run(
    training_command: list[str],
    *,
    cwd: Path,
    run_manifest_path: Path,
    run_manifest: dict[str, object],
    stdout_path: Path,
    stderr_path: Path,
    pid_path: Path,
) -> int:
    process = _launch_attached_command(
        training_command,
        cwd=cwd,
        pid_path=pid_path,
    )
    return_code = _stream_background_process(
        process,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
    )
    _reconcile_training_status_after_exit(
        run_manifest_path=run_manifest_path,
        run_manifest=run_manifest,
        return_code=return_code,
        stderr_path=stderr_path,
    )
    return return_code


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

    if args.monitor_run:
        return _monitor_run(
            training_command,
            cwd=repo_root,
            run_manifest_path=run_manifest_path,
            run_manifest=run_manifest,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            pid_path=pid_path,
        )

    _reconcile_stale_run_state_before_launch(
        run_manifest_path=run_manifest_path,
        run_manifest=run_manifest,
        pid_path=pid_path,
        stderr_path=stderr_path,
    )

    if args.detached:
        monitor_command = _build_monitor_command(
            run_manifest_path=run_manifest_path,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            pid_path=pid_path,
        )
        process = _launch_detached_command(
            monitor_command,
            cwd=repo_root,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
        )
        pid_path.parent.mkdir(parents=True, exist_ok=True)
        pid_path.write_text(str(process.pid), encoding="utf-8")
        print(f"Run name: {run_name}")
        print(f"Stdout: {stdout_path}")
        print(f"Stderr: {stderr_path}")
        print(f"PID file: {pid_path}")
        print(f"PID: {process.pid}")
        return 0

    process = _launch_attached_command(
        training_command,
        cwd=repo_root,
        pid_path=pid_path,
    )
    print(f"Run name: {run_name}")
    print(f"Stdout: {stdout_path}")
    print(f"Stderr: {stderr_path}")
    print(f"PID file: {pid_path}")
    print(f"PID: {process.pid}")
    print("Mode: attached")
    return_code = _stream_attached_process(
        process,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
    )
    _reconcile_training_status_after_exit(
        run_manifest_path=run_manifest_path,
        run_manifest=run_manifest,
        return_code=return_code,
        stderr_path=stderr_path,
    )
    return return_code


def _entrypoint() -> int:
    try:
        return main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(_entrypoint())
