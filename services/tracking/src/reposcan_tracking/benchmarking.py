"""Synthetic but field-shaped tracking benchmark helpers."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable

from reposcan_contracts.config.loader import load_pipeline_config
from reposcan_contracts.config.pipeline import TrackingAlgorithm
from reposcan_contracts.detection import BoundingBox, PlateCandidate
from reposcan_contracts.frame import CameraProfile, FrameEnvelope, SourceType
from reposcan_contracts.inference import AttributePredictions, InferenceCandidate, ModelVersions, PlateDetection, VehicleDetection
from reposcan_contracts.tracking import TrackedDetection
from reposcan_contracts.tracking_benchmark import (
    TrackingAlgorithmBenchmark,
    TrackingScenarioMetrics,
    TrackingStrategyBenchmarkReport,
)

from .service import TrackingService, _bbox_iou, _match_distance


def _utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class _ScenarioObject:
    object_id: str
    bbox: BoundingBox
    plate_bbox: BoundingBox
    plate_text: str
    color: str
    make: str
    model: str


@dataclass(frozen=True)
class _ScenarioFrame:
    frame_number: int
    timestamp_utc: str
    objects: tuple[_ScenarioObject, ...]


@dataclass(frozen=True)
class _TrackingScenario:
    name: str
    description: str
    frames: tuple[_ScenarioFrame, ...]
    expected_final_plates: tuple[str, ...]
    expected_suppressed_duplicates: int


def _iso(base: datetime, seconds: int) -> str:
    return (base + timedelta(seconds=seconds)).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _frame(frame_number: int, timestamp_utc: str) -> FrameEnvelope:
    return FrameEnvelope.model_validate(
        {
            "frame_id": f"trk_bench_{frame_number:04d}",
            "camera_id": "cam_tracking_benchmark_01",
            "timestamp_utc": timestamp_utc,
            "frame_path": f"media/tracking/benchmark/frame_{frame_number:04d}.jpg",
            "frame_number": frame_number,
            "source_type": "file",
            "camera_profile": CameraProfile(
                camera_id="cam_tracking_benchmark_01",
                source_type=SourceType.file,
                resolution_w=640,
                resolution_h=360,
            ).model_dump(mode="json"),
        }
    )


def _candidate(frame_number: int, timestamp_utc: str, objects: Iterable[_ScenarioObject]) -> InferenceCandidate:
    object_list = list(objects)
    return InferenceCandidate.model_validate(
        {
            "frame_id": f"cand_tracking_{frame_number:04d}",
            "camera_id": "cam_tracking_benchmark_01",
            "timestamp_utc": timestamp_utc,
            "vehicle_detections": [
                VehicleDetection(
                    bbox=obj.bbox,
                    confidence=0.92,
                    class_label="car",
                ).model_dump(mode="json")
                for obj in object_list
            ],
            "plate_detections": [
                PlateDetection(
                    bbox=obj.plate_bbox,
                    confidence=0.94,
                    vehicle_index=index,
                ).model_dump(mode="json")
                for index, obj in enumerate(object_list)
            ],
            "ocr_candidates": [
                PlateCandidate(text=obj.plate_text, confidence=0.95).model_dump(mode="json")
                for obj in object_list
            ],
            "attribute_predictions": [
                AttributePredictions(
                    color=obj.color,
                    color_confidence=0.9,
                    make=obj.make,
                    make_confidence=0.88,
                    model=obj.model,
                    model_confidence=0.82,
                ).model_dump(mode="json", by_alias=True)
                for obj in object_list
            ],
            "model_versions": ModelVersions(
                vehicle_detector="fixture_vehicle",
                plate_detector="fixture_plate",
                ocr="fixture_ocr",
                classifier="fixture_attr",
            ).model_dump(mode="json"),
            "processing_latency_ms": 8.0,
        }
    )


def _crossing_scenario() -> _TrackingScenario:
    base = datetime(2026, 3, 24, 18, 30, 0, tzinfo=timezone.utc)
    frames: list[_ScenarioFrame] = []
    positions_a = [120, 165, 210, 255, 300, 345]
    positions_b = [340, 295, 250, 205, 160, 115]
    for index, (xa, xb) in enumerate(zip(positions_a, positions_b), start=1):
        frames.append(
            _ScenarioFrame(
                frame_number=index,
                timestamp_utc=_iso(base, index - 1),
                objects=(
                    _ScenarioObject(
                        object_id="cross_a",
                        bbox=BoundingBox(x=xa, y=150, w=130, h=78),
                        plate_bbox=BoundingBox(x=xa + 38, y=198, w=46, h=14),
                        plate_text="8ABC123",
                        color="white",
                        make="toyota",
                        model="camry",
                    ),
                    _ScenarioObject(
                        object_id="cross_b",
                        bbox=BoundingBox(x=xb, y=150, w=130, h=78),
                        plate_bbox=BoundingBox(x=xb + 38, y=198, w=46, h=14),
                        plate_text="7BLUE42",
                        color="blue",
                        make="honda",
                        model="accord",
                    ),
                ),
            )
        )
    return _TrackingScenario(
        name="crowded_crossing",
        description="Two vehicles cross at similar scale and challenge identity continuity.",
        frames=tuple(frames),
        expected_final_plates=("8ABC123", "7BLUE42"),
        expected_suppressed_duplicates=0,
    )


def _camera_motion_scenario() -> _TrackingScenario:
    base = datetime(2026, 3, 24, 18, 31, 0, tzinfo=timezone.utc)
    frames: list[_ScenarioFrame] = []
    positions = [60, 185, 310, 435, 560]
    for index, x in enumerate(positions, start=1):
        frames.append(
            _ScenarioFrame(
                frame_number=index,
                timestamp_utc=_iso(base, index - 1),
                objects=(
                    _ScenarioObject(
                        object_id="motion_a",
                        bbox=BoundingBox(x=x, y=148, w=130, h=78),
                        plate_bbox=BoundingBox(x=x + 38, y=196, w=46, h=14),
                        plate_text="6BZN220",
                        color="white",
                        make="toyota",
                        model="camry",
                    ),
                ),
            )
        )
    return _TrackingScenario(
        name="camera_motion_drift",
        description="A single vehicle shifts aggressively across the frame as if the camera platform moved.",
        frames=tuple(frames),
        expected_final_plates=("6BZN220",),
        expected_suppressed_duplicates=0,
    )


def _repeat_pass_duplicate_scenario() -> _TrackingScenario:
    base = datetime(2026, 3, 24, 18, 32, 0, tzinfo=timezone.utc)
    frames = (
        _ScenarioFrame(1, _iso(base, 0), (_ScenarioObject("pass_a_1", BoundingBox(x=180, y=155, w=130, h=78), BoundingBox(x=218, y=203, w=46, h=14), "5DUP111", "silver", "ford", "fusion"),)),
        _ScenarioFrame(2, _iso(base, 1), (_ScenarioObject("pass_a_1", BoundingBox(x=195, y=155, w=130, h=78), BoundingBox(x=233, y=203, w=46, h=14), "5DUP111", "silver", "ford", "fusion"),)),
        _ScenarioFrame(3, _iso(base, 2), (_ScenarioObject("pass_a_1", BoundingBox(x=210, y=155, w=130, h=78), BoundingBox(x=248, y=203, w=46, h=14), "5DUP111", "silver", "ford", "fusion"),)),
        _ScenarioFrame(4, _iso(base, 3), tuple()),
        _ScenarioFrame(5, _iso(base, 4), tuple()),
        _ScenarioFrame(6, _iso(base, 5), (_ScenarioObject("pass_a_2", BoundingBox(x=182, y=155, w=130, h=78), BoundingBox(x=220, y=203, w=46, h=14), "5DUP111", "silver", "ford", "fusion"),)),
        _ScenarioFrame(7, _iso(base, 6), (_ScenarioObject("pass_a_2", BoundingBox(x=197, y=155, w=130, h=78), BoundingBox(x=235, y=203, w=46, h=14), "5DUP111", "silver", "ford", "fusion"),)),
        _ScenarioFrame(8, _iso(base, 7), (_ScenarioObject("pass_a_2", BoundingBox(x=212, y=155, w=130, h=78), BoundingBox(x=250, y=203, w=46, h=14), "5DUP111", "silver", "ford", "fusion"),)),
    )
    return _TrackingScenario(
        name="repeat_pass_duplicate_window",
        description="The same vehicle loops back quickly and should be suppressed as a duplicate.",
        frames=frames,
        expected_final_plates=("5DUP111",),
        expected_suppressed_duplicates=1,
    )


def _repeat_pass_after_window_scenario() -> _TrackingScenario:
    base = datetime(2026, 3, 24, 18, 33, 0, tzinfo=timezone.utc)
    frames: list[_ScenarioFrame] = []
    early_positions = [180, 195, 210]
    late_positions = [182, 197, 212]
    for index, x in enumerate(early_positions, start=1):
        frames.append(
            _ScenarioFrame(
                frame_number=index,
                timestamp_utc=_iso(base, index - 1),
                objects=(
                    _ScenarioObject(
                        object_id="late_pass_1",
                        bbox=BoundingBox(x=x, y=150, w=130, h=78),
                        plate_bbox=BoundingBox(x=x + 38, y=198, w=46, h=14),
                        plate_text="6LATE66",
                        color="black",
                        make="chevrolet",
                        model="malibu",
                    ),
                ),
            )
        )
    for frame_number in range(4, 16):
        frames.append(_ScenarioFrame(frame_number=frame_number, timestamp_utc=_iso(base, frame_number - 1), objects=tuple()))
    for offset, x in enumerate(late_positions, start=16):
        frames.append(
            _ScenarioFrame(
                frame_number=offset,
                timestamp_utc=_iso(base, offset - 1),
                objects=(
                    _ScenarioObject(
                        object_id="late_pass_2",
                        bbox=BoundingBox(x=x, y=150, w=130, h=78),
                        plate_bbox=BoundingBox(x=x + 38, y=198, w=46, h=14),
                        plate_text="6LATE66",
                        color="black",
                        make="chevrolet",
                        model="malibu",
                    ),
                ),
            )
        )
    return _TrackingScenario(
        name="repeat_pass_after_window",
        description="The same vehicle returns after the suppression window and should be stored again.",
        frames=tuple(frames),
        expected_final_plates=("6LATE66", "6LATE66"),
        expected_suppressed_duplicates=0,
    )


def _scenario_set() -> tuple[_TrackingScenario, ...]:
    return (
        _crossing_scenario(),
        _camera_motion_scenario(),
        _repeat_pass_duplicate_scenario(),
        _repeat_pass_after_window_scenario(),
    )


def _match_object_to_track(service: TrackingService, obj: _ScenarioObject) -> str | None:
    best_tracker_id: str | None = None
    best_score: tuple[float, float] | None = None
    for tracker_id, track in service._active_tracks.items():
        iou = _bbox_iou(track.current_vehicle_bbox, obj.bbox)
        distance = _match_distance(track.current_vehicle_bbox, obj.bbox)
        score = (iou, -distance)
        if best_score is None or score > best_score:
            best_score = score
            best_tracker_id = tracker_id
    return best_tracker_id


def _plate_match_count(expected: Iterable[str], actual: Iterable[str]) -> int:
    expected_counter = Counter(expected)
    actual_counter = Counter(actual)
    return sum(min(expected_counter[text], actual_counter[text]) for text in expected_counter)


def _score_scenario(
    *,
    plate_exact_matches: int,
    expected_finalized_detections: int,
    finalized_detections: int,
    identity_switches: int,
    expected_suppressed_duplicates: int,
    suppressed_duplicates: int,
) -> float:
    return (
        (plate_exact_matches * 12.0)
        - (abs(expected_finalized_detections - finalized_detections) * 8.0)
        - (identity_switches * 6.0)
        - (abs(expected_suppressed_duplicates - suppressed_duplicates) * 4.0)
    )


def _recommended_algorithm(
    algorithms: dict[str, TrackingAlgorithmBenchmark],
    *,
    default_algorithm: TrackingAlgorithm,
) -> TrackingAlgorithm:
    ordered_preferences = (
        default_algorithm,
        TrackingAlgorithm.deep_sort,
        TrackingAlgorithm.sort,
    )
    return max(
        algorithms.values(),
        key=lambda item: (
            item.total_score,
            -ordered_preferences.index(item.algorithm),
        ),
    ).algorithm


def benchmark_tracking_strategies(*, generated_at_utc: str | None = None) -> TrackingStrategyBenchmarkReport:
    base_pipeline = load_pipeline_config("configs/pipelines/default-edge.yaml")
    algorithms: dict[str, TrackingAlgorithmBenchmark] = {}

    for algorithm in TrackingAlgorithm:
        pipeline = base_pipeline.model_copy(deep=True)
        pipeline.tracking.algorithm = algorithm
        pipeline.tracking.min_hits_to_confirm = 2
        pipeline.tracking.max_lost_frames = 1
        pipeline.fusion.min_ocr_candidates_for_promotion = 1
        scenario_reports: dict[str, TrackingScenarioMetrics] = {}

        for scenario in _scenario_set():
            service = TrackingService(pipeline.model_copy(deep=True))
            last_tracker_by_object: dict[str, str] = {}
            identity_switches = 0
            finalized_detections: list[TrackedDetection] = []
            suppressed_before = service.suppressed_duplicates

            for scenario_frame in scenario.frames:
                frame = _frame(scenario_frame.frame_number, scenario_frame.timestamp_utc)
                candidate = _candidate(scenario_frame.frame_number, scenario_frame.timestamp_utc, scenario_frame.objects)
                finalized_detections.extend(service.ingest(frame, candidate))

                for scenario_object in scenario_frame.objects:
                    tracker_id = _match_object_to_track(service, scenario_object)
                    previous_tracker_id = last_tracker_by_object.get(scenario_object.object_id)
                    if previous_tracker_id is not None and tracker_id is not None and previous_tracker_id != tracker_id:
                        identity_switches += 1
                    if tracker_id is not None:
                        last_tracker_by_object[scenario_object.object_id] = tracker_id

            finalized_detections.extend(service.flush(camera_id="cam_tracking_benchmark_01"))
            actual_plates = [
                detection.best_plate_candidate.text
                for detection in finalized_detections
                if detection.best_plate_candidate is not None
            ]
            plate_exact_matches = _plate_match_count(scenario.expected_final_plates, actual_plates)
            suppressed_after = service.suppressed_duplicates
            suppressed_duplicates = suppressed_after - suppressed_before

            metrics = TrackingScenarioMetrics(
                frames=len(scenario.frames),
                expected_objects=len({obj.object_id for frame in scenario.frames for obj in frame.objects}),
                finalized_detections=len(finalized_detections),
                expected_finalized_detections=len(scenario.expected_final_plates),
                plate_exact_matches=plate_exact_matches,
                identity_switches=identity_switches,
                suppressed_duplicates=suppressed_duplicates,
                score=_score_scenario(
                    plate_exact_matches=plate_exact_matches,
                    expected_finalized_detections=len(scenario.expected_final_plates),
                    finalized_detections=len(finalized_detections),
                    identity_switches=identity_switches,
                    expected_suppressed_duplicates=scenario.expected_suppressed_duplicates,
                    suppressed_duplicates=suppressed_duplicates,
                ),
            )
            scenario_reports[scenario.name] = metrics

        total_score = sum(item.score for item in scenario_reports.values())
        algorithms[algorithm.value] = TrackingAlgorithmBenchmark(
            algorithm=algorithm,
            scenarios=scenario_reports,
            total_score=total_score,
        )

    recommended = _recommended_algorithm(
        algorithms,
        default_algorithm=base_pipeline.tracking.algorithm,
    )
    return TrackingStrategyBenchmarkReport(
        benchmark_name="tracking-strategy-field-relevant-workloads",
        generated_at_utc=generated_at_utc or _utcnow(),
        recommended_algorithm=recommended,
        algorithms=algorithms,
    )
