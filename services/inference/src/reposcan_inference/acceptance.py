"""Acceptance-run post-processing for promoted-model benchmarks.

The acceptance harness reuses ``benchmark_promoted_model`` to score a
field-captured ``eval_holdout`` dataset. This module maps the raw benchmark
subsets onto the three hardware-gated acceptance lanes defined in the project
status checklist (long-range readability, low-light/no-light, and
moving-vehicle/moving-platform) and renders the evidence artifacts that the
production-readiness review register consumes.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from pydantic import BaseModel, Field

from reposcan_contracts.benchmark import (
    BenchmarkFrameExpectation,
    BenchmarkSubsetMetrics,
    PromotedModelBenchmarkManifest,
    PromotedModelBenchmarkReport,
)

LONG_RANGE_LANE = "long_range"
LOW_LIGHT_LANE = "low_light"
MOVING_PLATFORM_LANE = "moving_platform"

ACCEPTANCE_LANES: tuple[str, ...] = (LONG_RANGE_LANE, LOW_LIGHT_LANE, MOVING_PLATFORM_LANE)

_LANE_SOURCE_TAGS: dict[str, frozenset[str]] = {
    LONG_RANGE_LANE: frozenset({"long_range"}),
    LOW_LIGHT_LANE: frozenset({"low_light", "dusk", "night", "no_light", "ir_assisted", "glare"}),
    MOVING_PLATFORM_LANE: frozenset({"moving_platform", "moving_vehicle"}),
}

_LANE_TAG_PREFIX = "lane:"


def _lane_tag(lane: str) -> str:
    return f"{_LANE_TAG_PREFIX}{lane}"


def frame_lanes(tags: Iterable[str]) -> list[str]:
    """Return the acceptance lanes a frame belongs to based on its source tags.

    A frame can belong to more than one lane (a night long-range shot feeds
    both long-range and low-light acceptance runs).
    """

    tag_set = {tag for tag in tags if tag}
    matched = []
    for lane in ACCEPTANCE_LANES:
        if tag_set & _LANE_SOURCE_TAGS[lane]:
            matched.append(lane)
    return matched


def stamp_acceptance_lanes(manifest: PromotedModelBenchmarkManifest) -> PromotedModelBenchmarkManifest:
    """Return a new benchmark manifest with acceptance-lane tags appended to every frame.

    The input manifest is not mutated. The downstream benchmark pipeline then
    reports ``subsets['lane:<name>']`` alongside the raw subset tags without
    re-scoring any frame twice.
    """

    stamped_frames: list[BenchmarkFrameExpectation] = []
    for frame in manifest.frames:
        lanes = frame_lanes(frame.tags)
        if lanes:
            extra = [_lane_tag(lane) for lane in lanes if _lane_tag(lane) not in frame.tags]
            new_tags = list(frame.tags) + extra
        else:
            new_tags = list(frame.tags)
        stamped_frames.append(frame.model_copy(update={"tags": new_tags}))

    return manifest.model_copy(update={"frames": stamped_frames})


class AcceptanceLaneReport(BaseModel):
    lane: str = Field(..., min_length=1)
    status: str = Field(..., min_length=1)
    frames: int = Field(..., ge=0)
    source_tags: list[str] = Field(default_factory=list)
    metrics: BenchmarkSubsetMetrics | None = None


class AcceptanceRunReport(BaseModel):
    run_id: str = Field(..., min_length=1)
    generated_at_utc: str = Field(..., min_length=1)
    benchmark_name: str = Field(..., min_length=1)
    model_stack_name: str = Field(..., min_length=1)
    source_dataset_name: str | None = None
    source_dataset_version: str | None = None
    source_dataset_manifest_path: str | None = None
    benchmark_manifest_path: str | None = None
    deployment_name: str | None = None
    runtime_ready: bool | None = None
    promotion_ready: bool | None = None
    deployment_ready: bool | None = None
    overall: BenchmarkSubsetMetrics
    lanes: list[AcceptanceLaneReport]


def _lane_metrics(report: PromotedModelBenchmarkReport, lane: str) -> BenchmarkSubsetMetrics | None:
    return report.subsets.get(_lane_tag(lane))


def _lane_status(metrics: BenchmarkSubsetMetrics | None) -> str:
    if metrics is None or metrics.frames == 0:
        return "not_evaluated"
    return "evaluated"


def build_acceptance_run_report(
    benchmark_report: PromotedModelBenchmarkReport,
    *,
    run_id: str,
    generated_at_utc: str | None = None,
) -> AcceptanceRunReport:
    """Reshape a benchmark report into an acceptance-run report keyed by lane."""

    lanes: list[AcceptanceLaneReport] = []
    for lane in ACCEPTANCE_LANES:
        metrics = _lane_metrics(benchmark_report, lane)
        lanes.append(
            AcceptanceLaneReport(
                lane=lane,
                status=_lane_status(metrics),
                frames=metrics.frames if metrics is not None else 0,
                source_tags=sorted(_LANE_SOURCE_TAGS[lane]),
                metrics=metrics,
            )
        )

    return AcceptanceRunReport(
        run_id=run_id,
        generated_at_utc=generated_at_utc or _utcnow(),
        benchmark_name=benchmark_report.benchmark_name,
        model_stack_name=benchmark_report.model_stack_name,
        source_dataset_name=benchmark_report.source_dataset_name,
        source_dataset_version=benchmark_report.source_dataset_version,
        source_dataset_manifest_path=benchmark_report.source_dataset_manifest_path,
        benchmark_manifest_path=benchmark_report.benchmark_manifest_path,
        deployment_name=benchmark_report.validation.deployment_name if benchmark_report.validation else None,
        runtime_ready=benchmark_report.validation.runtime_ready if benchmark_report.validation else None,
        promotion_ready=benchmark_report.validation.promotion_ready if benchmark_report.validation else None,
        deployment_ready=benchmark_report.validation.deployment_ready if benchmark_report.validation else None,
        overall=benchmark_report.overall,
        lanes=lanes,
    )


def _format_rate(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.3f}"


def _format_latency(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.1f} ms"


def _metrics_table(metrics: BenchmarkSubsetMetrics) -> str:
    rows = [
        ("frames", str(metrics.frames)),
        ("exact_match_rate", _format_rate(metrics.exact_match_rate)),
        ("character_accuracy", _format_rate(metrics.character_accuracy)),
        ("color_accuracy", _format_rate(metrics.color_accuracy)),
        ("make_accuracy", _format_rate(metrics.make_accuracy)),
        ("average_latency_ms", _format_latency(metrics.average_latency_ms)),
        ("p95_latency_ms", _format_latency(metrics.p95_latency_ms)),
        ("max_latency_ms", _format_latency(metrics.max_latency_ms)),
        ("average_vehicles_per_frame", _format_rate(metrics.average_vehicles_per_frame)),
        ("average_plates_per_frame", _format_rate(metrics.average_plates_per_frame)),
    ]
    lines = ["| metric | value |", "|---|---|"]
    for name, value in rows:
        lines.append(f"| {name} | {value} |")
    return "\n".join(lines)


def render_overall_markdown(report: AcceptanceRunReport) -> str:
    lines = [
        f"# Acceptance run {report.run_id}",
        "",
        f"- generated at: {report.generated_at_utc}",
        f"- benchmark: {report.benchmark_name}",
        f"- model stack: {report.model_stack_name}",
    ]
    if report.source_dataset_name:
        version = report.source_dataset_version or "n/a"
        lines.append(f"- source dataset: {report.source_dataset_name} ({version})")
    if report.source_dataset_manifest_path:
        lines.append(f"- source manifest: {report.source_dataset_manifest_path}")
    if report.deployment_name:
        lines.append(f"- deployment profile: {report.deployment_name}")
    if report.runtime_ready is not None:
        lines.append(f"- runtime ready: {report.runtime_ready}")
    if report.promotion_ready is not None:
        lines.append(f"- promotion ready: {report.promotion_ready}")
    if report.deployment_ready is not None:
        lines.append(f"- deployment ready: {report.deployment_ready}")
    lines.extend(["", "## Overall metrics", "", _metrics_table(report.overall), ""])

    lines.append("## Lane summary")
    lines.append("")
    lines.append("| lane | status | frames | exact_match | char_accuracy |")
    lines.append("|---|---|---|---|---|")
    for lane in report.lanes:
        metrics = lane.metrics
        exact_match = _format_rate(metrics.exact_match_rate) if metrics else "n/a"
        char_accuracy = _format_rate(metrics.character_accuracy) if metrics else "n/a"
        lines.append(
            f"| {lane.lane} | {lane.status} | {lane.frames} | {exact_match} | {char_accuracy} |"
        )
    lines.append("")
    lines.append("See per-lane reports for detailed metrics and source tags.")
    return "\n".join(lines) + "\n"


def render_lane_markdown(report: AcceptanceRunReport, lane: str) -> str:
    lane_report = next((entry for entry in report.lanes if entry.lane == lane), None)
    if lane_report is None:
        raise ValueError(f"unknown acceptance lane: {lane}")

    lines = [
        f"# Acceptance lane report: {lane}",
        "",
        f"- run id: {report.run_id}",
        f"- generated at: {report.generated_at_utc}",
        f"- benchmark: {report.benchmark_name}",
        f"- model stack: {report.model_stack_name}",
        f"- source tags that feed this lane: {', '.join(lane_report.source_tags)}",
        f"- frames evaluated in this lane: {lane_report.frames}",
        f"- status: {lane_report.status}",
        "",
    ]

    if lane_report.metrics is None or lane_report.frames == 0:
        lines.extend(
            [
                "## Metrics",
                "",
                "No frames in the source manifest carried tags that route into this lane.",
                "Tag the relevant assets in the eval-holdout manifest before re-running the acceptance harness.",
                "",
                "Expected source tags for this lane: " + ", ".join(lane_report.source_tags),
                "",
            ]
        )
        return "\n".join(lines) + "\n"

    lines.extend(["## Metrics", "", _metrics_table(lane_report.metrics), ""])
    return "\n".join(lines) + "\n"


def _utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def default_run_id() -> str:
    return "acc_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def lane_report_filenames() -> dict[str, str]:
    return {
        LONG_RANGE_LANE: "long_range_report.md",
        LOW_LIGHT_LANE: "low_light_report.md",
        MOVING_PLATFORM_LANE: "moving_platform_report.md",
    }


def write_acceptance_artifacts(
    report: AcceptanceRunReport,
    *,
    output_root: Path,
) -> Path:
    """Write the acceptance run artifacts to ``output_root/<run_id>/`` and return the folder."""

    run_dir = output_root / report.run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    overall_md_path = run_dir / "overall_report.md"
    overall_md_path.write_text(render_overall_markdown(report), encoding="utf-8")

    for lane, filename in lane_report_filenames().items():
        (run_dir / filename).write_text(render_lane_markdown(report, lane), encoding="utf-8")

    sidecar_path = run_dir / "acceptance_report.json"
    sidecar_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")

    return run_dir
