from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from PIL import Image

from reposcan_contracts.config.loader import load_benchmark_manifest, load_deployment_config, load_model_config
from reposcan_inference import (
    ACCEPTANCE_LANES,
    InferenceService,
    LONG_RANGE_LANE,
    LOW_LIGHT_LANE,
    MOVING_PLATFORM_LANE,
    benchmark_promoted_model,
    build_acceptance_run_report,
    frame_lanes,
    lane_report_filenames,
    readiness_evidence_map,
    package_promoted_onnx_bundle,
    render_lane_markdown,
    render_overall_markdown,
    stamp_acceptance_lanes,
    write_acceptance_artifacts,
)


def _write_demo_image(path: Path, *, color: tuple[int, int, int]) -> None:
    image = Image.new("RGB", (128, 72), color=color)
    image.save(path, format="JPEG")


def test_frame_lanes_routes_tags_into_acceptance_lanes():
    assert frame_lanes(["long_range"]) == [LONG_RANGE_LANE]
    assert frame_lanes(["night"]) == [LOW_LIGHT_LANE]
    assert frame_lanes(["ir_assisted"]) == [LOW_LIGHT_LANE]
    assert frame_lanes(["moving_platform"]) == [MOVING_PLATFORM_LANE]
    assert frame_lanes(["long_range", "night"]) == [LONG_RANGE_LANE, LOW_LIGHT_LANE]
    assert frame_lanes(["long_range", "moving_platform"]) == [LONG_RANGE_LANE, MOVING_PLATFORM_LANE]
    assert frame_lanes(["unknown"]) == []


