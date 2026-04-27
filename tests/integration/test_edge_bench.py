from __future__ import annotations

import json
from pathlib import Path

from reposcan_contracts.config.loader import (
    load_deployment_config,
    load_model_config,
    load_pipeline_config,
)
from reposcan_contracts.frame import CameraProfile, FrameEnvelope, SourceType
from reposcan_contracts.inference import AttributePredictions, PlateDetection, VehicleDetection
from reposcan_contracts.detection import PlateCandidate
from reposcan_inference import (
    CLASSIFY_STAGE,
    END_TO_END_STAGE,
    InferenceService,
    ModelAdapterBundle,
    NoopThermalSampler,
    OCR_STAGE,
    PLATE_STAGE,
    STAGES_IN_ORDER,
    StaticClassifierAdapter,
    StaticOcrAdapter,
    StaticPlateDetectorAdapter,
    StaticVehicleDetectorAdapter,
    ThermalSample,
    VEHICLE_STAGE,
    render_edge_bench_markdown,
    run_edge_bench,
    write_edge_bench_artifacts,
)
def _frame(frame_number: int) -> FrameEnvelope:
    return FrameEnvelope.model_validate(
        {
            "frame_id": f"frm_edge_{frame_number}",
            "camera_id": "cam_edge_01",
            "timestamp_utc": f"2026-04-15T18:00:{frame_number:02d}Z",
            "frame_path": f"media/frames/cam_edge_01/frame_{frame_number:06d}.jpg",
            "frame_number": frame_number,
            "source_type": "file",
            "camera_profile": CameraProfile(
                camera_id="cam_edge_01", source_type=SourceType.file
            ).model_dump(mode="json"),
        }
    )


def _build_service(*, with_classifier: bool = True) -> InferenceService:
    model_stack = load_model_config("configs/models/example-model-stack.yaml")
    pipeline = load_pipeline_config("configs/pipelines/default-edge.yaml")
    classifier = None
    if with_classifier and model_stack.classifier is not None:
        classifier = StaticClassifierAdapter(
            model_stack.classifier,
            outputs=[
                AttributePredictions.model_validate(
                    {"color": "white", "color_confidence": 0.8}
                )
            ],
        )
    return InferenceService(
        model_stack,
        pipeline,
        ModelAdapterBundle(
            vehicle_detector=StaticVehicleDetectorAdapter(
                model_stack.vehicle_detector,
                outputs=[
                    VehicleDetection.model_validate(
                        {
                            "bbox": {"x": 1, "y": 2, "w": 30, "h": 40},
                            "confidence": 0.9,
                            "class_label": "car",
                        }
                    )
                ],
            ),
            plate_detector=StaticPlateDetectorAdapter(
                model_stack.plate_detector,
                outputs=[
                    PlateDetection.model_validate(
                        {
                            "bbox": {"x": 3, "y": 4, "w": 10, "h": 8},
                            "confidence": 0.88,
                            "vehicle_index": 0,
                        }
                    )
                ],
            ),
            ocr=StaticOcrAdapter(
                model_stack.ocr,
                outputs=[PlateCandidate.model_validate({"text": "6BZN220", "confidence": 0.93})],
            ),
            classifier=classifier,
        ),
    )


def test_run_edge_bench_records_stage_and_end_to_end_stats():
    service = _build_service()
    deployment = load_deployment_config("configs/deployments/jetson-orin-nano-super.yaml")

    report = run_edge_bench(
        service,
        [_frame(i) for i in range(1, 6)],
        run_id="edge_test_run",
        deployment=deployment,
    )

    assert report.run_id == "edge_test_run"
    assert report.frames_processed == 5
    assert report.cold_start_latency_ms >= 0.0
    assert report.end_to_end.stage == END_TO_END_STAGE
    assert report.end_to_end.count == 5
    assert report.end_to_end.max_ms >= report.end_to_end.average_ms
    assert report.end_to_end.p99_ms >= report.end_to_end.p95_ms

    stages_by_name = {stage.stage: stage for stage in report.stages}
    assert set(stages_by_name) == set(STAGES_IN_ORDER)
    for stage_name in (VEHICLE_STAGE, PLATE_STAGE, OCR_STAGE, CLASSIFY_STAGE):
        stage = stages_by_name[stage_name]
        assert stage.count == 5, f"stage {stage_name} did not record every frame"
        assert stage.max_ms >= stage.average_ms
        assert stage.p99_ms >= stage.p95_ms

    assert report.target_hardware == "jetson_orin_nano_super"
    assert report.target_fps_per_camera == 10.0
    assert report.max_active_cameras == 1
    assert report.latency_budget_ms_p95 == 250.0
    assert report.memory_budget_mb == 6144
    assert any("TensorRT" in rec for rec in report.recommendations)
    assert report.thermal_samples  # noop sampler still records informational rows


def test_run_edge_bench_without_classifier_reports_zero_stage_count():
    service = _build_service(with_classifier=False)

    report = run_edge_bench(service, [_frame(1), _frame(2)], run_id="edge_no_cls")

    stages_by_name = {stage.stage: stage for stage in report.stages}
    assert stages_by_name[CLASSIFY_STAGE].count == 0
    assert stages_by_name[VEHICLE_STAGE].count == 2


def test_run_edge_bench_empty_frame_list_returns_zero_report():
    service = _build_service()

    report = run_edge_bench(service, [], run_id="edge_empty")

    assert report.frames_processed == 0
    assert report.cold_start_latency_ms == 0.0
    assert report.end_to_end.count == 0
    for stage in report.stages:
        assert stage.count == 0


def test_edge_bench_artifacts_round_trip(tmp_path: Path):
    service = _build_service()

    report = run_edge_bench(service, [_frame(i) for i in range(1, 4)], run_id="edge_rt_run")
    run_dir = write_edge_bench_artifacts(report, output_root=tmp_path)

    assert run_dir.name == "edge_rt_run"
    md_path = run_dir / "edge_bench_report.md"
    json_path = run_dir / "edge_bench_report.json"
    assert md_path.exists()
    assert json_path.exists()

    markdown = md_path.read_text(encoding="utf-8")
    assert "Edge bench run edge_rt_run" in markdown
    assert "Per-stage latency" in markdown

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["run_id"] == "edge_rt_run"
    assert payload["frames_processed"] == 3
    assert payload["end_to_end"]["stage"] == END_TO_END_STAGE


def test_render_edge_bench_markdown_includes_custom_thermal_samples():
    service = _build_service()

    class StaticSampler:
        def sample(self) -> list[ThermalSample]:
            return [
                ThermalSample(
                    timestamp_utc="2026-04-15T00:00:00Z",
                    component="orin_cpu",
                    temperature_c=52.5,
                    power_w=7.2,
                    notes="tegrastats",
                )
            ]

    report = run_edge_bench(
        service,
        [_frame(1)],
        run_id="edge_thermal",
        thermal_sampler=StaticSampler(),
    )
    markdown = render_edge_bench_markdown(report)
    assert "orin_cpu" in markdown
    assert "tegrastats" in markdown


def test_noop_thermal_sampler_produces_informational_sample():
    samples = NoopThermalSampler().sample()
    assert samples
    assert samples[0].component == "host"
    assert samples[0].temperature_c is None
