# ACCEPTANCE_HARNESS.md

The acceptance harness produces the evidence artifacts that close the hardware-gated acceptance runs in [PROJECT_STATUS_CHECKLIST.md](PROJECT_STATUS_CHECKLIST.md) §12.179, §12.180, and §12.181 and feed the evidence register in [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md).

The harness is a thin wrapper over the existing promoted-bundle benchmark runner. It groups the benchmark subset tags into three acceptance lanes, scores each lane from the same single inference pass, and writes per-lane markdown reports plus a signed JSON sidecar and a run manifest.

## When to use it

Run the acceptance harness every time any of these change:

- a new promoted runtime bundle is accepted
- a new field-eval holdout is staged and qualified
- the deployment profile is updated in a way that affects runtime selection
- a production-readiness review is about to be signed

Until hardware arrives, the harness runs against the repo-tracked ONNX fixture bundle and the qualified internal holdout so the pipeline stays exercised.

## Prerequisites

- a promoted model stack config (a packaged ONNX bundle config or a tracked local runtime config)
- either a qualified `eval_holdout` dataset manifest (preferred) or a hand-written benchmark manifest
- a pipeline config (defaults to `configs/pipelines/default-edge.yaml`)
- optionally a deployment profile config so the harness records deployment readiness

For field runs, the eval-holdout manifest must pass the qualification gate documented in [FIELD_EVAL_QUALIFICATION.md](FIELD_EVAL_QUALIFICATION.md). Tagging conventions for field assets are defined in [FIELD_CAPTURE_KIT.md](FIELD_CAPTURE_KIT.md) and [ANNOTATION_STANDARDS.md](ANNOTATION_STANDARDS.md).

## Lane routing

Each acceptance lane pulls from a named set of source tags. Frames carrying any source tag in a lane are routed into that lane. A single frame can feed more than one lane (a night long-range shot feeds both long-range and low-light).

| Lane | Source tags |
|---|---|
| long_range | long_range |
| low_light | low_light, dusk, night, no_light, ir_assisted, glare |
| moving_platform | moving_platform, moving_vehicle |

Source tags are emitted automatically from the dataset manifest by `build_benchmark_manifest_from_eval_holdout`:

- `long_range` is added when the asset's `distance_band` is `long_range`
- `low_light` and related lighting tags are added from the asset's `lighting_conditions`
- `moving_platform` and `moving_vehicle` must be set explicitly on the asset's `tags` list by the field team

The harness stamps each frame with the appropriate `lane:<name>` tags before running the benchmark, so the benchmark report's subset map carries lane aggregates alongside the raw tag subsets.

## Invocation

Invoke the harness through the repo Python environment. On Windows:

```powershell
.\.venv\Scripts\python.exe .\scripts\run_acceptance.py `
  --model-config .\ml\inference\fixtures\promoted-onnx-runtime\promoted-onnx.yaml `
  --dataset-manifest .\configs\datasets\runtime-benchmark-qualified-holdout.yaml `
  --deployment-config .\configs\deployments\local-dev.yaml
```

Key flags:

- `--model-config` (required): promoted model stack config
- `--dataset-manifest` OR `--benchmark-manifest` (required, mutually exclusive)
- `--pipeline-config` (default `configs/pipelines/default-edge.yaml`)
- `--deployment-config` (optional, enables deployment-readiness recording)
- `--output-root` (default `artifacts/acceptance`)
- `--run-id` (default: auto-generated `acc_<utc-timestamp>`)
- `--derived-benchmark-output`: write the lane-stamped benchmark manifest for audit
- `--json`: print the full acceptance report as JSON on stdout

## Output layout

Every run lands in `artifacts/acceptance/<run_id>/`:

```text
artifacts/acceptance/<run_id>/
|-- run_manifest.json         # run id, git HEAD, inputs, lane status summary
|-- acceptance_report.json    # structured AcceptanceRunReport sidecar
|-- benchmark_report.json     # raw PromotedModelBenchmarkReport sidecar
|-- production_readiness_evidence.json # criterion-to-artifact evidence map
|-- overall_report.md         # overall metrics + lane summary table
|-- long_range_report.md      # long-range lane metrics or "not evaluated"
|-- low_light_report.md       # low-light lane metrics or "not evaluated"
`-- moving_platform_report.md # moving-platform lane metrics or "not evaluated"
```

These paths intentionally match the evidence register paths in [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md) so an approved run can be referenced directly in the go/no-go decision.
The `production_readiness_evidence.json` sidecar binds the run ID, source dataset manifest, derived benchmark manifest, and covered readiness criteria so reviewers can trace evidence rows without reconstructing that mapping from separate files.

## How lanes get marked "not evaluated"

A lane reports `not_evaluated` when no frame in the source manifest routes into it. The lane report explains which source tags it was looking for so the field team can tag the relevant assets and re-run. A not-evaluated lane does not fail the harness — it marks the evidence register row as still pending.

## Swapping synthetic for real footage

Until the deployment rig returns field captures, run the harness against the repo-tracked fixture holdout so the pipeline stays exercised:

```powershell
.\.venv\Scripts\python.exe .\scripts\run_acceptance.py `
  --model-config .\ml\inference\fixtures\promoted-onnx-runtime\promoted-onnx.yaml `
  --dataset-manifest .\configs\datasets\runtime-benchmark-qualified-holdout.yaml `
  --deployment-config .\configs\deployments\local-dev.yaml
```

When real field captures land, follow the field handoff path in [FIELD_CAPTURE_KIT.md](FIELD_CAPTURE_KIT.md) §Handoff and re-run the harness against the field eval-holdout manifest. The CLI is the same; only the manifest path changes.

A real-footage run is the only acceptable evidence for criterion P1-2, P2-2, P6-1 (and related rows) in [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md). Fixture-holdout runs cannot close those rows; they only prove the pipeline is alive.

## Contract with the rest of the repo

- the harness does not reimplement inference; it drives the existing `reposcan_inference.benchmark_promoted_model`
- the harness does not mutate the input manifest; it clones and re-tags frames in memory before scoring
- the harness does not edit `PRODUCTION_READINESS.md`; the reviewer reads the generated reports and updates the evidence register
- acceptance-lane grouping is defined in `services/inference/src/reposcan_inference/acceptance.py`; changing the routing requires updating the lane source-tag map there

## Related Documents

- [Field Capture Kit](FIELD_CAPTURE_KIT.md)
- [Field Eval Qualification](FIELD_EVAL_QUALIFICATION.md)
- [Annotation Standards](ANNOTATION_STANDARDS.md)
- [Inference Runtime Evidence](INFERENCE_RUNTIME_EVIDENCE.md)
- [Promoted Model Benchmarks](PROMOTED_MODEL_BENCHMARKS.md)
- [Production Readiness](PRODUCTION_READINESS.md)
- [Project Status Checklist](PROJECT_STATUS_CHECKLIST.md)
