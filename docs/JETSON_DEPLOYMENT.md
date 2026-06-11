# JETSON_DEPLOYMENT.md — model → engine → run on the Orin Nano

This is the on-device runbook for getting the recognition pipeline running on a
**Jetson Orin Nano Super** with TensorRT. It picks up where the ONNX models leave
off: the repo's models are trained/exported to ONNX (see
[MODEL_INVENTORY.md](MODEL_INVENTORY.md) and
[VEHICLE_RECOGNITION_PIPELINE_STATUS.md](VEHICLE_RECOGNITION_PIPELINE_STATUS.md)),
and this document covers converting them to TensorRT engines **on the device** and
wiring them into the runtime.

> **Honesty up front.** "Runs on the Orin" ≠ "field-accurate." The current models
> are trained but not field-accepted: a smoke-grade vehicle detector, global
> (un-tuned) plate detector + OCR, synthetic-only color, ~68% year. Long-range /
> low-light / IR accuracy is gated on the camera + field data + the field-eval
> pass in [FIELD_EVAL_QUALIFICATION.md](FIELD_EVAL_QUALIFICATION.md), not on this
> deployment step. This runbook makes the pipeline *run on the hardware*; it does
> not make it *accurate*.

## 0. Target profile

[`configs/deployments/jetson-orin-nano-super.yaml`](../configs/deployments/jetson-orin-nano-super.yaml)
pins the contract the runtime validates against:

- `required_backend: tensorrt`, `target_runtime: tensorrt`
- `required_cuda_version: "12.2"`, `required_tensorrt_version: "10.0.1"`,
  `required_compute_capability: "8.7"`
- `latency_budget_ms_p95: 250`, `memory_budget_mb: 6144`, 1 active AI camera

TensorRT engines are **not portable** across GPU / TensorRT version — they must
be built on the device with the matching JetPack. Do not copy engines between
machines.

## 1. Device prep (JetPack)

1. Flash JetPack matching the profile (CUDA 12.2 / TensorRT 10.0.1). `trtexec`
   ships with TensorRT at `/usr/src/tensorrt/bin/trtexec` (add to `PATH` or pass
   `--trtexec /usr/src/tensorrt/bin/trtexec`).
2. Set the board to max performance for benchmarking/build: `sudo nvpmodel -m 0`
   then `sudo jetson_clocks`.
3. Python deps: install the repo's inference extras plus `onnxruntime-gpu`
   (TensorRT execution provider) and `tensorrt` / `pycuda` for the engine
   adapters. Verify with `python -c "import tensorrt, pycuda.autoinit"`.

## 2. Stage the ONNX models

The weights live under `runtime/` (gitignored). Restore them from backup and
verify integrity against the committed catalog:

```bash
python scripts/inventory_trained_models.py --verify
```

This must report all artifacts present and unchanged before you build engines —
it is the guard against a partial/corrupt model restore.

## 3. Build TensorRT engines (on the device)

Preview the plan anywhere (no device needed):

```bash
python scripts/build_tensorrt_engines.py \
    --model-config configs/models/local-onnx-full-real.yaml
```

On the Orin, build the engines:

```bash
python scripts/build_tensorrt_engines.py \
    --model-config configs/models/local-onnx-full-real.yaml \
    --output-dir runtime/engines/orin --run
```

This converts the two detectors and the four deferred recognition heads
(make/model, GM-SUV re-rank, Jeep re-rank, year, color) to fp16 engines under
`runtime/engines/orin/artifacts/`. fp16 is the right Orin default; add `--no-fp16`
only to debug accuracy deltas. Tune `--workspace-mib` if a build reports an
insufficient workspace.

**The OCR stage is intentionally skipped.** The `fast_alpr` reader is accelerated
through onnxruntime's TensorRT execution provider at runtime, not a standalone
engine. Enable it by setting the provider chain (see §5).

## 4. Wire the engines into a TensorRT stack config

Create a promoted stack mirroring
[`configs/models/promoted-tensorrt-template.yaml`](../configs/models/promoted-tensorrt-template.yaml)
(`path_base: config_dir`, so engine paths are relative to the config). Point each
stage's `artifact_path` at the matching `artifacts/<name>.engine` the build step
produced, set `backend: tensorrt`, and keep every other field (input size,
labels, thresholds, the `deferred_recognition` block, normalization) identical to
`local-onnx-full-real.yaml`. Keep the OCR stage as `backend: fast_alpr` pointing
at the staged `cct_xs_v2_global.onnx`.

Validate the assembled stack before running:

```bash
python -c "from reposcan_inference.validation import validate_model_stack; \
import yaml; from reposcan_contracts.config.model import ModelStackConfig; \
r = validate_model_stack(ModelStackConfig.model_validate(yaml.safe_load(open('<your-tensorrt-stack>.yaml')))); \
print(all(s.ready for s in r.stages), [(s.stage, s.ready) for s in r.stages])"
```

`validate_deployment_runtime_bundle` (in `reposcan_inference.deployment_validation`)
checks the stack against the Jetson profile's `required_backend` — run it as the
final gate so a CPU/ONNX fallback can't silently ship.

## 5. Execution providers

For the `fast_alpr` OCR (and any ONNX fallback), set the runtime provider chain
so it uses TensorRT → CUDA → CPU:

```bash
export REPOSCAN_ONNX_PROVIDERS="TensorrtExecutionProvider,CUDAExecutionProvider,CPUExecutionProvider"
```

The deployment profile's `target_runtime: tensorrt` already drives this chain via
`adapter_factory._providers_for_deployment`; the env var is the manual override.

## 6. Validate latency on the device

Use the edge bench to confirm the 250 ms p95 budget — full usage in
[EDGE_BENCH.md](EDGE_BENCH.md):

```bash
python scripts/run_edge_bench.py --help
```

Engines built, stack validated, latency within budget → the pipeline is running
on the Orin. Field accuracy is the next, separate gate (§ honesty note).

## Related

- [DEPLOYMENT.md](DEPLOYMENT.md) — full appliance bring-up (services, storage, API/UI)
- [MODEL_INVENTORY.md](MODEL_INVENTORY.md) — what models exist + integrity verify
- [VEHICLE_RECOGNITION_PIPELINE_STATUS.md](VEHICLE_RECOGNITION_PIPELINE_STATUS.md) — accuracy + open items
- [FIELD_EVAL_QUALIFICATION.md](FIELD_EVAL_QUALIFICATION.md) — the field-acceptance gate
