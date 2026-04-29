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


def test_generate_inference_runtime_evidence_writes_fixture_reports(tmp_path):
    output_root = tmp_path / "fixtures"
    result = _run_script(
        "scripts/generate_inference_runtime_evidence.py",
        "--output-root",
        str(output_root),
        "--overwrite",
    )

    assert result.returncode == 0, result.stdout + result.stderr

    qualification_report = json.loads(
        (output_root / "reports" / "runtime-benchmark-qualified-holdout.qualification.json").read_text(encoding="utf-8")
    )
    benchmark_report = json.loads(
        (output_root / "reports" / "promoted-onnx-runtime.benchmark.json").read_text(encoding="utf-8")
    )
    local_validation = json.loads(
        (output_root / "reports" / "promoted-onnx-runtime.local-dev.validation.json").read_text(encoding="utf-8")
    )
    jetson_validation = json.loads(
        (output_root / "reports" / "promoted-tensorrt-runtime.jetson-orin-nano-super.validation.json").read_text(encoding="utf-8")
    )

    assert qualification_report["qualified"] is True
    assert qualification_report["total_assets"] == 10
    assert qualification_report["subsets"]["long_range"]["assets"] == 5
    assert qualification_report["subsets"]["low_light"]["assets"] == 7

    assert benchmark_report["source_dataset_name"] == "runtime-benchmark-qualified-holdout"
    assert benchmark_report["validation"]["deployment_ready"] is True
    assert benchmark_report["subsets"]["long_range"]["frames"] == 5
    assert benchmark_report["subsets"]["low_light"]["frames"] == 7

    assert local_validation["ready"] is True
    assert jetson_validation["ready"] is True
