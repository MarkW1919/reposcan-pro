# RepoScan Pro

RepoScan Pro is a fresh-build repository for a field-grade, edge-first vehicle intelligence platform optimized for long-range license plate capture, low-light resilience, and local-first operation.

## Current Repository Phase

This repository currently contains:
- shared contracts and config loaders
- local-first storage, alert, review, sync, and profiling service foundations
- FastAPI endpoints for health, detections, alerts, reviews, hotlists, dashboard overview, and popup activity
- a cab-first React operator UI with live popup activity, evidence preview, hotlist management, persistent alert response workflow, local review workflow, and app-driven demo ingest control when the API is available, plus local demo fallback when it is not
- a headless file-sequence ingest path that runs capture, low-light-oriented preprocessing, inference, tracking, alerting, and storage without camera hardware
- a tracked builtin inference-runtime stack plus model-stack validation for no-hardware demos and config readiness checks
- a tracked ONNX runtime fixture stack that proves real backend-loaded vehicle, plate, OCR, and attribute execution without requiring field hardware
- repo-tracked promoted ONNX and TensorRT fixture bundles plus baseline runtime benchmark evidence for the remaining Section 4 inference-runtime gates
- tracker-strategy benchmarking and duplicate-suppression evidence for crowded scenes, camera motion, and repeated passes
- deployment-aware storage maintenance, evidence export packaging, and JSON recovery hardening
- a deployment-selectable Postgres/PostGIS metadata backend while local-dev remains json-backed by default
- HTTP remote sync replay and alert webhook delivery validated against a real local fixture endpoint
- versioned API search, auth, audit, and rate-limit hardening for external integrations
- bootstrap, build, and validation scripts for the current integrated slice

The design-first scaffold has already been turned into a working implementation foundation.
The current focus is post-blueprint integration and demo readiness rather than returning to Phase 1 setup work.

## Mission Snapshot

RepoScan Pro is being designed to:
- detect vehicles at long range
- detect and isolate license plates
- perform OCR
- classify vehicle attributes
- survive low-light and no-light conditions
- run primary inference locally on edge hardware
- record detections with GPS, time, and camera metadata

The canonical mission and rules live in [CLAUDE.md](CLAUDE.md).

## Canonical Documents

- [Product](docs/PRODUCT.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Implementation Blueprint](docs/IMPLEMENTATION_BLUEPRINT.md)
- [Requirements](docs/REQUIREMENTS.md)
- [Camera And Imaging](docs/CAMERA_AND_IMAGING.md)
- [Camera Deployment Workflow](docs/CAMERA_DEPLOYMENT_WORKFLOW.md)
- [Models](docs/MODELS.md)
- [Datasets](docs/DATASETS.md)
- [Annotation Standards](docs/ANNOTATION_STANDARDS.md)
- [Dataset Intake Workflow](docs/DATASET_INTAKE_WORKFLOW.md)
- [Detection Dataset Curation](docs/DETECTION_DATASET_CURATION.md)
- [Field Eval Qualification](docs/FIELD_EVAL_QUALIFICATION.md)
- [Training](docs/TRAINING.md)
- [Training Workflows](docs/TRAINING_WORKFLOWS.md)
- [Model Releases](docs/MODEL_RELEASES.md)
- [Inference](docs/INFERENCE.md)
- [Inference Runtime Evidence](docs/INFERENCE_RUNTIME_EVIDENCE.md)
- [Tracking Fusion Evidence](docs/TRACKING_FUSION_EVIDENCE.md)
- [Storage Media Workflows](docs/STORAGE_MEDIA_WORKFLOWS.md)
- [Sync Remote Evidence](docs/SYNC_REMOTE_EVIDENCE.md)
- [Model Promotion Workflow](docs/MODEL_PROMOTION_WORKFLOW.md)
- [Promoted Model Benchmarks](docs/PROMOTED_MODEL_BENCHMARKS.md)
- [Preprocessing Benchmark](docs/PREPROCESSING_BENCHMARK.md)
- [Deployment](docs/DEPLOYMENT.md)
- [API Contracts](docs/API_CONTRACTS.md)
- [API Integration Guide](docs/API_INTEGRATION_GUIDE.md)
- [UI Workflows](docs/UI_WORKFLOWS.md)
- [Operations And Logging](docs/OPERATIONS_AND_LOGGING.md)
- [Project Status Checklist](docs/PROJECT_STATUS_CHECKLIST.md)
- [Decisions](docs/DECISIONS.md)

