"""Headless runtime helpers for local ingest-to-storage simulations."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from reposcan_alerting import AlertingService
from reposcan_capture import CaptureService, FileSequenceFrameSource
from reposcan_contracts.alert import AlertRecord
from reposcan_contracts.config.camera import CameraConfig
from reposcan_contracts.config.loader import load_camera_config, load_model_config, load_pipeline_config
from reposcan_contracts.config.model import ModelStackConfig
from reposcan_contracts.detection import PlateCandidate
from reposcan_contracts.frame import FrameEnvelope, GpsSnapshot
from reposcan_contracts.inference import AttributePredictions, InferenceCandidate, PlateDetection, VehicleDetection
from reposcan_contracts.tracking import TrackedDetection
from reposcan_preprocessing import PreprocessingService
from reposcan_storage.service import StorageService, create_development_storage_service
from reposcan_tracking import TrackingService

from .adapters import (
    ModelAdapterBundle,
    StaticClassifierAdapter,
    StaticOcrAdapter,
    StaticPlateDetectorAdapter,
    StaticVehicleDetectorAdapter,
)
from .service import InferenceService
from .workflow import FrameToCandidateWorkflow


@dataclass
class FrameEnvelopeQueue:
    """Simple in-process queue for capture-to-processing handoff."""

    _items: deque[FrameEnvelope] = field(default_factory=deque)

    def put(self, frame: FrameEnvelope) -> None:
        self._items.append(frame)

    def drain(self) -> list[FrameEnvelope]:
        drained = list(self._items)
        self._items.clear()
        return drained

    def __len__(self) -> int:
        return len(self._items)


@dataclass(frozen=True)
class HeadlessRunSummary:
    frames_captured: int
    candidates_processed: int
    tracks_finalized: int
    stored_detection_ids: list[str]
    created_alert_ids: list[str]


def build_demo_adapter_bundle(
    model_stack: ModelStackConfig,
    *,
    plate_text: str = "6BZN220",
) -> ModelAdapterBundle:
    """Create deterministic stub adapters for local file-sequence simulations."""

    classifier = None
    if model_stack.classifier is not None:
        classifier = StaticClassifierAdapter(
            model_stack.classifier,
            outputs=[
                AttributePredictions.model_validate(
                    {
                        "color": "white",
                        "color_confidence": 0.89,
                        "make": "toyota",
                        "make_confidence": 0.82,
                        "model": "camry",
                        "model_confidence": 0.78,
                        "year": "2018-2021",
                        "year_confidence": 0.66,
                    }
                )
            ],
        )

    return ModelAdapterBundle(
        vehicle_detector=StaticVehicleDetectorAdapter(
            model_stack.vehicle_detector,
            outputs=[
                VehicleDetection.model_validate(
                    {
                        "bbox": {"x": 416, "y": 212, "w": 320, "h": 188},
                        "confidence": 0.91,
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
                        "bbox": {"x": 524, "y": 336, "w": 94, "h": 30},
                        "confidence": 0.88,
                        "vehicle_index": 0,
                    }
                )
            ],
        ),
        ocr=StaticOcrAdapter(
            model_stack.ocr,
            outputs=[PlateCandidate.model_validate({"text": plate_text, "confidence": 0.93})],
        ),
        classifier=classifier,
    )


class HeadlessFileSequenceRunner:
    """Drive a file-backed frame sequence through capture, inference, tracking, and storage."""

    def __init__(
        self,
        *,
        camera: CameraConfig,
        capture_service: CaptureService,
        frame_queue: FrameEnvelopeQueue,
        candidate_workflow: FrameToCandidateWorkflow,
        tracking_service: TrackingService,
        alerting_service: AlertingService,
        storage_service: StorageService,
    ) -> None:
        self.camera = camera
        self.capture_service = capture_service
        self.frame_queue = frame_queue
        self.candidate_workflow = candidate_workflow
        self.tracking_service = tracking_service
        self.alerting_service = alerting_service
        self.storage_service = storage_service

    @classmethod
    def from_config_paths(
        cls,
        *,
        camera_config_path: str | Path = "configs/cameras/local-file-demo.yaml",
        model_config_path: str | Path = "configs/models/example-model-stack.yaml",
        pipeline_config_path: str | Path = "configs/pipelines/default-edge.yaml",
        deployment_config_path: str | Path = "configs/deployments/local-dev.yaml",
        metadata_root: str | Path = "runtime/storage",
        preprocessed_root: str | Path = "runtime/preprocessed",
        plate_text: str = "6BZN220",
        storage_service: StorageService | None = None,
    ) -> "HeadlessFileSequenceRunner":
        camera = load_camera_config(camera_config_path)
        model_stack = load_model_config(model_config_path)
        adapters = build_demo_adapter_bundle(model_stack, plate_text=plate_text)
        inference_service = InferenceService.from_config_paths(
            model_config_path=str(model_config_path),
            pipeline_config_path=str(pipeline_config_path),
            adapters=adapters,
        )
        pipeline_config = load_pipeline_config(pipeline_config_path)

        return cls(
            camera=camera,
            capture_service=CaptureService(),
            frame_queue=FrameEnvelopeQueue(),
            candidate_workflow=FrameToCandidateWorkflow(
                inference_service=inference_service,
                preprocessing_service=PreprocessingService(
                    pipeline_config,
                    artifact_root=preprocessed_root,
                ),
            ),
            tracking_service=TrackingService.from_config_path(str(pipeline_config_path)),
            alerting_service=AlertingService.from_config_path(str(pipeline_config_path)),
            storage_service=storage_service
            or create_development_storage_service(
                deployment_config_path=deployment_config_path,
                metadata_root=metadata_root,
            ),
        )

    def minimum_frames_required(self) -> int:
        return max(
            self.tracking_service.pipeline_config.tracking.min_hits_to_confirm,
            self.tracking_service.pipeline_config.fusion.min_ocr_candidates_for_promotion,
        )

    def _default_gps_snapshot(self) -> GpsSnapshot | None:
        if self.camera.mounting.gps_latitude is None or self.camera.mounting.gps_longitude is None:
            return None
        return GpsSnapshot(
            latitude=self.camera.mounting.gps_latitude,
            longitude=self.camera.mounting.gps_longitude,
            accuracy_m=self.camera.mounting.gps_accuracy_m,
        )

    def enqueue_source(self, source: Iterable) -> int:
        count = 0
        for captured_frame in source:
            self.frame_queue.put(self.capture_service.capture_frame(self.camera, captured_frame))
            count += 1
        return count

    def process_enqueued_frames(self) -> HeadlessRunSummary:
        finalized_tracks: list[TrackedDetection] = []
        processed_count = 0

        for frame in self.frame_queue.drain():
            candidate: InferenceCandidate = self.candidate_workflow.process(frame)
            finalized_tracks.extend(self.tracking_service.ingest(frame, candidate))
            processed_count += 1

        finalized_tracks.extend(self.tracking_service.flush(camera_id=self.camera.camera_id))
        stored_detections = [self.storage_service.store_tracked_detection(track) for track in finalized_tracks]

        created_alerts: list[AlertRecord] = []
        active_hotlists = self.storage_service.list_hotlists(active_only=True, limit=500)
        for track in finalized_tracks:
            alert = self.alerting_service.evaluate(track, active_hotlists)
            if alert is None:
                continue
            created_alerts.append(self.storage_service.store_alert(alert))

        return HeadlessRunSummary(
            frames_captured=processed_count,
            candidates_processed=processed_count,
            tracks_finalized=len(finalized_tracks),
            stored_detection_ids=[record.detection_id for record in stored_detections],
            created_alert_ids=[record.alert_id for record in created_alerts],
        )

    def run_file_sequence(
        self,
        frames_directory: str | Path,
        *,
        start_timestamp_utc: str,
        frame_interval_ms: float = 33.3,
        glob_pattern: str = "*.jpg",
        start_frame_number: int = 0,
        sequence_id: str | None = None,
    ) -> HeadlessRunSummary:
        source = FileSequenceFrameSource.from_directory(
            frames_directory,
            glob_pattern=glob_pattern,
            start_timestamp_utc=start_timestamp_utc,
            frame_interval_ms=frame_interval_ms,
            start_frame_number=start_frame_number,
            sequence_id=sequence_id,
            gps_snapshot=self._default_gps_snapshot(),
        )

        if not source.frame_paths:
            raise ValueError(f"No frame files found in '{Path(frames_directory)}' using pattern '{glob_pattern}'")

        minimum_frames = self.minimum_frames_required()
        if len(source.frame_paths) < minimum_frames:
            raise ValueError(
                f"At least {minimum_frames} frames are required for the current tracking and OCR promotion settings; "
                f"found {len(source.frame_paths)}."
            )

        captured = self.enqueue_source(source)
        summary = self.process_enqueued_frames()
        return HeadlessRunSummary(
            frames_captured=captured,
            candidates_processed=summary.candidates_processed,
            tracks_finalized=summary.tracks_finalized,
            stored_detection_ids=summary.stored_detection_ids,
            created_alert_ids=summary.created_alert_ids,
        )
