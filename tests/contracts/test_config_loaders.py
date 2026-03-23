"""Tests for config schemas and YAML loaders.

These tests load the example YAML files shipped in configs/ and verify:
1. The example configs parse cleanly against their schema.
2. Loader errors are surfaced clearly for bad inputs.
3. All documented config fields exist on the schema.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from reposcan_contracts.config.loader import (
    ConfigLoadError,
    load_benchmark_manifest,
    load_camera_config,
    load_dataset_split_manifest,
    load_deployment_config,
    load_model_config,
    load_pipeline_config,
    load_training_dataset_manifest,
    load_training_profile,
)
from reposcan_contracts.config.camera import CameraConfig, SourceType, ColorMode
from reposcan_contracts.dataset import (
    DatasetFormat,
    DatasetReviewStatus,
    DatasetSplit,
    DatasetTask,
)
from reposcan_contracts.training import DatasetAdapter, TrainingFramework
from reposcan_contracts.config.model import ArtifactPathBase, ModelStackConfig, InferenceBackend
from reposcan_contracts.config.pipeline import PipelineConfig, PlateDetectionStrategy, PreprocessingBackend
from reposcan_contracts.config.deployment import DeploymentConfig, TargetHardware


CONFIGS = Path(__file__).parent.parent.parent / "configs"


# ---------------------------------------------------------------------------
# Camera config
# ---------------------------------------------------------------------------

class TestCameraConfigSchema:
    def test_example_file_parses(self):
        cam = load_camera_config(CONFIGS / "cameras" / "example-camera.yaml")
        assert cam.camera_id == "cam_north_gate_01"
        assert cam.source_type == SourceType.rtsp
        assert cam.enabled is True

    def test_usb_example_file_parses(self):
        cam = load_camera_config(CONFIGS / "cameras" / "example-usb-camera.yaml")
        assert cam.camera_id == "cam_cab_usb_01"
        assert cam.source_type == SourceType.usb
        assert cam.device_index == 0

    def test_sensor_fields(self):
        cam = load_camera_config(CONFIGS / "cameras" / "example-camera.yaml")
        assert cam.sensor.resolution_w == 3840
        assert cam.sensor.color_mode == ColorMode.color

    def test_optics_ir_illuminator(self):
        cam = load_camera_config(CONFIGS / "cameras" / "example-camera.yaml")
        assert cam.optics.ir_illuminator is True
        assert cam.optics.ir_wavelength_nm == 940

    def test_mounting_gps(self):
        cam = load_camera_config(CONFIGS / "cameras" / "example-camera.yaml")
        assert cam.mounting.gps_latitude == pytest.approx(34.12345)

    def test_missing_file_raises_config_load_error(self, tmp_path):
        with pytest.raises(ConfigLoadError) as exc_info:
            load_camera_config(tmp_path / "does_not_exist.yaml")
        assert "file not found" in str(exc_info.value)

    def test_invalid_yaml_raises_config_load_error(self, tmp_path):
        bad = tmp_path / "bad.yaml"
        bad.write_text("{{invalid: yaml: content")
        with pytest.raises(ConfigLoadError):
            load_camera_config(bad)

    def test_schema_validation_error_raises_config_load_error(self, tmp_path):
        bad = tmp_path / "cam.yaml"
        bad.write_text("camera_id: test\nsource_type: invalid_type\n")
        with pytest.raises(ConfigLoadError):
            load_camera_config(bad)

    def test_minimal_valid_from_dict(self):
        cam = CameraConfig.model_validate({
            "camera_id": "cam_test",
            "source_type": "usb",
            "device_index": 0,
        })
        assert cam.camera_id == "cam_test"
        assert cam.enabled is True

    def test_rtsp_accepts_stream_url(self):
        cam = CameraConfig.model_validate({
            "camera_id": "cam_rtsp",
            "source_type": "rtsp",
            "stream_url": "rtsp://10.0.0.1/stream",
        })
        assert cam.stream_url == "rtsp://10.0.0.1/stream"

    def test_usb_requires_device_index(self):
        with pytest.raises(ValidationError):
            CameraConfig.model_validate({
                "camera_id": "cam_usb",
                "source_type": "usb",
            })

    def test_rtsp_requires_stream_url(self):
        with pytest.raises(ValidationError):
            CameraConfig.model_validate({
                "camera_id": "cam_rtsp",
                "source_type": "rtsp",
            })

    def test_usb_rejects_stream_url(self):
        with pytest.raises(ValidationError):
            CameraConfig.model_validate({
                "camera_id": "cam_usb",
                "source_type": "usb",
                "device_index": 0,
                "stream_url": "rtsp://10.0.0.1/stream",
            })


# ---------------------------------------------------------------------------
# Model stack config
# ---------------------------------------------------------------------------

class TestModelStackConfigSchema:
    def test_example_file_parses(self):
        stack = load_model_config(CONFIGS / "models" / "example-model-stack.yaml")
        assert stack.stack_name == "default-lpr-stack"

    def test_local_demo_runtime_file_parses(self):
        stack = load_model_config(CONFIGS / "models" / "local-demo-runtime.yaml")
        assert stack.stack_name == "local-demo-runtime"
        assert stack.path_base == ArtifactPathBase.repo_root
        assert stack.vehicle_detector.backend == InferenceBackend.builtin
        assert stack.ocr.backend == InferenceBackend.builtin
        assert stack.classifier is not None
        assert stack.classifier.backend == InferenceBackend.builtin

    def test_local_onnx_runtime_file_parses(self):
        stack = load_model_config(CONFIGS / "models" / "local-onnx-runtime.yaml")
        assert stack.stack_name == "local-onnx-runtime"
        assert stack.path_base == ArtifactPathBase.repo_root
        assert stack.vehicle_detector.backend == InferenceBackend.onnx
        assert stack.plate_detector.backend == InferenceBackend.onnx
        assert stack.ocr.backend == InferenceBackend.onnx
        assert stack.classifier is not None
        assert stack.classifier.backend == InferenceBackend.onnx

    def test_promoted_onnx_template_parses(self):
        stack = load_model_config(CONFIGS / "models" / "promoted-onnx-template.yaml")
        assert stack.stack_name == "promoted-onnx-template"
        assert stack.path_base == ArtifactPathBase.config_dir
        assert stack.vehicle_detector.artifact_manifest_path is not None
        assert stack.ocr.artifact_manifest_path is not None
        assert stack.classifier is not None
        assert stack.classifier.artifact_manifest_path is not None

    def test_promoted_tensorrt_template_parses(self):
        stack = load_model_config(CONFIGS / "models" / "promoted-tensorrt-template.yaml")
        assert stack.stack_name == "promoted-tensorrt-template"
        assert stack.path_base == ArtifactPathBase.config_dir
        assert stack.vehicle_detector.backend == InferenceBackend.tensorrt
        assert stack.vehicle_detector.artifact_manifest_path is not None
        assert stack.classifier is not None
        assert stack.classifier.backend == InferenceBackend.tensorrt

    def test_vehicle_detector_fields(self):
        stack = load_model_config(CONFIGS / "models" / "example-model-stack.yaml")
        vd = stack.vehicle_detector
        assert vd.backend == InferenceBackend.onnx
        assert vd.input_width == 640
        assert "car" in vd.class_labels

    def test_ocr_charset_nonempty(self):
        stack = load_model_config(CONFIGS / "models" / "example-model-stack.yaml")
        assert len(stack.ocr.charset) > 0

    def test_classifier_optional(self):
        stack = ModelStackConfig.model_validate({
            "stack_name": "no-classifier",
            "vehicle_detector": {
                "name": "vd", "artifact_path": "a.onnx", "input_width": 640, "input_height": 640,
            },
            "plate_detector": {
                "name": "pd", "artifact_path": "b.onnx", "input_width": 640, "input_height": 640,
            },
            "ocr": {
                "name": "ocr", "artifact_path": "c.onnx",
                "input_width": 94, "input_height": 24, "charset": "ABC",
            },
        })
        assert stack.classifier is None

    def test_confidence_threshold_bounds(self):
        with pytest.raises(ValidationError):
            ModelStackConfig.model_validate({
                "stack_name": "bad",
                "vehicle_detector": {
                    "name": "vd", "artifact_path": "a.onnx",
                    "input_width": 640, "input_height": 640,
                    "confidence_threshold": 1.5,  # invalid
                },
                "plate_detector": {
                    "name": "pd", "artifact_path": "b.onnx", "input_width": 640, "input_height": 640,
                },
                "ocr": {
                    "name": "ocr", "artifact_path": "c.onnx",
                    "input_width": 94, "input_height": 24, "charset": "ABC",
                },
            })


# ---------------------------------------------------------------------------
# Pipeline config
# ---------------------------------------------------------------------------

class TestPipelineConfigSchema:
    def test_example_file_parses(self):
        pipeline = load_pipeline_config(CONFIGS / "pipelines" / "default-edge.yaml")
        assert pipeline.pipeline_name == "default-edge"
        assert pipeline.plate_detection_strategy == PlateDetectionStrategy.vehicle_crop

    def test_preprocessing_defaults(self):
        pipeline = load_pipeline_config(CONFIGS / "pipelines" / "default-edge.yaml")
        assert pipeline.preprocessing.enabled is True
        assert pipeline.preprocessing.denoise is True
        assert pipeline.preprocessing.enhancement_backend == PreprocessingBackend.auto
        assert pipeline.preprocessing.exposure_compensation is True
        assert pipeline.preprocessing.rectify_plate_crops is True

    def test_thresholds(self):
        pipeline = load_pipeline_config(CONFIGS / "pipelines" / "default-edge.yaml")
        assert pipeline.thresholds.alert_min_plate_confidence == pytest.approx(0.7)

    def test_tracking_algorithm(self):
        pipeline = load_pipeline_config(CONFIGS / "pipelines" / "default-edge.yaml")
        assert pipeline.tracking.algorithm.value == "byte_tracker"

    def test_fusion_promotion_threshold(self):
        pipeline = load_pipeline_config(CONFIGS / "pipelines" / "default-edge.yaml")
        assert pipeline.fusion.promote_best_read_threshold == pytest.approx(0.8)

    def test_all_plate_detection_strategies_valid(self):
        for strategy in PlateDetectionStrategy:
            p = PipelineConfig.model_validate({
                "pipeline_name": "test",
                "plate_detection_strategy": strategy.value,
            })
            assert p.plate_detection_strategy == strategy


# ---------------------------------------------------------------------------
# Deployment config
# ---------------------------------------------------------------------------

class TestDeploymentConfigSchema:
    def test_example_file_parses(self):
        dep = load_deployment_config(CONFIGS / "deployments" / "local-dev.yaml")
        assert dep.deployment_name == "local-dev"
        assert dep.target_hardware == TargetHardware.cpu

    def test_sync_disabled_in_local_dev(self):
        dep = load_deployment_config(CONFIGS / "deployments" / "local-dev.yaml")
        assert dep.enabled_services.sync is False
        assert dep.runtime.required_backend == InferenceBackend.onnx
        assert dep.runtime.target_runtime == "onnxruntime"

    def test_all_core_services_enabled(self):
        dep = load_deployment_config(CONFIGS / "deployments" / "local-dev.yaml")
        svc = dep.enabled_services
        assert all([svc.capture, svc.inference, svc.storage, svc.api])

    def test_media_retention_days(self):
        dep = load_deployment_config(CONFIGS / "deployments" / "local-dev.yaml")
        assert dep.media_retention.frames_days == 7
        assert dep.media_retention.crops_days == 30

    def test_profiling_enabled_in_local_dev(self):
        dep = load_deployment_config(CONFIGS / "deployments" / "local-dev.yaml")
        assert dep.performance.enable_profiling is True

    def test_jetson_orin_profile_parses(self):
        dep = load_deployment_config(CONFIGS / "deployments" / "jetson-orin-edge.yaml")
        assert dep.target_hardware == TargetHardware.jetson_orin
        assert dep.enabled_services.sync is True
        assert dep.performance.frame_queue_depth == 16
        assert dep.runtime.required_backend == InferenceBackend.tensorrt
        assert dep.runtime.required_path_base == ArtifactPathBase.config_dir
        assert dep.runtime.required_cuda_version == "12.2"
        assert dep.runtime.required_tensorrt_version == "10.0.1"
        assert dep.runtime.required_compute_capability == "8.7"

    def test_invalid_port_rejected(self):
        with pytest.raises(ValidationError):
            DeploymentConfig.model_validate({
                "deployment_name": "bad",
                "infrastructure": {"api_port": 99999},
            })

    def test_non_mapping_yaml_raises_config_load_error(self, tmp_path):
        bad = tmp_path / "dep.yaml"
        bad.write_text("- item1\n- item2\n")
        with pytest.raises(ConfigLoadError) as exc_info:
            load_deployment_config(bad)
        assert "mapping" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Benchmark manifest
# ---------------------------------------------------------------------------

class TestBenchmarkManifestSchema:
    def test_example_benchmark_manifest_parses(self):
        manifest = load_benchmark_manifest(CONFIGS / "benchmarks" / "example-promoted-onnx-benchmark.yaml")
        assert manifest.benchmark_name == "example-promoted-onnx-benchmark"
        assert manifest.camera_id == "cam_benchmark_01"
        assert len(manifest.frames) == 2
        assert "long_range" in manifest.frames[0].tags

    def test_benchmark_manifest_requires_frames(self, tmp_path):
        bad = tmp_path / "benchmark.yaml"
        bad.write_text("benchmark_name: empty-benchmark\nframes: []\n", encoding="utf-8")
        with pytest.raises(ConfigLoadError):
            load_benchmark_manifest(bad)


class TestTrainingDatasetManifestSchema:
    def test_capture_intake_manifest_parses(self):
        manifest = load_training_dataset_manifest(CONFIGS / "datasets" / "example-capture-intake.yaml")
        assert manifest.dataset_name == "example-oklahoma-capture-intake"
        assert manifest.task == DatasetTask.plate_detection
        assert manifest.format == DatasetFormat.generic_capture
        assert manifest.review_status == DatasetReviewStatus.approved
        assert len(manifest.assets) == 3

    def test_integrated_training_dataset_manifest_parses(self):
        manifest = load_training_dataset_manifest(CONFIGS / "datasets" / "example-integrated-training-dataset.yaml")
        assert manifest.dataset_name == "example-stanford-cars-warmstart"
        assert manifest.task == DatasetTask.vehicle_make_model_classification
        assert manifest.format == DatasetFormat.imagefolder
        assert len(manifest.splits) == 2

    def test_dataset_split_manifest_parses(self):
        manifest = load_dataset_split_manifest(CONFIGS / "datasets" / "example-dataset-split.yaml")
        assert manifest.dataset_name == "example-oklahoma-capture-intake"
        assert manifest.assignments[0].split == DatasetSplit.field_eval

    def test_approved_dataset_requires_annotation_review(self, tmp_path):
        bad = tmp_path / "dataset.yaml"
        bad.write_text(
            "\n".join(
                [
                    "dataset_name: bad-approved-dataset",
                    "dataset_version: 1",
                    "task: plate_detection",
                    "format: generic_capture",
                    "storage_root: data/staged/bad",
                    "review_status: approved",
                    "provenance:",
                    "  source_name: bad",
                    "  source_kind: field_capture",
                    "  license_tier: internal",
                    "  license_name: internal",
                    "  license_reference: internal://bad",
                    "assets:",
                    "  - asset_id: a1",
                    "    relative_path: batch/frame.jpg",
                    "    capture_session_id: session_01",
                    "    lighting_conditions: [unknown]",
                ]
            ),
            encoding="utf-8",
        )
        with pytest.raises(ConfigLoadError):
            load_training_dataset_manifest(bad)

    def test_dataset_split_ratios_cannot_exceed_one(self, tmp_path):
        bad = tmp_path / "split.yaml"
        bad.write_text(
            "\n".join(
                [
                    "split_name: bad",
                    "dataset_name: bad",
                    "train_ratio: 0.7",
                    "validation_ratio: 0.2",
                    "holdout_ratio: 0.2",
                    "assignments:",
                    "  - asset_id: a1",
                    "    capture_session_id: s1",
                    "    split: train",
                    "    relative_path: batch/frame.jpg",
                ]
            ),
            encoding="utf-8",
        )
        with pytest.raises(ConfigLoadError):
            load_dataset_split_manifest(bad)


class TestTrainingProfileSchema:
    def test_vehicle_detector_profile_parses(self):
        profile = load_training_profile(CONFIGS / "training" / "vehicle-detector-finetune.yaml")
        assert profile.task == DatasetTask.vehicle_detection
        assert profile.framework == TrainingFramework.ultralytics
        assert profile.class_names == ["vehicle"]

    def test_plate_ocr_profile_parses(self):
        profile = load_training_profile(CONFIGS / "training" / "plate-ocr-finetune.yaml")
        assert profile.task == DatasetTask.plate_ocr
        assert profile.framework == TrainingFramework.paddleocr

    def test_make_model_warmstart_profile_parses(self):
        profile = load_training_profile(CONFIGS / "training" / "vehicle-make-model-warmstart.yaml")
        assert profile.task == DatasetTask.vehicle_make_model_classification
        assert profile.framework == TrainingFramework.torchvision
        assert profile.dataset_adapter == DatasetAdapter.stanford_cars

    def test_detection_profile_requires_class_names(self, tmp_path):
        bad = tmp_path / "profile.yaml"
        bad.write_text(
            "\n".join(
                [
                    "profile_name: bad-detector",
                    "task: plate_detection",
                    "framework: ultralytics",
                    "dataset_adapter: manifest_split",
                ]
            ),
            encoding="utf-8",
        )
        with pytest.raises(ConfigLoadError):
            load_training_profile(bad)
