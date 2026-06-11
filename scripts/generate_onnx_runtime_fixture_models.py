from __future__ import annotations

from pathlib import Path


def _tensor(name, data_type, dims, vals):
    import onnx

    return onnx.helper.make_tensor(name=name, data_type=data_type, dims=dims, vals=vals)


def _constant_node(output_name: str, tensor):
    import onnx

    return onnx.helper.make_node(
        "Constant",
        inputs=[],
        outputs=[output_name],
        value=tensor,
        name=f"{output_name}_const",
    )


def _save_model(path: Path, *, input_shape: list[int], outputs: list[tuple[str, int, list[int], list]]) -> None:
    import onnx

    image_input = onnx.helper.make_tensor_value_info("image", onnx.TensorProto.FLOAT, input_shape)
    output_infos = [
        onnx.helper.make_tensor_value_info(output_name, data_type, dims)
        for output_name, data_type, dims, _ in outputs
    ]
    nodes = [
        _constant_node(output_name, _tensor(f"{output_name}_value", data_type, dims, values))
        for output_name, data_type, dims, values in outputs
    ]
    graph = onnx.helper.make_graph(
        nodes=nodes,
        name=path.stem,
        inputs=[image_input],
        outputs=output_infos,
    )
    model = onnx.helper.make_model(
        graph,
        producer_name="reposcan-pro",
        opset_imports=[onnx.helper.make_operatorsetid("", 13)],
    )
    onnx.checker.check_model(model)
    path.parent.mkdir(parents=True, exist_ok=True)
    onnx.save_model(model, path)


def main() -> int:
    import onnx

    repo_root = Path(__file__).resolve().parents[1]
    output_root = repo_root / "ml" / "inference" / "fixtures" / "onnx-runtime"

    _save_model(
        output_root / "vehicle-detector.onnx",
        input_shape=[1, 3, 640, 640],
        outputs=[
            ("boxes_xywh", onnx.TensorProto.FLOAT, [1, 4], [0.22, 0.28, 0.48, 0.34]),
            ("scores", onnx.TensorProto.FLOAT, [1], [0.94]),
            ("label_indices", onnx.TensorProto.INT64, [1], [0]),
        ],
    )
    _save_model(
        output_root / "plate-detector.onnx",
        input_shape=[1, 3, 160, 320],
        outputs=[
            ("boxes_xywh", onnx.TensorProto.FLOAT, [1, 4], [0.34, 0.60, 0.28, 0.14]),
            ("scores", onnx.TensorProto.FLOAT, [1], [0.90]),
            ("label_indices", onnx.TensorProto.INT64, [1], [0]),
        ],
    )
    _save_model(
        output_root / "ocr.onnx",
        input_shape=[1, 3, 48, 144],
        outputs=[
            ("texts", onnx.TensorProto.STRING, [1], ["6BZN220"]),
            ("confidences", onnx.TensorProto.FLOAT, [1], [0.93]),
        ],
    )
    _save_model(
        output_root / "classifier.onnx",
        input_shape=[1, 3, 224, 224],
        outputs=[
            ("color_indices", onnx.TensorProto.INT64, [1], [0]),
            ("color_confidences", onnx.TensorProto.FLOAT, [1], [0.89]),
            ("make_indices", onnx.TensorProto.INT64, [1], [0]),
            ("make_confidences", onnx.TensorProto.FLOAT, [1], [0.82]),
            ("model_texts", onnx.TensorProto.STRING, [1], ["camry"]),
            ("model_confidences", onnx.TensorProto.FLOAT, [1], [0.78]),
            ("year_texts", onnx.TensorProto.STRING, [1], ["2018-2021"]),
            ("year_confidences", onnx.TensorProto.FLOAT, [1], [0.66]),
        ],
    )
    print(f"Generated ONNX runtime fixtures under {output_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
