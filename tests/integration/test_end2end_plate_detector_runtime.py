"""End2end (NMS-in-graph) plate-detector ONNX decode.

Covers exports like ``yolo-v9-t-384-license-plate-end2end`` that run NMS inside
the graph and emit a single ``[num_detections, 7]`` table
(``[batch, x1, y1, x2, y2, class, score]``) in input-pixel coordinates, rather
than the raw ``[1, 4+nc, anchors]`` grid the standard YOLO decoder consumes.
"""

from __future__ import annotations

import numpy as np
import onnx
import pytest
from PIL import Image

from reposcan_contracts.config.model import DetectorModelConfig
from reposcan_contracts.config.pipeline import PlateDetectionStrategy
from reposcan_contracts.frame import CameraProfile, FrameEnvelope, SourceType
from reposcan_inference.onnx_adapters import (
    OnnxPlateDetectorAdapter,
    _decode_end2end_detector_outputs,
    _looks_like_end2end_detector_output,
)


def _plate_config(path) -> DetectorModelConfig:
    return DetectorModelConfig.model_validate(
        {
            "name": "yolo-v9-plate-end2end",
            "backend": "onnx",
            "artifact_path": str(path),
            "input_width": 384,
            "input_height": 384,
            "normalization_mean": [0.0, 0.0, 0.0],
            "normalization_std": [1.0, 1.0, 1.0],
            "class_labels": ["plate"],
            "confidence_threshold": 0.5,
            "nms_iou_threshold": 0.45,
        }
    )


def test_decode_end2end_seven_column_pixel_table_maps_to_relative_xywh():
    # [batch, x1, y1, x2, y2, class, score] in 384-px space.
    table = {
        "output0": np.asarray(
            [
                [0.0, 96.0, 192.0, 288.0, 288.0, 0.0, 0.91],  # centered box, high conf
                [0.0, 0.0, 0.0, 38.4, 38.4, 0.0, 0.20],       # low conf -> filtered
            ],
            dtype=np.float32,
        )
    }
    assert _looks_like_end2end_detector_output(table) is True
    boxes, scores, classes = _decode_end2end_detector_outputs(table, _plate_config("x.onnx"))

    assert boxes.shape == (1, 4)
    assert scores[0] == pytest.approx(0.91)
    assert classes[0] == 0
    # 96/384=0.25, 192/384=0.5, width=(288-96)/384=0.5, height=(288-192)/384=0.25
    assert boxes[0] == pytest.approx([0.25, 0.5, 0.5, 0.25])


def test_decode_end2end_six_column_layout():
    # [x1, y1, x2, y2, score, class]
    table = {"o": np.asarray([[0.0, 0.0, 192.0, 384.0, 0.77, 0.0]], dtype=np.float32)}
    boxes, scores, classes = _decode_end2end_detector_outputs(table, _plate_config("x.onnx"))
    assert scores[0] == pytest.approx(0.77)
    assert boxes[0] == pytest.approx([0.0, 0.0, 0.5, 1.0])


def _write_end2end_constant_model(path) -> None:
    image_input = onnx.helper.make_tensor_value_info("images", onnx.TensorProto.FLOAT, [1, 3, 384, 384])
    output = onnx.helper.make_tensor_value_info("output0", onnx.TensorProto.FLOAT, [1, 7])
    table = np.asarray([[0.0, 96.0, 192.0, 288.0, 288.0, 0.0, 0.91]], dtype=np.float32)
    tensor = onnx.helper.make_tensor("table", onnx.TensorProto.FLOAT, table.shape, table.flatten())
    node = onnx.helper.make_node("Constant", inputs=[], outputs=["output0"], value=tensor, name="end2end_output")
    graph = onnx.helper.make_graph([node], name="plate_end2end", inputs=[image_input], outputs=[output])
    model = onnx.helper.make_model(graph, producer_name="reposcan-tests", opset_imports=[onnx.helper.make_operatorsetid("", 13)])
    model.ir_version = 10
    onnx.checker.check_model(model)
    onnx.save_model(model, path)


def test_end2end_plate_adapter_full_frame_decode(tmp_path):
    model_path = tmp_path / "plate-end2end.onnx"
    image_path = tmp_path / "frame.jpg"
    _write_end2end_constant_model(model_path)
    Image.new("RGB", (768, 384), color=(200, 200, 200)).save(image_path)

    model_config = _plate_config(model_path)
    frame = FrameEnvelope.model_validate(
        {
            "frame_id": "frm_plate_001",
            "camera_id": "cam_plate_01",
            "timestamp_utc": "2026-06-11T08:00:00Z",
            "frame_path": str(image_path),
            "frame_number": 0,
            "source_type": "file",
            "camera_profile": CameraProfile(
                camera_id="cam_plate_01",
                source_type=SourceType.file,
                resolution_w=768,
                resolution_h=384,
            ).model_dump(mode="json"),
        }
    )

    detections = OnnxPlateDetectorAdapter(model_config, artifact_path=model_path).detect(
        frame, vehicle_detections=[], strategy=PlateDetectionStrategy.full_frame
    )

    assert len(detections) == 1
    detection = detections[0]
    assert detection.confidence == pytest.approx(0.91)
    # relative 0.25,0.5,0.5,0.25 on a 768x384 frame
    assert detection.bbox.x == 192
    assert detection.bbox.y == 192
    assert detection.bbox.w == 384
    assert detection.bbox.h == 96
