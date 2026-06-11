"""Edge inference benchmarking harness.

This module extends the existing :class:`InferenceProfiler` with the
measurements that matter for edge deployment sign-off:

- per-stage latency (vehicle_detect, plate_detect, ocr, classify) with
  p50/p95/p99 percentiles
- end-to-end latency distribution
- cold-start latency (first frame isolated)
- peak resident-set size (RSS) during the run
- optional thermal/power samples via a pluggable sampler protocol so the
  same harness can stay passive on a developer workstation and wire into
  tegrastats on the Jetson Orin rig

The harness does **not** re-implement inference; it drives the existing
``InferenceService`` pipeline so the numbers it produces match what the
runtime actually does in production.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from time import perf_counter
from typing import Protocol

from pydantic import BaseModel, Field

from reposcan_contracts.config.deployment import DeploymentConfig
from reposcan_contracts.frame import FrameEnvelope, PreparedFrame
from reposcan_contracts.inference import InferenceCandidate

from .profiling import recommend_runtime_tuning
from .service import InferenceService

VEHICLE_STAGE = "vehicle_detect"
PLATE_STAGE = "plate_detect"
OCR_STAGE = "ocr"
CLASSIFY_STAGE = "classify"
END_TO_END_STAGE = "end_to_end"

STAGES_IN_ORDER: tuple[str, ...] = (
    VEHICLE_STAGE,
    PLATE_STAGE,
    OCR_STAGE,
    CLASSIFY_STAGE,
)


class StageLatencyStats(BaseModel):
    stage: str = Field(..., min_length=1)
    count: int = Field(..., ge=0)
    average_ms: float = Field(..., ge=0.0)
    p50_ms: float = Field(..., ge=0.0)
    p95_ms: float = Field(..., ge=0.0)
    p99_ms: float = Field(..., ge=0.0)
    max_ms: float = Field(..., ge=0.0)


class ThermalSample(BaseModel):
    timestamp_utc: str = Field(..., min_length=1)
    component: str = Field(..., min_length=1)
    temperature_c: float | None = None
    power_w: float | None = None
    notes: str | None = None


class ThermalSampler(Protocol):
    """Pluggable sampler that records thermal/power telemetry during a run.

    The default implementation returns no samples. On the Jetson Orin rig
    an operator wires in a sampler that reads ``tegrastats`` or the
    ``sysfs`` thermal zones.
    """

    def sample(self) -> list[ThermalSample]:  # pragma: no cover - protocol
        ...


class NoopThermalSampler:
    """Default sampler used on developer workstations.

    Returns a single informational record so the evidence artifact makes
    it obvious the run did not come from real hardware telemetry.
    """

    def sample(self) -> list[ThermalSample]:
        return [
            ThermalSample(
                timestamp_utc=_utcnow(),
                component="host",
                temperature_c=None,
                power_w=None,
                notes="no thermal telemetry available on this host",
            )
        ]


class EdgeBenchReport(BaseModel):
    run_id: str = Field(..., min_length=1)
    generated_at_utc: str = Field(..., min_length=1)
    model_stack_name: str = Field(..., min_length=1)
    pipeline_name: str | None = None
    deployment_name: str | None = None
    target_hardware: str | None = None
    target_fps_per_camera: float | None = None
    max_active_cameras: int | None = None
    latency_budget_ms_p95: float | None = None
    memory_budget_mb: int | None = None
    host_platform: str = Field(..., min_length=1)
    frames_processed: int = Field(..., ge=0)
    cold_start_latency_ms: float = Field(..., ge=0.0)
    end_to_end: StageLatencyStats
    stages: list[StageLatencyStats]
    peak_rss_mb: float | None = None
    peak_rss_source: str | None = None
    thermal_samples: list[ThermalSample] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


def _percentile(sorted_values: list[float], percentile: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    index = max(0, min(len(sorted_values) - 1, int(round(percentile * (len(sorted_values) - 1)))))
    return sorted_values[index]


def _summarize(stage: str, samples_ms: list[float]) -> StageLatencyStats:
    if not samples_ms:
        return StageLatencyStats(
            stage=stage,
            count=0,
            average_ms=0.0,
            p50_ms=0.0,
            p95_ms=0.0,
            p99_ms=0.0,
            max_ms=0.0,
        )
    ordered = sorted(samples_ms)
    return StageLatencyStats(
        stage=stage,
        count=len(ordered),
        average_ms=mean(ordered),
        p50_ms=_percentile(ordered, 0.50),
        p95_ms=_percentile(ordered, 0.95),
        p99_ms=_percentile(ordered, 0.99),
        max_ms=max(ordered),
    )


def _peak_rss_mb() -> tuple[float | None, str | None]:
    """Best-effort peak resident-set size lookup.

    On Linux/macOS uses ``resource.getrusage`` which is already in the
    standard library. On Windows falls back to ``psutil`` if available,
    otherwise returns ``(None, None)``.
    """

    try:
        import resource  # type: ignore[import-not-found]
    except ImportError:
        resource = None  # type: ignore[assignment]

    if resource is not None:
        usage = resource.getrusage(resource.RUSAGE_SELF)
        raw = float(usage.ru_maxrss)
        if sys.platform == "darwin":
            return raw / (1024.0 * 1024.0), "resource.ru_maxrss(bytes)"
        return raw / 1024.0, "resource.ru_maxrss(kilobytes)"

    try:
        import psutil  # type: ignore[import-not-found]
    except ImportError:
        return None, None
    rss = float(psutil.Process().memory_info().rss)
    return rss / (1024.0 * 1024.0), "psutil.Process.memory_info.rss"


def _run_frame_with_stage_timings(
    service: InferenceService,
    frame: FrameEnvelope | PreparedFrame,
) -> tuple[InferenceCandidate, dict[str, float], float]:
    """Run a single frame through the pipeline while recording stage timings.

    Mirrors :meth:`InferenceService.run` but adds a timer around every
    adapter call. Returns the candidate, a dict of stage timings in
    milliseconds, and the end-to-end latency in milliseconds.
    """

    stage_timings: dict[str, float] = {}
    started = perf_counter()

    t0 = perf_counter()
    vehicle_detections = service.adapters.vehicle_detector.detect(frame)
    stage_timings[VEHICLE_STAGE] = (perf_counter() - t0) * 1000.0

    t0 = perf_counter()
    plate_detections = service.adapters.plate_detector.detect(
        frame,
        vehicle_detections=vehicle_detections,
        strategy=service.pipeline_config.plate_detection_strategy,
    )
    stage_timings[PLATE_STAGE] = (perf_counter() - t0) * 1000.0

    t0 = perf_counter()
    ocr_candidates = service.adapters.ocr.recognize(frame, plate_detections)
    stage_timings[OCR_STAGE] = (perf_counter() - t0) * 1000.0

    attribute_predictions = []
    if service.adapters.classifier is not None:
        t0 = perf_counter()
        attribute_predictions = service.adapters.classifier.predict(frame, vehicle_detections)
        stage_timings[CLASSIFY_STAGE] = (perf_counter() - t0) * 1000.0

    total_ms = max((perf_counter() - started) * 1000.0, 0.0)

    candidate = InferenceCandidate(
        frame_id=frame.frame_id,
        camera_id=frame.camera_id,
        timestamp_utc=frame.timestamp_utc,
        vehicle_detections=vehicle_detections,
        plate_detections=plate_detections,
        ocr_candidates=ocr_candidates,
        attribute_predictions=attribute_predictions,
        model_versions=service.model_versions(),
        processing_latency_ms=total_ms,
    )
    return candidate, stage_timings, total_ms


def run_edge_bench(
    service: InferenceService,
    frames: list[FrameEnvelope | PreparedFrame],
    *,
    run_id: str | None = None,
    deployment: DeploymentConfig | None = None,
    thermal_sampler: ThermalSampler | None = None,
    generated_at_utc: str | None = None,
) -> EdgeBenchReport:
    """Run an edge benchmark over ``frames`` using the configured pipeline.

    The first frame is recorded separately as the cold-start sample and is
    still included in the end-to-end distribution.
    """

    if not frames:
        return EdgeBenchReport(
            run_id=run_id or default_edge_run_id(),
            generated_at_utc=generated_at_utc or _utcnow(),
            model_stack_name=service.model_stack.stack_name,
            pipeline_name=getattr(service.pipeline_config, "pipeline_name", None),
            deployment_name=deployment.deployment_name if deployment is not None else None,
            target_hardware=deployment.target_hardware.value if deployment is not None else None,
            target_fps_per_camera=deployment.performance.target_fps_per_camera if deployment is not None else None,
            max_active_cameras=deployment.performance.max_active_cameras if deployment is not None else None,
            latency_budget_ms_p95=deployment.performance.latency_budget_ms_p95 if deployment is not None else None,
            memory_budget_mb=deployment.performance.memory_budget_mb if deployment is not None else None,
            host_platform=sys.platform,
            frames_processed=0,
            cold_start_latency_ms=0.0,
            end_to_end=_summarize(END_TO_END_STAGE, []),
            stages=[_summarize(stage, []) for stage in STAGES_IN_ORDER],
            peak_rss_mb=None,
            peak_rss_source=None,
            thermal_samples=[],
            recommendations=recommend_runtime_tuning(deployment, service.model_stack) if deployment else [],
        )

    sampler = thermal_sampler or NoopThermalSampler()
    thermal_samples: list[ThermalSample] = []

    cold_candidate, cold_stages, cold_total_ms = _run_frame_with_stage_timings(service, frames[0])
    thermal_samples.extend(sampler.sample())

    stage_samples: dict[str, list[float]] = {stage: [] for stage in STAGES_IN_ORDER}
    end_to_end_samples: list[float] = [cold_total_ms]
    for stage, value in cold_stages.items():
        stage_samples[stage].append(value)

    for frame in frames[1:]:
        _candidate, stage_timings, total_ms = _run_frame_with_stage_timings(service, frame)
        end_to_end_samples.append(total_ms)
        for stage, value in stage_timings.items():
            stage_samples[stage].append(value)

    thermal_samples.extend(sampler.sample())

    peak_rss_mb, peak_rss_source = _peak_rss_mb()

    recommendations: list[str] = []
    if deployment is not None:
        recommendations = list(recommend_runtime_tuning(deployment, service.model_stack))

    return EdgeBenchReport(
        run_id=run_id or default_edge_run_id(),
        generated_at_utc=generated_at_utc or _utcnow(),
        model_stack_name=service.model_stack.stack_name,
        pipeline_name=getattr(service.pipeline_config, "pipeline_name", None),
        deployment_name=deployment.deployment_name if deployment is not None else None,
        target_hardware=deployment.target_hardware.value if deployment is not None else None,
        target_fps_per_camera=deployment.performance.target_fps_per_camera if deployment is not None else None,
        max_active_cameras=deployment.performance.max_active_cameras if deployment is not None else None,
        latency_budget_ms_p95=deployment.performance.latency_budget_ms_p95 if deployment is not None else None,
        memory_budget_mb=deployment.performance.memory_budget_mb if deployment is not None else None,
        host_platform=sys.platform,
        frames_processed=len(frames),
        cold_start_latency_ms=cold_total_ms,
        end_to_end=_summarize(END_TO_END_STAGE, end_to_end_samples),
        stages=[_summarize(stage, stage_samples[stage]) for stage in STAGES_IN_ORDER],
        peak_rss_mb=peak_rss_mb,
        peak_rss_source=peak_rss_source,
        thermal_samples=thermal_samples,
        recommendations=recommendations,
    )


def _format_ms(value: float) -> str:
    return f"{value:.2f} ms"


def _format_mb(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.1f} MB"


def render_edge_bench_markdown(report: EdgeBenchReport) -> str:
    lines = [
        f"# Edge bench run {report.run_id}",
        "",
        f"- generated at: {report.generated_at_utc}",
        f"- model stack: {report.model_stack_name}",
        f"- host platform: {report.host_platform}",
        f"- frames processed: {report.frames_processed}",
        f"- cold-start latency: {_format_ms(report.cold_start_latency_ms)}",
        f"- peak RSS: {_format_mb(report.peak_rss_mb)}"
        + (f" (source: {report.peak_rss_source})" if report.peak_rss_source else ""),
    ]
    if report.pipeline_name:
        lines.append(f"- pipeline: {report.pipeline_name}")
    if report.deployment_name:
        lines.append(f"- deployment profile: {report.deployment_name}")
    if report.target_hardware:
        lines.append(f"- target hardware: {report.target_hardware}")
    if report.target_fps_per_camera is not None:
        lines.append(f"- target FPS per camera: {report.target_fps_per_camera:.1f}")
    if report.max_active_cameras is not None:
        lines.append(f"- max active cameras: {report.max_active_cameras}")
    if report.latency_budget_ms_p95 is not None:
        lines.append(f"- p95 latency budget: {_format_ms(report.latency_budget_ms_p95)}")
    if report.memory_budget_mb is not None:
        lines.append(f"- memory budget: {report.memory_budget_mb} MB")

    lines.extend(
        [
            "",
            "## End-to-end latency",
            "",
            "| metric | value |",
            "|---|---|",
            f"| frames | {report.end_to_end.count} |",
            f"| average | {_format_ms(report.end_to_end.average_ms)} |",
            f"| p50 | {_format_ms(report.end_to_end.p50_ms)} |",
            f"| p95 | {_format_ms(report.end_to_end.p95_ms)} |",
            f"| p99 | {_format_ms(report.end_to_end.p99_ms)} |",
            f"| max | {_format_ms(report.end_to_end.max_ms)} |",
            "",
            "## Per-stage latency",
            "",
            "| stage | count | avg | p50 | p95 | p99 | max |",
            "|---|---|---|---|---|---|---|",
        ]
    )
    for stage in report.stages:
        lines.append(
            "| "
            + " | ".join(
                [
                    stage.stage,
                    str(stage.count),
                    _format_ms(stage.average_ms),
                    _format_ms(stage.p50_ms),
                    _format_ms(stage.p95_ms),
                    _format_ms(stage.p99_ms),
                    _format_ms(stage.max_ms),
                ]
            )
            + " |"
        )

    lines.extend(["", "## Thermal samples", ""])
    if not report.thermal_samples:
        lines.append("No thermal samples recorded.")
    else:
        lines.append("| timestamp | component | temp (C) | power (W) | notes |")
        lines.append("|---|---|---|---|---|")
        for sample in report.thermal_samples:
            lines.append(
                "| "
                + " | ".join(
                    [
                        sample.timestamp_utc,
                        sample.component,
                        f"{sample.temperature_c:.1f}" if sample.temperature_c is not None else "n/a",
                        f"{sample.power_w:.1f}" if sample.power_w is not None else "n/a",
                        sample.notes or "",
                    ]
                )
                + " |"
            )

    if report.recommendations:
        lines.extend(["", "## Recommendations", ""])
        for rec in report.recommendations:
            lines.append(f"- {rec}")

    return "\n".join(lines) + "\n"


def write_edge_bench_artifacts(
    report: EdgeBenchReport,
    *,
    output_root: Path,
) -> Path:
    run_dir = output_root / report.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "edge_bench_report.md").write_text(
        render_edge_bench_markdown(report), encoding="utf-8"
    )
    (run_dir / "edge_bench_report.json").write_text(
        report.model_dump_json(indent=2), encoding="utf-8"
    )
    return run_dir


def _utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def default_edge_run_id() -> str:
    return "edge_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
