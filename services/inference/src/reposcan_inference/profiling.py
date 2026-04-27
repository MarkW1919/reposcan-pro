"""Inference profiling helpers for Phase 5."""

from __future__ import annotations

from statistics import mean

from pydantic import BaseModel, Field

from reposcan_contracts.config.deployment import DeploymentConfig, TargetHardware
from reposcan_contracts.config.model import ModelStackConfig
from reposcan_contracts.frame import FrameEnvelope

from .service import InferenceService


class InferenceLatencyProfile(BaseModel):
    frames_processed: int = Field(..., ge=0)
    average_latency_ms: float = Field(..., ge=0.0)
    p95_latency_ms: float = Field(..., ge=0.0)
    max_latency_ms: float = Field(..., ge=0.0)
    average_vehicles_per_frame: float = Field(..., ge=0.0)
    average_plates_per_frame: float = Field(..., ge=0.0)
    recommendations: list[str] = Field(default_factory=list)


class InferenceProfiler:
    def __init__(self, inference_service: InferenceService) -> None:
        self.inference_service = inference_service

    def benchmark(self, frames: list[FrameEnvelope], *, deployment: DeploymentConfig | None = None) -> InferenceLatencyProfile:
        candidates = self.inference_service.run_batch(frames)
        if not candidates:
            return InferenceLatencyProfile(
                frames_processed=0,
                average_latency_ms=0.0,
                p95_latency_ms=0.0,
                max_latency_ms=0.0,
                average_vehicles_per_frame=0.0,
                average_plates_per_frame=0.0,
                recommendations=[],
            )

        latencies = sorted(candidate.processing_latency_ms for candidate in candidates)
        p95_index = max(0, int(len(latencies) * 0.95) - 1)
        recommendations = []
        if deployment is not None:
            recommendations = recommend_runtime_tuning(deployment, self.inference_service.model_stack)

        return InferenceLatencyProfile(
            frames_processed=len(candidates),
            average_latency_ms=mean(latencies),
            p95_latency_ms=latencies[p95_index],
            max_latency_ms=max(latencies),
            average_vehicles_per_frame=mean(len(candidate.vehicle_detections) for candidate in candidates),
            average_plates_per_frame=mean(len(candidate.plate_detections) for candidate in candidates),
            recommendations=recommendations,
        )


def recommend_runtime_tuning(deployment: DeploymentConfig, model_stack: ModelStackConfig) -> list[str]:
    recommendations: list[str] = []
    jetson_targets = {
        TargetHardware.jetson_orin,
        TargetHardware.jetson_orin_nano_super,
        TargetHardware.jetson_xavier,
    }
    if deployment.target_hardware in jetson_targets:
        detector_backends = {
            model_stack.vehicle_detector.backend.value,
            model_stack.plate_detector.backend.value,
        }
        if "tensorrt" not in detector_backends:
            recommendations.append("Benchmark TensorRT exports for detector stages on Jetson hardware.")
        if deployment.performance.frame_queue_depth > 24:
            recommendations.append("Reduce frame_queue_depth on Jetson to limit memory pressure.")
        if deployment.target_hardware == TargetHardware.jetson_orin_nano_super:
            if deployment.performance.inference_batch_size > 1:
                recommendations.append("Keep Nano Super detector batching at 1 unless target-hardware benchmarks prove a gain.")
            if deployment.performance.max_active_cameras > 1:
                recommendations.append("Validate multi-camera Nano Super operation with tegrastats before field deployment.")
    else:
        if deployment.performance.inference_batch_size > 1:
            recommendations.append("Validate that batching improves latency on the current CPU profile.")

    if not deployment.performance.enable_profiling:
        recommendations.append("Enable profiling in the deployment config before hardware tuning.")

    if model_stack.classifier is not None and model_stack.classifier.backend.value == "pytorch":
        recommendations.append("Export the classifier to ONNX or TensorRT before edge deployment.")

    return recommendations
