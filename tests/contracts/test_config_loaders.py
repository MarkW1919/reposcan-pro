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
    load_camera_config,
    load_deployment_config,
    load_model_config,
    load_pipeline_config,
)
from reposcan_contracts.config.camera import CameraConfig, SourceType, ColorMode
from reposcan_contracts.config.model import ModelStackConfig, InferenceBackend
from reposcan_contracts.config.pipeline import PipelineConfig, PlateDetectionStrategy
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