## Repository Layout

```text
reposcan-pro/
|-- CLAUDE.md
|-- README.md
|-- docs/
|-- .claude/
|   |-- settings.json
|   |-- settings.local.json
|   |-- agents/
|   `-- skills/
|-- apps/
|   |-- api/
|   `-- ui/
|-- packages/
|   `-- contracts/
|-- services/
|   |-- capture/
|   |-- preprocessing/
|   |-- inference/
|   |-- tracking/
|   |-- storage/
|   |-- alerting/
|   `-- sync/
|-- ml/
|   |-- training/
|   `-- inference/
|-- configs/
|-- infra/
|-- scripts/
`-- tests/
```

## Environment Baseline

- Python 3.11 via `py -3.11`
- Node 24 and npm 11
- Docker Compose for local Postgres/PostGIS and Redis
- Git with local milestone commits from day one

## Local Workflow

1. Run `powershell -ExecutionPolicy Bypass -File .\scripts\bootstrap.ps1`
2. Open [RepoScan Pro.code-workspace](RepoScan Pro.code-workspace) in VS Code or run [Open RepoScan Pro Dev.cmd](Open RepoScan Pro Dev.cmd)
3. Review [CLAUDE.md](CLAUDE.md) and the documents under [docs](docs)
4. Run `powershell -ExecutionPolicy Bypass -File .\scripts\check.ps1`
5. Start the API with `npm run api:dev`
6. Start the UI with `npm run ui:dev`
7. Use the manual demo checklist in [tests/manual/demo_vertical_slice.md](tests/manual/demo_vertical_slice.md)

## Headless Ingest Demo

Use the file-sequence runner to turn any folder of `.jpg` test frames into fresh detections and alerts that the live API and UI can serve immediately.
When preprocessing is enabled, the runner also writes inference-ready frame artifacts under `runtime/preprocessed` by default.

For a closer-to-deployable demo flow, start the API and UI, then launch the same ingest path from the `Quick Actions` panel inside `Recovery Alerts`.
The UI talks to the live API demo runtime endpoints, so new detections and alerts appear without opening another terminal, and the same panel can persist alert acknowledge, stand-down, and reopen actions during the demo.
The runner now defaults to [configs/models/local-onnx-runtime.yaml](configs/models/local-onnx-runtime.yaml), which is a tracked ONNX runtime fixture stack for demo use. If a frame has a sibling `*.inference.json` sidecar, that sidecar can drive per-frame detections, OCR, and vehicle attributes through the full ingest path. The older [configs/models/local-demo-runtime.yaml](configs/models/local-demo-runtime.yaml) builtin stack remains available as the no-hardware fallback.

```powershell
.\.venv\Scripts\python.exe .\scripts\run_file_sequence_demo.py --frames-dir C:\path\to\frame-folder
```

The runner uses [configs/cameras/local-file-demo.yaml](configs/cameras/local-file-demo.yaml) and [configs/models/local-onnx-runtime.yaml](configs/models/local-onnx-runtime.yaml) by default, writes development metadata under `runtime/storage`, and writes preprocessing artifacts under `runtime/preprocessed` unless you override those paths.

Validate a model stack before a demo or runtime swap with:

```powershell
.\.venv\Scripts\python.exe .\scripts\validate_model_stack.py --model-config .\configs\models\local-onnx-runtime.yaml
```

