"""TensorRT build planner: trtexec command construction + stage enumeration.

The actual engine build runs on the Jetson (trtexec), but the *plan* — which
ONNX artifacts convert, what the commands are, what's skipped — is pure and
locked here so it can't silently drift on a workstation.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import yaml

from reposcan_contracts.config.model import ModelStackConfig

REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = REPO_ROOT / "scripts" / "build_tensorrt_engines.py"
_spec = importlib.util.spec_from_file_location("build_tensorrt_engines", _SCRIPT)
btr = importlib.util.module_from_spec(_spec)
# Register before exec: @dataclass introspects sys.modules[cls.__module__].
sys.modules[_spec.name] = btr
_spec.loader.exec_module(btr)


def _spec_obj(name="vehicle", w=640, h=640) -> "btr.EngineBuildSpec":
    return btr.EngineBuildSpec(
        stage="vehicle_detector",
        name=name,
        onnx_path=Path("/models/v.onnx"),
        engine_path=Path("/out/v.engine"),
        input_width=w,
        input_height=h,
    )


def test_trtexec_command_fp16_with_fixed_shapes():
    cmd = btr.build_trtexec_command(_spec_obj(w=384, h=384), fp16=True, workspace_mib=4096)
    assert cmd[0] == "trtexec"
    assert "--onnx=/models/v.onnx" in cmd
    assert "--saveEngine=/out/v.engine" in cmd
    assert "--fp16" in cmd
    assert "--memPoolSize=workspace:4096" in cmd
    assert "--minShapes=images:1x3x384x384" in cmd
    assert "--optShapes=images:1x3x384x384" in cmd
    assert "--maxShapes=images:1x3x384x384" in cmd


def test_trtexec_command_fp32_and_no_shapes():
    cmd = btr.build_trtexec_command(_spec_obj(), fp16=False, set_shapes=False)
    assert "--fp16" not in cmd
    assert not any(c.startswith("--minShapes") for c in cmd)


def test_trtexec_command_custom_input_name():
    cmd = btr.build_trtexec_command(_spec_obj(w=260, h=260), input_name="pixel_values")
    assert "--optShapes=pixel_values:1x3x260x260" in cmd


def test_enumerate_skips_fast_alpr_ocr_and_includes_deferred_heads():
    stack = ModelStackConfig.model_validate(
        yaml.safe_load((REPO_ROOT / "configs/models/local-onnx-full-real.yaml").read_text(encoding="utf-8"))
    )
    specs, skipped = btr.enumerate_engine_specs(stack, Path("/out/artifacts"))
    stages = {s.stage for s in specs}

    # detectors + every deferred head build engines
    assert "vehicle_detector" in stages
    assert "plate_detector" in stages
    assert "deferred.make_model" in stages
    assert "deferred.rerank.gm-fullsize-suv" in stages
    assert "deferred.rerank.jeep" in stages
    assert "deferred.year" in stages
    assert "deferred.color" in stages
    # fast_alpr OCR is accelerated via the ORT TRT EP, not a standalone engine
    assert not any(s.stage == "ocr" for s in specs)
    assert any("ocr" in note and "fast_alpr" in note for note in skipped)
    # engine paths land under the artifacts dir with .engine suffix
    assert all(s.engine_path.suffix == ".engine" for s in specs)
    assert all(str(s.engine_path).startswith(str(Path("/out/artifacts"))) for s in specs)
