from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_generate_sync_remote_evidence_writes_report(tmp_path):
    output_root = tmp_path / "sync-fixtures"
    result = _run_script(
        "scripts/generate_sync_remote_evidence.py",
        "--output-root",
        str(output_root),
        "--overwrite",
    )

    assert result.returncode == 0, result.stdout + result.stderr

    report = json.loads(
        (output_root / "reports" / "remote-sync-validation.json").read_text(encoding="utf-8")
    )
    assert report["generated_at_utc"] == "2026-03-25T00:15:00Z"
    assert report["sync_transport"]["first_run_failed"] == 1
    assert report["sync_transport"]["retry_run_synced"] == 1
    assert report["sync_transport"]["idempotent_replay_synced"] == 1
    assert report["sync_transport"]["remote_unique_detections"] == 1
    assert report["sync_transport"]["remote_sync_posts"] == 3
    assert report["sync_transport"]["final_sync_status"] == "synced"
    assert report["alert_delivery"]["remote_unique_alerts"] == 1
    assert report["alert_delivery"]["remote_alert_posts"] == 2