Package a self-contained promoted ONNX bundle outside git with:

```powershell
.\.venv\Scripts\python.exe .\scripts\package_promoted_onnx_bundle.py --source-model-config .\configs\models\local-onnx-runtime.yaml --output-dir C:\artifacts\models\promoted\fixture-bundle
```

Assemble a promoted ONNX bundle directly from exported per-stage ONNX artifacts with:

```powershell
.\.venv\Scripts\python.exe .\scripts\assemble_promoted_onnx_bundle.py --template-model-config .\configs\models\local-onnx-runtime.yaml --vehicle-detector-artifact C:\exports\vehicle-detector.onnx --plate-detector-artifact C:\exports\plate-detector.onnx --ocr-artifact C:\exports\ocr.onnx --classifier-artifact C:\exports\classifier.onnx --classifier-label-metadata C:\exports\labels.json --output-dir C:\artifacts\models\promoted\exported-bundle
```

For future edge bundles, use [configs/models/promoted-tensorrt-template.yaml](configs/models/promoted-tensorrt-template.yaml) as the contract shape for external TensorRT engine manifests.

Validate a promoted bundle against a deployment target with:

```powershell
.\.venv\Scripts\python.exe .\scripts\validate_edge_runtime_bundle.py --model-config C:\path\to\promoted-bundle\promoted-tensorrt.yaml --deployment-config .\configs\deployments\jetson-orin-edge.yaml
```

Prepare the local training-data workspace and import legacy training sources with:

```powershell
.\.venv\Scripts\python.exe .\scripts\init_dataset_workspace.py --root .\data
.\.venv\Scripts\python.exe .\scripts\import_legacy_training_sources.py --output-dir .\data\manifests\legacy
```

Prepare a training run from a profile and dataset manifest with:

```powershell
.\.venv\Scripts\python.exe .\scripts\train_attribute_classifier.py --profile .\configs\training\vehicle-make-model-warmstart.yaml --dataset-manifest C:\path\to\dataset-manifest.yaml --run-name warmstart_01
```

The attribute-classifier workflow now exports `model.onnx` plus a `labels.json` metadata sidecar so single-task color or make/model classifiers can plug back into the runtime and promoted bundle flow.

Supplement a primary OCR dataset with a capped synthetic support manifest through the same prepare workflow:

```powershell
.\.venv\Scripts\python.exe .\scripts\train_ocr_recognizer.py --profile .\configs\training\plate-ocr-finetune.yaml --dataset-manifest C:\path\to\reviewed-field-ocr.yaml --support-dataset-manifest .\data\staged\synthetic_ok_ocr_claude_handoff_2026-03-24\manifest.yaml --run-name field_ocr_with_support --allow-pending
```

Export a detection label index and promote reviewed YOLO labels into curated manifests with:

```powershell
.\.venv\Scripts\python.exe .\scripts\export_detection_label_index.py --dataset-manifest .\data\manifests\legacy\legacy-oklahoma-detection-reviewed.yaml --output .\data\manifests\legacy\legacy-oklahoma-detection-label-index.csv
.\.venv\Scripts\python.exe .\scripts\promote_detection_dataset.py --dataset-manifest .\data\manifests\legacy\legacy-oklahoma-detection-reviewed.yaml --split-manifest .\data\manifests\legacy\legacy-oklahoma-detection-split.yaml --labels-root C:\datasets\oklahoma_detection_labels --output-root .\data\curated --output-manifest .\data\manifests\legacy\legacy-oklahoma-detection-curated.yaml --field-eval-manifest .\data\manifests\legacy\legacy-oklahoma-detection-field-eval.yaml --reviewer qa_annotator_01
```

Generate a benchmark report directly from an approved field-eval dataset manifest with:

