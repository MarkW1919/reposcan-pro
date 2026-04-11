# EXECUTION_PLAN.md

This document defines the practical finish path for RepoScan Pro from the current repository state to requirements closure.

It exists to keep the team focused on the remaining acceptance work instead of spending time on lower-value side branches.

## Ground Truth

The project requirements are still the controlling scope:

- long-range detection
- low-light detection
- real-time inference
- edge deployment
- vehicle detection, plate detection, OCR, classification, and GPS tagging
- no cloud-inference dependency
- no internet dependency on the mission-critical path

Those requirements are not closed by synthetic benchmarks alone.
They are only closed by reviewed evidence on the correct hardware and in the correct scene conditions.

## Current Development Machine

Current local workstation profile:

- Windows 10
- Python 3.11.9
- Node 24.14.0 / npm 11.9.0
- Docker 29.2.1
- AMD Ryzen 5 5600G
- 8 GB system RAM
- installed PyTorch: `2.11.0+cpu`
- `torch.cuda.is_available() == False`

Practical conclusion:

- this machine is suitable for software integration, local demo flows, dataset plumbing, ONNX export, and light CPU-only experiments
- this machine is not the primary environment for heavy model training, TensorRT validation, or final latency claims

## Use This Machine For

- API, UI, storage, sync, and integration work
- manifest validation and dataset review workflows
- local runtime verification with [local-dev](../configs/deployments/local-dev.yaml)
- training workflow preparation, dry runs, and export-only evaluation
- lightweight classifier iteration with [vehicle-make-model-warmstart-cpu](../configs/training/vehicle-make-model-warmstart-cpu.yaml)
- targeted test runs and regression checks

## Do Not Use This Machine For

- long-running EfficientNet or larger classifier experiments intended to settle model decisions
- target-hardware latency or memory claims
- TensorRT acceptance evidence for edge deployment
- final field-acceptance signoff
- deciding that a run is stalled based only on slow CPU progress

## Required Hardware Lanes

RepoScan Pro now needs two separate hardware lanes:

1. A supported GPU training environment for serious model work.
2. A target deployment rig for edge validation and field acceptance.

The GPU training environment is for:

- make/model classifier experiments beyond the CPU warm-start profile
- detector and OCR retraining that would otherwise be too slow to iterate responsibly
- faster ablation work so model decisions are evidence-backed instead of guess-driven

The target deployment rig is for:

- [jetson-orin-edge](../configs/deployments/jetson-orin-edge.yaml) validation
- camera reconnect and power-loss behavior on deployment-intended hardware
- validation of the live GPS ingest path on deployment hardware
- TensorRT bundle validation
- latency and memory benchmarking on the actual edge target

## Finish Order

### 1. Keep The Repo Honest

Before new scope is added:

- keep `README.md`, [Project Status Checklist](PROJECT_STATUS_CHECKLIST.md), and runtime evidence aligned
- treat failing tests or stale status reporting as real delivery defects
- avoid committing sidecar dataset tools that bypass the manifest and review contract

### 2. Stabilize The Software Baseline

The software baseline is not "done" until:

- training workflows report true holdout evaluation where available
- launcher state is resilient to interrupted terminal sessions
- `check.ps1`, targeted `pytest`, and `npm run ui:build` stay usable as milestone gates

### 3. Freeze A Reference Model Per Task

For each task, identify the current model to beat before more experimentation:

- vehicle detector
- plate detector
- OCR
- color classifier
- make/model classifier

Every replacement candidate must improve against an evaluated baseline, not just produce a newer artifact.

### 4. Move Serious Training Off The CPU Workstation

Do not spend weeks trying to force the workstation into being the primary trainer.

On this machine:

- use CPU profiles
- validate workflows
- prepare manifests
- run export and evaluation plumbing

On the GPU training environment:

- run the real ablation plan
- train from the current best checkpoints instead of cold-starting expensive recipes
- compare only against real holdout metrics

### 5. Close The Remaining Requirements With Evidence

The remaining high-value gates are:

- hardware-in-the-loop capture validation
- long-range plate-readability acceptance run
- low-light / no-light acceptance run
- moving-vehicle and moving-platform acceptance run
- internet-outage local-first acceptance run
- target-hardware latency and memory benchmark report
- operator UX pilot
- production go / no-go review

These are the real completion gates for the project.

## Immediate Working Rules

- keep all new training data manifest-driven and review-gated
- treat curated field data as more valuable than additional benchmark-only web images
- use approved holdouts for acceptance evidence
- keep promoted bundles and release records outside git
- prefer small, reviewable milestones over large mixed-scope branches

## Immediate Next Actions

1. Keep the training workflow and validation surfaces green.
2. Use the current evaluated baselines as the models to beat.
3. Run local classifier iteration only with CPU-appropriate profiles.
4. Stand up or reserve a supported GPU training environment for serious retraining.
5. Prepare the deployment rig with cameras and GPS for field capture.
6. Capture and review the missing long-range, low-light, moving, and outage scenarios.
7. Benchmark promoted bundles on target hardware and record the reports.
8. Run the operator pilot and final readiness review.

## Related Documents

- [Requirements](REQUIREMENTS.md)
- [Project Status Checklist](PROJECT_STATUS_CHECKLIST.md)
- [Training](TRAINING.md)
- [Training Workflows](TRAINING_WORKFLOWS.md)
- [Deployment](DEPLOYMENT.md)
- [Camera Deployment Workflow](CAMERA_DEPLOYMENT_WORKFLOW.md)
- [Field Eval Qualification](FIELD_EVAL_QUALIFICATION.md)
