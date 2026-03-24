from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from PIL import Image

from reposcan_contracts.config.loader import load_benchmark_manifest, load_deployment_config, load_model_config
from reposcan_inference import InferenceService, benchmark_promoted_model, package_promoted_onnx_bundle


def _write_demo_image(path: Path, *, color: tuple[int, int, int]) -> None:
    image = Image.new("RGB", (128, 72), color=color)
    image.save(path, format="JPEG")


def test_benchmark_promoted_model_reports_overall_and_tagged_metrics(tmp_path):
    source_stack = load_model_config("configs/models/local-onnx-runtime.yaml")
    package_report = package_promoted_onnx_bundle(
        source_stack,
        output_dir=tmp_path / "onnx-bundle",
        bundle_name="benchmark-bundle",
        exported_at_utc="2026-03-23T10:00:00Z",
        source_run_id="benchmark_bundle_001",
        export_tool="reposcan.package_promoted_onnx_bundle",
        export_tool_version="0.1.0",
        opset_version=13,
        precision="fp32",
        target_runtime="onnxruntime",
    )

    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    _write_demo_image(frames_dir / "frame_0001.jpg", color=(240, 240, 240))
    _write_demo_image(frames_dir / "frame_0002.jpg", color=(240, 240, 240))
    _write_demo_image(frames_dir / "frame_0003.jpg", color=(240, 240, 240))

    manifest_path = tmp_path / "benchmark.yaml"
    manifest_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "sample-promoted-benchmark",
                "camera_id": "cam_benchmark_01",
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
                    {
                        "frame_path": str(frames_dir / "frame_0003.jpg"),
                        "expected_plate_text": "6BZN221",
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

    inference_service = InferenceService.from_config_paths(
        model_config_path=package_report.config_path,
        pipeline_config_path="configs/pipelines/default-edge.yaml",
    )
    deployment = load_deployment_config("configs/deployments/local-dev.yaml")
    report = benchmark_promoted_model(
        inference_service,
        load_benchmark_manifest(manifest_path),
        deployment=deployment,
        benchmark_manifest_path=manifest_path,
    )

    assert report.benchmark_name == "sample-promoted-benchmark"
    assert report.model_stack_name == "benchmark-bundle"
    assert report.benchmark_manifest_path == str(manifest_path)
    assert report.overall.frames == 3
    assert report.overall.exact_match_rate == pytest.approx(2 / 3)
    assert report.overall.character_accuracy == pytest.approx((1.0 + 1.0 + (6 / 7)) / 3)
    assert report.overall.color_accuracy == pytest.approx(1.0)
    assert report.overall.make_accuracy == pytest.approx(1.0)
    assert report.overall.average_latency_ms is not None
    assert report.overall.p95_latency_ms is not None
    assert report.overall.max_latency_ms is not None
    assert report.subsets["long_range"].exact_match_rate == pytest.approx(1.0)
    assert report.subsets["low_light"].exact_match_rate == pytest.approx(0.5)
    assert report.subsets["low_light"].average_latency_ms is not None
    assert report.validation is not None
    assert report.validation.runtime_ready is True
    assert report.validation.promotion_ready is True
    assert report.validation.deployment_ready is True
    assert report.validation.deployment_name == "local-dev"
