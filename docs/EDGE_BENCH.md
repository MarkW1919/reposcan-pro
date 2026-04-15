# EDGE_BENCH.md

The edge bench harness produces the latency, memory, and thermal evidence artifacts that close §12.183 (edge inference sign-off) in [PROJECT_STATUS_CHECKLIST.md](PROJECT_STATUS_CHECKLIST.md) and feed row P3-1 of [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md).

The harness drives the existing `InferenceService` pipeline — the same code that runs in production — and records per-stage latency distributions, cold-start timing, peak RSS, and a pluggable thermal/power telemetry stream. The same CLI is used on a developer workstation to keep the pipeline exercised and on the Jetson Orin rig to produce the hardware sign-off numbers.

## When to use it

Run the edge bench every time any of these change:

- a new promoted runtime bundle is accepted
- the inference pipeline config changes (batch size, queue depth, worker threads)
- the deployment profile for a target device changes
- a production-readiness review is about to be signed

Until the Orin rig ships, run the harness on a developer workstation so regressions in stage-level latency and memory are caught before they reach hardware.

## Prerequisites

- a promoted (or dev) model stack config under `configs/models/`
- a pipeline config (defaults to `configs/pipelines/default-edge.yaml`)
- a benchmark manifest listing the frames to drive through the pipeline (any promoted-bundle benchmark manifest works — the harness does not score OCR, it only measures timing)
- optionally a deployment profile so the harness records target-hardware context and Jetson-specific recommendations

## Invocation

On Windows:

```powershell
.\.venv\Scripts\python.exe .\scripts\run_edge_bench.py `
  --model-config .\configs\models\example-model-stack.yaml `
  --benchmark-manifest .\configs\benchmarks\example-promoted-onnx-benchmark.yaml `
  --deployment-config .\configs\deployments\jetson-orin-edge.yaml
```

Key flags:

- `--model-config` (required): model stack config (promoted bundle config for sign-off runs)
- `--benchmark-manifest` (required): benchmark manifest whose frames drive the bench
- `--pipeline-config` (default `configs/pipelines/default-edge.yaml`)
- `--deployment-config` (optional, enables target-hardware context and recommendations)
- `--output-root` (default `artifacts/bench/edge`)
- `--run-id` (default: auto-generated `edge_<utc-timestamp>`)
- `--json`: print the full report as JSON on stdout

## Output layout

Every run lands in `artifacts/bench/edge/<run_id>/`:

```text
artifacts/bench/edge/<run_id>/
|-- run_manifest.json        # run id, git HEAD, configs, frames processed, peak RSS
|-- edge_bench_report.json   # full EdgeBenchReport sidecar
`-- edge_bench_report.md     # operator-readable summary
```

## What the report contains

- **Cold-start latency**: the first frame is timed in isolation so it can be compared against the steady-state distribution
- **End-to-end latency**: average, p50, p95, p99, and max across all frames (including the cold-start frame)
- **Per-stage latency**: the same distribution for `vehicle_detect`, `plate_detect`, `ocr`, and `classify`. A stage with `count=0` means that stage was never called (for example `classify` when the model stack has no classifier)
- **Peak RSS**: best-effort peak resident-set size. On Linux/macOS the harness uses `resource.ru_maxrss` from the standard library; on Windows it falls back to `psutil.Process.memory_info.rss`; if neither is available the field is `null` and the report records that state explicitly
- **Thermal samples**: on a developer workstation the default sampler records a single informational row so the absence of hardware telemetry is explicit. On the Orin rig an operator wires in a tegrastats-based sampler (see below)

## CPU-vs-Orin delta

Runs on a developer CPU are valid for regression detection but are **not** acceptable evidence for criterion P3-1 in the production-readiness register. The Orin rig produces materially different numbers for three reasons:

1. TensorRT detector exports are only exercised on Jetson; CPU runs exercise the ONNX Runtime CPU provider
2. The Orin memory hierarchy (unified CPU/GPU memory) changes peak RSS envelopes
3. Thermal throttling on the Orin changes the tail of the latency distribution under sustained load

A CPU run proves the pipeline is alive and the harness is wired. Only an Orin run with the promoted TensorRT bundle closes P3-1.

## Wiring a thermal sampler on the Orin rig

The harness accepts any object that implements `reposcan_inference.ThermalSampler`:

```python
class ThermalSampler(Protocol):
    def sample(self) -> list[ThermalSample]: ...
```

On the Orin rig, the field operator implements a sampler that shells out to `tegrastats` (or reads `/sys/class/thermal/thermal_zone*/temp` plus the `ina3221` power sysfs paths) and returns one or more `ThermalSample` records per call. The harness calls `sample()` twice per run (before the first frame and after the last frame). Drop-in hook:

```python
from reposcan_inference import run_edge_bench, ThermalSample

class TegrastatsSampler:
    def sample(self) -> list[ThermalSample]:
        # parse a single tegrastats line and return samples
        ...

report = run_edge_bench(service, frames, deployment=deployment, thermal_sampler=TegrastatsSampler())
```

The library ships with `NoopThermalSampler` so developer workstations produce an explicit "no telemetry" row instead of silently empty tables.

## Contract with the rest of the repo

- the harness does not reimplement inference; it drives the existing `InferenceService` pipeline
- stage-level timings are recorded around every adapter call, so any regression in a single stage (e.g. OCR) shows up in the per-stage distribution
- the harness does not mutate the input manifest; it only loads frame records and feeds them through the pipeline
- the harness does not edit `PRODUCTION_READINESS.md`; the reviewer reads the generated reports and updates the evidence register
- new stages must be added to `STAGES_IN_ORDER` in `services/inference/src/reposcan_inference/edge_bench.py` and to the corresponding `_run_frame_with_stage_timings` helper

## Related Documents

- [Acceptance Harness](ACCEPTANCE_HARNESS.md)
- [Inference Runtime Evidence](INFERENCE_RUNTIME_EVIDENCE.md)
- [Promoted Model Benchmarks](PROMOTED_MODEL_BENCHMARKS.md)
- [Production Readiness](PRODUCTION_READINESS.md)
- [Project Status Checklist](PROJECT_STATUS_CHECKLIST.md)
