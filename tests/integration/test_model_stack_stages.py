"""The shared stage enumerator must include deferred_recognition stages.

This is the single source of truth used by runtime validation, promotion
packaging, and deployment compatibility checks. If it ever omits the deferred
stages, a promoted/validated bundle could silently ship without the real
recognition models — the exact gap the audit flagged.
"""

from __future__ import annotations

from reposcan_contracts.config.model import ModelStackConfig
from reposcan_inference.validation import iter_model_stack_stages


def _detector(name: str) -> dict:
    return {"name": name, "artifact_path": f"{name}.onnx", "input_width": 640, "input_height": 640}


def _classifier(name: str) -> dict:
    return {
        "name": name,
        "artifact_path": f"{name}.onnx",
        "label_metadata_path": f"{name}.labels.json",
        "input_width": 260,
        "input_height": 260,
    }


def _base_stack() -> dict:
    return {
        "stack_name": "stages-test",
        "vehicle_detector": _detector("vd"),
        "plate_detector": _detector("pd"),
        "ocr": {"name": "ocr", "artifact_path": "ocr.onnx", "input_width": 94, "input_height": 24, "charset": "ABC"},
    }


def test_enumerates_top_level_stages_only_when_no_deferred():
    stack = ModelStackConfig.model_validate(_base_stack())
    ids = [stage_id for stage_id, _ in iter_model_stack_stages(stack)]
    assert ids == ["vehicle_detector", "plate_detector", "ocr"]


def test_includes_optional_realtime_classifier():
    data = _base_stack()
    data["classifier"] = _classifier("rt")
    stack = ModelStackConfig.model_validate(data)
    ids = [stage_id for stage_id, _ in iter_model_stack_stages(stack)]
    assert "classifier" in ids


def test_enumerates_every_deferred_recognition_stage():
    data = _base_stack()
    data["deferred_recognition"] = {
        "make_model": _classifier("mm"),
        "rerank_heads": [
            {"name": "gm-fullsize-suv", "trigger_classes": ["chevrolet_tahoe"], "classifier": _classifier("gm")},
            {"name": "jeep", "trigger_classes": ["jeep_wrangler"], "classifier": _classifier("jeep")},
        ],
        "year": _classifier("year"),
        "color": _classifier("color"),
    }
    stack = ModelStackConfig.model_validate(data)
    ids = [stage_id for stage_id, _ in iter_model_stack_stages(stack)]

    assert ids == [
        "vehicle_detector",
        "plate_detector",
        "ocr",
        "deferred.make_model",
        "deferred.rerank.gm-fullsize-suv",
        "deferred.rerank.jeep",
        "deferred.year",
        "deferred.color",
    ]


def test_packaging_rejects_deferred_stack_loudly():
    # A deferred stack must fail packaging with a clear message rather than
    # silently omit/overwrite recognition artifacts.
    import pytest

    from reposcan_inference.promotion import _require_packagable_onnx_stack

    data = _base_stack()
    data["deferred_recognition"] = {"make_model": _classifier("mm")}
    stack = ModelStackConfig.model_validate(data)
    with pytest.raises(ValueError, match="deferred_recognition"):
        # Guard raises before any artifact I/O for deferred stacks. (We bypass
        # the runtime-readiness check by calling the guard's deferred branch via
        # a stack whose detectors are fine but deferred is set; validate runs
        # first, so we assert the guard exists by catching its message.)
        _require_packagable_onnx_stack(stack)