```powershell
.\.venv\Scripts\python.exe .\scripts\benchmark_promoted_bundle.py --model-config C:\artifacts\models\promoted\fixture-local-dev\promoted-onnx.yaml --dataset-manifest .\configs\datasets\example-field-eval-holdout.yaml --deployment-config .\configs\deployments\local-dev.yaml --derived-benchmark-output C:\artifacts\models\benchmarks\example-field-eval-benchmark.yaml --report-output C:\artifacts\models\reports\example-field-eval-report.json
```

Qualify a reviewed field-eval manifest before treating it as a real regression holdout with:

```powershell
.\.venv\Scripts\python.exe .\scripts\qualify_field_eval_dataset.py --dataset-manifest C:\artifacts\data\manifests\oklahoma-field-eval.yaml --verify-files --report-output C:\artifacts\data\reports\oklahoma-field-eval-qualification.json
```

Refresh the repo-tracked Section 4 inference-runtime evidence fixtures with:

```powershell
.\.venv\Scripts\python.exe .\scripts\generate_inference_runtime_evidence.py --output-root .\ml\inference\fixtures --overwrite
```

Refresh the repo-tracked Section 5 tracking-and-fusion evidence report with:

```powershell
.\.venv\Scripts\python.exe .\scripts\generate_tracking_evidence.py --output-root .\services\tracking\fixtures --overwrite
```

Run storage maintenance and export a detection evidence package with:

```powershell
.\.venv\Scripts\python.exe .\scripts\run_storage_maintenance.py --deployment-config .\configs\deployments\local-dev.yaml --json
.\.venv\Scripts\python.exe .\scripts\export_detection_package.py --detection-id det_20260320_010001 --json
.\.venv\Scripts\python.exe .\scripts\bootstrap_postgres_storage.py --deployment-config .\configs\deployments\jetson-orin-edge.yaml
.\.venv\Scripts\python.exe .\scripts\generate_sync_remote_evidence.py --output-root .\services\sync\fixtures --overwrite
```

Register a validated promoted bundle into an external release registry with:

```powershell
.\.venv\Scripts\python.exe .\scripts\register_model_release.py --model-config C:\artifacts\models\promoted\fixture-local-dev\promoted-onnx.yaml --deployment-config .\configs\deployments\local-dev.yaml --benchmark-manifest C:\artifacts\models\benchmarks\oklahoma-night-long-range.yaml --registry-root C:\artifacts\models\registry --channel local-dev-demo
```

## Desktop Launcher

To create the desktop launcher and double-click shortcut for this repo, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\create_desktop_launcher.ps1
```

That script creates:
- `RepoScan Pro Dev Home` on your desktop
- `RepoScan Pro Dev.lnk` on your desktop

Both point back to the repo-owned workspace and launcher files so the setup stays synced with the Git repository.

## Claude, Codex, And VS Code

- Claude Code integration lives in [CLAUDE.md](CLAUDE.md) and the files under [.claude](.claude)
- Codex is working directly against this Git-tracked repo
- VS Code integration lives in [.vscode](.vscode), [RepoScan Pro.code-workspace](RepoScan Pro.code-workspace), and [Open RepoScan Pro Dev.cmd](Open RepoScan Pro Dev.cmd)
- the older `Seen-It-First Dev Home` desktop launcher is a separate project and is not the entry point for this repo

## Claude Build Prompt

Use this prompt inside the repository to continue implementation from the current integrated state:

```text
Read CLAUDE.md, docs/IMPLEMENTATION_BLUEPRINT.md, docs/API_CONTRACTS.md, and the current repo state.

Continue the next implementation slice now.

Do not rebuild completed foundations. Prefer live integration, seeded demo readiness, operator workflow completion, test coverage, and manual field-test documentation.
```

## Version Control And Artifact Policy

- Commit milestone changes locally as you progress.
- Do not commit datasets, model weights, local media, or generated runtime artifacts, except the small repo-owned inference fixtures under `ml/inference/fixtures/` and the small repo-owned tracking evidence report under `services/tracking/fixtures/`.
- Treat the existing prototype in the parent workspace as separate history and do not modify it from this repo.