def test_stamp_acceptance_lanes_adds_lane_tags_without_mutating_input(tmp_path):
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    _write_demo_image(frames_dir / "frame.jpg", color=(240, 240, 240))

    manifest_path = tmp_path / "benchmark.yaml"
    manifest_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "stamp-test",
                "camera_id": "cam_test",
                "frames": [
                    {
                        "frame_path": str(frames_dir / "frame.jpg"),
                        "expected_plate_text": "AAA0000",
                        "tags": ["long_range", "night"],
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    manifest = load_benchmark_manifest(manifest_path)
    stamped = stamp_acceptance_lanes(manifest)

    assert manifest.frames[0].tags == ["long_range", "night"]
    assert "lane:long_range" in stamped.frames[0].tags
    assert "lane:low_light" in stamped.frames[0].tags
    assert "lane:moving_platform" not in stamped.frames[0].tags


def test_acceptance_run_report_and_artifacts_end_to_end(tmp_path):
    source_stack = load_model_config("configs/models/local-onnx-runtime.yaml")
    package_report = package_promoted_onnx_bundle(
        source_stack,
        output_dir=tmp_path / "onnx-bundle",
        bundle_name="acceptance-bundle",
        exported_at_utc="2026-04-14T10:00:00Z",
        source_run_id="acceptance_bundle_001",
        export_tool="reposcan.package_promoted_onnx_bundle",
        export_tool_version="0.1.0",
        opset_version=13,
        precision="fp32",
        target_runtime="onnxruntime",
    )

    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    _write_demo_image(frames_dir / "lr.jpg", color=(240, 240, 240))
    _write_demo_image(frames_dir / "ll.jpg", color=(240, 240, 240))
    _write_demo_image(frames_dir / "mp.jpg", color=(240, 240, 240))

    manifest_path = tmp_path / "acceptance_benchmark.yaml"
    manifest_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "acceptance-integration-test",
                "camera_id": "cam_acceptance_test",
                "frames": [
                    {
                        "frame_path": str(frames_dir / "lr.jpg"),
                        "expected_plate_text": "6BZN220",
                        "expected_vehicle_color": "white",
                        "expected_vehicle_make": "toyota",
                        "tags": ["long_range"],
                    },
                    {
                        "frame_path": str(frames_dir / "ll.jpg"),
                        "expected_plate_text": "6BZN220",
                        "expected_vehicle_color": "white",
                        "expected_vehicle_make": "toyota",
                        "tags": ["night"],
                    },
                    {
                        "frame_path": str(frames_dir / "mp.jpg"),
                        "expected_plate_text": "6BZN220",
                        "expected_vehicle_color": "white",
                        "expected_vehicle_make": "toyota",
                        "tags": ["moving_platform"],
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

    manifest = load_benchmark_manifest(manifest_path)
    stamped = stamp_acceptance_lanes(manifest)
    benchmark_report = benchmark_promoted_model(
        inference_service,
        stamped,
        deployment=deployment,
        benchmark_manifest_path=manifest_path,
    )

    acceptance_report = build_acceptance_run_report(benchmark_report, run_id="acc_test_run")
    assert acceptance_report.run_id == "acc_test_run"
    assert acceptance_report.benchmark_name == "acceptance-integration-test"
    assert acceptance_report.overall.frames == 3
    assert {lane.lane for lane in acceptance_report.lanes} == set(ACCEPTANCE_LANES)

    lanes_by_name = {lane.lane: lane for lane in acceptance_report.lanes}
    for lane_name in ACCEPTANCE_LANES:
        lane = lanes_by_name[lane_name]
        assert lane.status == "evaluated"
        assert lane.frames == 1
        assert lane.metrics is not None
        assert lane.metrics.exact_match_rate == pytest.approx(1.0)

    overall_md = render_overall_markdown(acceptance_report)
    assert "Acceptance run acc_test_run" in overall_md
    assert LONG_RANGE_LANE in overall_md
    assert LOW_LIGHT_LANE in overall_md
    assert MOVING_PLATFORM_LANE in overall_md

    long_range_md = render_lane_markdown(acceptance_report, LONG_RANGE_LANE)
    assert LONG_RANGE_LANE in long_range_md
    assert "frames evaluated in this lane: 1" in long_range_md

    run_dir = write_acceptance_artifacts(acceptance_report, output_root=tmp_path / "artifacts")
    assert run_dir.name == "acc_test_run"
    assert (run_dir / "overall_report.md").exists()
    for filename in lane_report_filenames().values():
        assert (run_dir / filename).exists()
    sidecar = run_dir / "acceptance_report.json"
    assert sidecar.exists()
    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    assert payload["run_id"] == "acc_test_run"
    assert len(payload["lanes"]) == len(ACCEPTANCE_LANES)
    evidence_map = json.loads((run_dir / "production_readiness_evidence.json").read_text(encoding="utf-8"))
    assert evidence_map["run_id"] == "acc_test_run"
    assert evidence_map["criteria"]["P1-1"]["artifact"] == "long_range_report.md"
    assert evidence_map["criteria"]["P1-1"]["status"] == "evaluated"
    assert evidence_map["criteria"]["P2-1"]["artifact"] == "low_light_report.md"
    assert evidence_map["criteria"]["P4-2"]["metric"] == "character_accuracy"
    assert readiness_evidence_map(acceptance_report)["criteria"]["moving_platform"]["frames"] == 1


def test_acceptance_run_report_marks_missing_lane_as_not_evaluated(tmp_path):
    source_stack = load_model_config("configs/models/local-onnx-runtime.yaml")
    package_report = package_promoted_onnx_bundle(
        source_stack,
        output_dir=tmp_path / "onnx-bundle",
        bundle_name="acceptance-bundle-missing",
        exported_at_utc="2026-04-14T10:00:00Z",
        source_run_id="acceptance_bundle_002",
        export_tool="reposcan.package_promoted_onnx_bundle",
        export_tool_version="0.1.0",
        opset_version=13,
        precision="fp32",
        target_runtime="onnxruntime",
    )

    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    _write_demo_image(frames_dir / "lr.jpg", color=(240, 240, 240))

    manifest_path = tmp_path / "lr_only.yaml"
    manifest_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "lr-only",
                "camera_id": "cam_lr",
                "frames": [
                    {
                        "frame_path": str(frames_dir / "lr.jpg"),
                        "expected_plate_text": "6BZN220",
                        "tags": ["long_range"],
                    }
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
    stamped = stamp_acceptance_lanes(load_benchmark_manifest(manifest_path))
    benchmark_report = benchmark_promoted_model(
        inference_service,
        stamped,
        benchmark_manifest_path=manifest_path,
    )
    acceptance_report = build_acceptance_run_report(benchmark_report, run_id="acc_lr_only")

    lanes = {lane.lane: lane for lane in acceptance_report.lanes}
    assert lanes[LONG_RANGE_LANE].status == "evaluated"
    assert lanes[LOW_LIGHT_LANE].status == "not_evaluated"
    assert lanes[LOW_LIGHT_LANE].frames == 0
    assert lanes[MOVING_PLATFORM_LANE].status == "not_evaluated"

    low_light_md = render_lane_markdown(acceptance_report, LOW_LIGHT_LANE)
    assert "No frames in the source manifest carried tags that route into this lane." in low_light_md
