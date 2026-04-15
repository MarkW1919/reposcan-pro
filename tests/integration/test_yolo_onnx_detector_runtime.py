from __future__ import annotations

import numpy as np
import onnx
import pytest
from PIL import Image

from reposcan_contracts.config.model import DetectorModelConfig
from reposcan_contracts.frame import CameraProfile, FrameEnvelope, SourceType
from reposcan_inference.onnx_adapters import OnnxVehicleDetectorAdapter, validate_onnx_artifact


def _write_yolo_constant_model(path) -> None:
    image_input = onnx.helper.make_tensor_value_info("images", onnx.TensorProto.FLOAT, [1, 3, 320, 320])
    output = onnx.helper.make_tensor_value_info("output0", onnx.TensorProto.FLOAT, [1, 5, 3])
    predictions = np.asarray(
        [
            [
                [160.0, 162.0, 10.0],
                [80.0, 82.0, 10.0],
                [80.0, 82.0, 5.0],
                [40.0, 42.0, 5.0],
                [0.90, 0.80, 0.10],
            ]
        ],
        dtype=np.float32,
    )
    tensor = onnx.helper.make_tensor("predictions", onnx.TensorProto.FLOAT, predictions.shape, predictions.flatten())
    constant_node = onnx.helper.make_node("Constant", inputs=[], outputs=["output0"], value=tensor, name="yolo_output")
    graph = onnx.helper.make_graph([constant_node], name="yolo_detector", inputs=[image_input], outputs=[output])
    model = onnx.helper.make_model(graph, producer_name="reposcan-tests", opset_imports=[onnx.helper.make_operatorsetid("", 13)])
    model.ir_version = 10
    onnx.checker.check_model(model)
    onnx.save_model(model, path)


def _detector_config(path) -> DetectorModelConfig:
    return DetectorModelConfig.model_validate(
        {
            "name": "yolo-vehicle-smoke",
            "backend": "onnx",
            "artifact_path": str(path),
            "input_width": 320,
            "input_height": 320,
            "normalization_mean": [0.0, 0.0, 0.0],
            "normalization_std": [1.0, 1.0, 1.0],
            "class_labels": ["vehicle"],
            "confidence_threshold": 0.25,
            "nms_iou_threshold": 0.5,
        }
    )


def test_yolo_detector_output_validates_and_decodes(tmp_path):
    model_path = tmp_path / "yolo-detector.onnx"
    image_path = tmp_path / "frame.jpg"
    _write_yolo_constant_model(model_path)
    Image.new("RGB", (640, 320), color=(240, 240, 240)).save(image_path)

    model_config = _detector_config(model_path)
    assert validate_onnx_artifact("vehicle_detector", model_config, artifact_path=model_path) == []

    frame = FrameEnvelope.model_validate(
        {
            "frame_id": "frm_yolo_001",
            "camera_id": "cam_yolo_01",
            "timestamp_utc": "2026-04-15T08:00:00Z",
            "frame_path": str(image_path),
            "frame_number": 0,
            "source_type": "file",
            "camera_profile": CameraProfile(
                camera_id="cam_yolo_01",
                source_type=SourceType.file,
                resolution_w=640,
                resolution_h=320,
            ).model_dump(mode="json"),
        }
    )

    detections = OnnxVehicleDetectorAdapter(model_config, artifact_path=model_path).detect(frame)

    assert len(detections) == 1
    detection = detections[0]
    assert detection.class_label == "vehicle"
    assert detection.confidence == pytest.approx(0.9)
    assert detection.bbox.x == 240
    assert detection.bbox.y == 60
    assert detection.bbox.w == 160
    assert detection.bbox.h == 40
