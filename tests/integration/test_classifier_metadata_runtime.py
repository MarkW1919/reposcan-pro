from __future__ import annotations

from pathlib import Path

import onnx
import yaml
from PIL import Image

from reposcan_contracts.classifier_export import build_classifier_export_metadata
from reposcan_contracts.config.loader import load_model_config
from reposcan_contracts.frame import CameraProfile, FrameEnvelope, SourceType
from reposcan_inference import InferenceService, package_promoted_onnx_bundle, validate_model_stack


def _write_demo_image(path: Path) -> None:
    image = Image.new("RGB", (128, 72), color=(200, 200, 200))
    image.save(path, format="JPEG")


def _write_constant_logits_classifier(path: Path, *, logits: list[float]) -> None:
    image_input = onnx.helper.make_tensor_value_info("images", onnx.TensorProto.FLOAT, [1, 3, 224, 224])
    logits_output = onnx.helper.make_tensor_value_info("logits", onnx.TensorProto.FLOAT, [1, len(logits)])
    logits_tensor = onnx.helper.make_tensor("logits_value", onnx.TensorProto.FLOAT, [1, len(logits)], logits)
    constant_node = onnx.helper.make_node("Constant", inputs=[], outputs=["logits"], value=logits_tensor, name="logits")
    graph = onnx.helper.make_graph([constant_node], name="classifier_logits", inputs=[image_input], outputs=[logits_output])
    model = onnx.helper.make_model(graph, producer_name="reposcan-tests", opset_imports=[onnx.helper.make_operatorsetid("", 13)])
    onnx.checker.check_model(model)
    path.parent.mkdir(parents=True, exist_ok=True)
    onnx.save_model(model, path)


def _write_metadata_runtime_config(tmp_path: Path, *, classifier_path: Path, metadata_path: Path) -> Path:
    config = yaml.safe_load(Path("configs/models/local-onnx-runtime.yaml").read_text(encoding="utf-8"))
    config["stack_name"] = "metadata-classifier-runtime"
    config["classifier"]["artifact_path"] = str(classifier_path)
    config["classifier"]["label_metadata_path"] = str(metadata_path)
    config_path = tmp_path / "model-stack.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return config_path


def test_local_onnx_runtime_accepts_metadata_backed_make_model_classifier(tmp_path):
    classifier_path = tmp_path / "classifier.onnx"
    metadata_path = tmp_path / "labels.json"
    _write_constant_logits_classifier(classifier_path, logits=[0.1, 3.4, 0.3])
    metadata = build_classifier_export_metadata(
        task="vehicle_make_model_classification",
        classes=[
            "Acura RL Sedan 2012",
            "Toyota Camry Sedan 2019",
            "Ford F-150 SuperCrew 2020",
        ],
        image_size=224,
        base_model="efficientnet_b0",
    )
    metadata_path.write_text(metadata.model_dump_json(indent=2, by_alias=True), encoding="utf-8")

    config_path = _write_metadata_runtime_config(tmp_path, classifier_path=classifier_path, metadata_path=metadata_path)
    model_stack = load_model_config(config_path)

    report = validate_model_stack(model_stack)

    assert report.ready is True
    assert report.error_count == 0

    frame_path = tmp_path / "frame.jpg"
    _write_demo_image(frame_path)
    frame = FrameEnvelope.model_validate(
        {
            "frame_id": "frm_classifier_001",
            "camera_id": "cam_classifier_01",
            "timestamp_utc": "2026-03-30T12:00:00Z",
            "frame_path": str(frame_path),
            "frame_number": 0,
            "source_type": "file",
            "camera_profile": CameraProfile(
                camera_id="cam_classifier_01",
                source_type=SourceType.file,
                resolution_w=128,
                resolution_h=72,
            ).model_dump(mode="json"),
        }
    )

    service = InferenceService.from_config_paths(model_config_path=config_path)
    candidate = service.run(frame)

    assert candidate.attribute_predictions[0].make == "toyota"
    assert candidate.attribute_predictions[0].model_label == "camry sedan"
    assert candidate.attribute_predictions[0].year == "2019"


def test_package_promoted_bundle_copies_classifier_label_metadata(tmp_path):
    classifier_path = tmp_path / "source" / "classifier.onnx"
    metadata_path = tmp_path / "source" / "labels.json"
    _write_constant_logits_classifier(classifier_path, logits=[0.2, 2.8, 0.1])
    metadata = build_classifier_export_metadata(
        task="vehicle_make_model_classification",
        classes=[
            "Acura RL Sedan 2012",
            "Toyota Camry Sedan 2019",
            "Ford F-150 SuperCrew 2020",
        ],
        image_size=224,
        base_model="efficientnet_b0",
    )
    metadata_path.write_text(metadata.model_dump_json(indent=2, by_alias=True), encoding="utf-8")

    source_config = _write_metadata_runtime_config(tmp_path, classifier_path=classifier_path, metadata_path=metadata_path)
    model_stack = load_model_config(source_config)

    report = package_promoted_onnx_bundle(
        model_stack,
        output_dir=tmp_path / "bundle",
        bundle_name="metadata-classifier-bundle",
        exported_at_utc="2026-03-30T12:10:00Z",
        source_run_id="metadata_classifier_run",
        export_tool="torch.onnx.export",
        export_tool_version="2.7.0",
        opset_version=17,
        precision="fp32",
        target_runtime="onnxruntime",
    )

    assert report.ready is True
    packaged_stack = load_model_config(report.config_path)
    assert packaged_stack.classifier is not None
    assert packaged_stack.classifier.label_metadata_path == "artifacts/labels.json"
    assert (Path(report.output_dir) / "artifacts" / "labels.json").exists()
