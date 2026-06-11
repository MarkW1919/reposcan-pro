from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml
from PIL import Image

from reposcan_contracts.config.loader import load_model_release_channel, load_model_release_record, load_model_config
from reposcan_inference import package_promoted_onnx_bundle


REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _write_demo_image(path: Path, *, color: tuple[int, int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (128, 72), color=color).save(path, format="JPEG")


def test_register_and_rollback_model_release_channel(tmp_path):
    source_stack = load_model_config("configs/models/local-onnx-runtime.yaml")
    package_report = package_promoted_onnx_bundle(
        source_stack,
        output_dir=tmp_path / "onnx-bundle",
        bundle_name="release-registry-bundle",
        exported_at_utc="2026-03-23T12:00:00Z",
        source_run_id="release_registry_bundle_001",
        export_tool="reposcan.package_promoted_onnx_bundle",
        export_tool_version="0.1.0",
        opset_version=13,
        precision="fp32",
        target_runtime="onnxruntime",
    )

    frames_dir = tmp_path / "frames"
    _write_demo_image(frames_dir / "frame_0001.jpg", color=(240, 240, 240))
    _write_demo_image(frames_dir / "frame_0002.jpg", color=(240, 240, 240))

    benchmark_manifest = tmp_path / "benchmark.yaml"
    benchmark_manifest.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "release-registry-benchmark",
                "camera_id": "cam_release_registry_01",
                "frames": [
                    {
                        "frame_path": str(frames_dir / "frame_0001.jpg"),
                        "expected_plate_text": "6BZN220",
                        "expected_vehicle_color": "white",
                        "expected_vehicle_make": "toyota",
                        "tags": ["long_range"],
                    },
                    {
                        "frame_path": str(frames_dir / "frame_0002.jpg"),
                        "expected_plate_text": "6BZN220",
                        "expected_vehicle_color": "white",
                        "expected_vehicle_make": "toyota",
                        "tags": ["low_light"],
                    },
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    registry_root = tmp_path / "registry"
    channel_name = "local-dev-demo"

    first = _run_script(
        "scripts/register_model_release.py",
        "--model-config",
        str(Path(package_report.config_path)),
        "--deployment-config",
        str(REPO_ROOT / "configs" / "deployments" / "local-dev.yaml"),
        "--benchmark-manifest",
        str(benchmark_manifest),
        "--registry-root",
        str(registry_root),
        "--channel",
        channel_name,
        "--release-id",
        "release-a",
    )
    assert first.returncode == 0, first.stdout + first.stderr

    second = _run_script(
        "scripts/register_model_release.py",
        "--model-config",
        str(Path(package_report.config_path)),
        "--deployment-config",
        str(REPO_ROOT / "configs" / "deployments" / "local-dev.yaml"),
        "--benchmark-manifest",
        str(benchmark_manifest),
        "--registry-root",
        str(registry_root),
        "--channel",
        channel_name,
        "--release-id",
        "release-b",
        "--notes",
        "Second accepted benchmark pass",
    )
    assert second.returncode == 0, second.stdout + second.stderr

    channel = load_model_release_channel(registry_root / "channels" / "local-dev-demo.yaml")
    assert channel.current_release_id == "release-b"
    assert channel.previous_release_id == "release-a"
    assert channel.release_history == ["release-a", "release-b"]
    assert [event.action.value for event in channel.events] == ["promote", "promote"]

    record_b = load_model_release_record(registry_root / "releases" / "release-b" / "release-record.yaml")
    assert record_b.validation.deployment_ready is True
    assert record_b.overall_benchmark.exact_match_rate == 1.0
    assert record_b.subset_benchmarks["long_range"].exact_match_rate == 1.0
    benchmark_report_path = registry_root / "releases" / "release-b" / "benchmark_report.json"
    assert benchmark_report_path.exists()
    benchmark_report = json.loads(benchmark_report_path.read_text(encoding="utf-8"))
    assert benchmark_report["benchmark_name"] == "release-registry-benchmark"

    rollback = _run_script(
        "scripts/rollback_model_release.py",
        "--registry-root",
        str(registry_root),
        "--channel",
        channel_name,
        "--reason",
        "Operator validation regression",
    )
    assert rollback.returncode == 0, rollback.stdout + rollback.stderr

    rolled_back = load_model_release_channel(registry_root / "channels" / "local-dev-demo.yaml")
    assert rolled_back.current_release_id == "release-a"
    assert rolled_back.previous_release_id == "release-b"
    assert [event.action.value for event in rolled_back.events] == ["promote", "promote", "rollback"]
