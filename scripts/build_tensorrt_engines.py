#!/usr/bin/env python
"""Build TensorRT engines for every ONNX stage in a model stack (for the Jetson).

The repo's real models are ONNX (detectors, classifiers) plus a fast-plate-ocr
OCR model. To hit the Orin Nano latency/throughput budget they run on TensorRT.
TensorRT engines are NOT portable across GPUs / TensorRT versions, so they must
be built ON the target device. This script enumerates the ONNX artifacts a stack
references and emits the exact ``trtexec`` command to convert each one, with
Orin-appropriate defaults (fp16, a workspace pool, fixed input shapes).

It is **dry-run by default**: it prints the plan and writes nothing, so it is
safe and reviewable on a workstation (and its command construction is unit
tested). Pass ``--run`` on the Jetson to actually invoke ``trtexec``.

The OCR stage uses the ``fast_alpr`` backend, which is accelerated through
onnxruntime's TensorRT execution provider at runtime (set ``REPOSCAN_ONNX_PROVIDERS``
or the deployment ``target_runtime``) rather than a standalone ``.engine`` — so
it is reported but not converted here. After building, wire the engines into a
``backend: tensorrt`` stack (see configs/models/promoted-tensorrt-template.yaml
and docs/JETSON_DEPLOYMENT.md).

Usage:
    # On a workstation — review the plan (no device needed):
    python scripts/build_tensorrt_engines.py --model-config configs/models/local-onnx-full-real.yaml

    # On the Jetson Orin — actually build the engines:
    python scripts/build_tensorrt_engines.py \
        --model-config configs/models/local-onnx-full-real.yaml \
        --output-dir runtime/engines/orin --run
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


def _configure_pythonpath(repo_root: Path) -> None:
    for src in (
        repo_root / "packages" / "contracts" / "src",
        repo_root / "services" / "inference" / "src",
    ):
        if str(src) not in sys.path:
            sys.path.insert(0, str(src))


@dataclass(frozen=True)
class EngineBuildSpec:
    """One ONNX -> TensorRT engine conversion."""

    stage: str           # e.g. "vehicle_detector", "deferred.make_model"
    name: str            # model name from config
    onnx_path: Path
    engine_path: Path
    input_width: int
    input_height: int


def build_trtexec_command(
    spec: EngineBuildSpec,
    *,
    fp16: bool = True,
    workspace_mib: int = 2048,
    input_name: str = "images",
    set_shapes: bool = True,
    trtexec: str = "trtexec",
) -> list[str]:
    """Construct the trtexec CLI for one engine build.

    ``set_shapes`` emits min/opt/max shape flags pinned to a single fixed input
    (batch 1, the config's HxW) — the right default for an edge appliance with a
    dynamic-axis ONNX export. Static-shape ONNX models don't need them.
    """
    # Emit POSIX paths: engines are built on the Jetson (Linux) via trtexec, so
    # the command must read the same whether the plan is printed there or
    # reviewed on a Windows workstation.
    cmd = [
        trtexec,
        f"--onnx={spec.onnx_path.as_posix()}",
        f"--saveEngine={spec.engine_path.as_posix()}",
        f"--memPoolSize=workspace:{workspace_mib}",
    ]
    if fp16:
        cmd.append("--fp16")
    if set_shapes:
        shape = f"{input_name}:1x3x{spec.input_height}x{spec.input_width}"
        cmd.extend([f"--minShapes={shape}", f"--optShapes={shape}", f"--maxShapes={shape}"])
    return cmd


def _classifier_specs(prefix: str, classifier, resolve, out_artifacts: Path) -> list[EngineBuildSpec]:
    onnx = Path(resolve(classifier.artifact_path))
    return [
        EngineBuildSpec(
            stage=prefix,
            name=classifier.name,
            onnx_path=onnx,
            engine_path=out_artifacts / f"{classifier.name}.engine",
            input_width=classifier.input_width,
            input_height=classifier.input_height,
        )
    ]


def enumerate_engine_specs(model_stack, out_artifacts: Path) -> tuple[list[EngineBuildSpec], list[str]]:
    """Return (engines to build, stages skipped) for a stack config.

    Skips the fast_alpr OCR stage (accelerated via the ORT TensorRT EP, not a
    standalone engine). Includes detectors, an optional real-time classifier,
    and all deferred recognition heads.
    """
    from reposcan_contracts.config.model import InferenceBackend

    resolve = model_stack.resolve_artifact_path
    specs: list[EngineBuildSpec] = []
    skipped: list[str] = []

    def add_detector(stage: str, cfg) -> None:
        specs.append(
            EngineBuildSpec(
                stage=stage,
                name=cfg.name,
                onnx_path=Path(resolve(cfg.artifact_path)),
                engine_path=out_artifacts / f"{cfg.name}.engine",
                input_width=cfg.input_width,
                input_height=cfg.input_height,
            )
        )

    add_detector("vehicle_detector", model_stack.vehicle_detector)
    add_detector("plate_detector", model_stack.plate_detector)

    if model_stack.ocr.backend == InferenceBackend.fast_alpr:
        skipped.append("ocr (fast_alpr -> ORT TensorRT execution provider, no standalone engine)")
    elif model_stack.ocr.backend == InferenceBackend.onnx:
        specs.append(
            EngineBuildSpec(
                stage="ocr",
                name=model_stack.ocr.name,
                onnx_path=Path(resolve(model_stack.ocr.artifact_path)),
                engine_path=out_artifacts / f"{model_stack.ocr.name}.engine",
                input_width=model_stack.ocr.input_width,
                input_height=model_stack.ocr.input_height,
            )
        )
    else:
        skipped.append(f"ocr (backend={model_stack.ocr.backend.value}, not ONNX)")

    if model_stack.classifier is not None and model_stack.classifier.backend == InferenceBackend.onnx:
        specs.extend(_classifier_specs("classifier", model_stack.classifier, resolve, out_artifacts))

    deferred = getattr(model_stack, "deferred_recognition", None)
    if deferred is not None:
        specs.extend(_classifier_specs("deferred.make_model", deferred.make_model, resolve, out_artifacts))
        for head in deferred.rerank_heads:
            specs.extend(_classifier_specs(f"deferred.rerank.{head.name}", head.classifier, resolve, out_artifacts))
        if deferred.year is not None:
            specs.extend(_classifier_specs("deferred.year", deferred.year, resolve, out_artifacts))
        if deferred.color is not None:
            specs.extend(_classifier_specs("deferred.color", deferred.color, resolve, out_artifacts))

    return specs, skipped


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model-config", required=True, help="ONNX model stack config to convert")
    parser.add_argument("--output-dir", default="runtime/engines", help="where engines are written (artifacts/ subdir)")
    parser.add_argument("--run", action="store_true", help="actually invoke trtexec (default: dry-run / print plan)")
    parser.add_argument("--no-fp16", action="store_true", help="build fp32 engines (default fp16)")
    parser.add_argument("--workspace-mib", type=int, default=2048)
    parser.add_argument(
        "--input-name",
        default="images",
        help="ONNX input tensor name for shape flags (all current models use 'images')",
    )
    parser.add_argument("--trtexec", default="trtexec", help="path to the trtexec binary")
    parser.add_argument("--repo-root", default=None)
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve() if args.repo_root else Path(__file__).resolve().parents[1]
    _configure_pythonpath(repo_root)
    import yaml
    from reposcan_contracts.config.model import ModelStackConfig

    config_path = (repo_root / args.model_config) if not Path(args.model_config).is_absolute() else Path(args.model_config)
    model_stack = ModelStackConfig.model_validate(yaml.safe_load(config_path.read_text(encoding="utf-8")))

    out_artifacts = (repo_root / args.output_dir / "artifacts") if not Path(args.output_dir).is_absolute() else Path(args.output_dir) / "artifacts"
    specs, skipped = enumerate_engine_specs(model_stack, out_artifacts)

    mode = "RUN" if args.run else "DRY-RUN"
    print(f"[{mode}] stack '{model_stack.stack_name}' -> {len(specs)} engine(s), {len(skipped)} skipped")
    print(f"        output: {out_artifacts}")
    for note in skipped:
        print(f"  SKIP  {note}")

    missing = [s for s in specs if not s.onnx_path.exists()]
    if missing:
        print("\nERROR: missing source ONNX artifacts:")
        for s in missing:
            print(f"  {s.stage}: {s.onnx_path}")
        return 2

    if args.run:
        out_artifacts.mkdir(parents=True, exist_ok=True)

    failures = 0
    for spec in specs:
        cmd = build_trtexec_command(
            spec,
            fp16=not args.no_fp16,
            workspace_mib=args.workspace_mib,
            input_name=args.input_name,
            trtexec=args.trtexec,
        )
        print(f"\n# {spec.stage} ({spec.name})  {spec.input_width}x{spec.input_height}")
        print("  " + " ".join(cmd))
        if args.run:
            result = subprocess.run(cmd, check=False)
            if result.returncode != 0:
                print(f"  FAILED (exit {result.returncode})")
                failures += 1

    if args.run and failures:
        print(f"\n{failures} engine build(s) failed.")
        return 1
    if not args.run:
        print("\nDry-run only. Re-run on the Jetson with --run to build engines.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
