# TRAINING_WORKFLOWS.md

RepoScan Pro training workflows are profile-driven and dataset-manifest-driven.

## What Exists Today

- detection training workflow via `scripts/train_detection_model.py`
- attribute classifier workflow via `scripts/train_attribute_classifier.py`
- OCR workflow via `scripts/train_ocr_recognizer.py`
- dry-run export handoff commands for detection ONNX export
- reusable training profiles under `configs/training/`
- run-manifest generation under `runtime/training/` by default

## Safety Model

These scripts are prepare-first.

- without `--execute`, they only validate inputs, write prep artifacts, and write a run manifest
- `--dry-run` prints the framework command or script invocation that would be used
- `--execute` is reserved for machines that actually have the required frameworks installed
- `--allow-pending` exists for controlled dry-runs against imported but not-yet-approved manifests

## Current Profiles

- `configs/training/vehicle-detector-finetune.yaml`
- `configs/training/plate-detector-finetune.yaml`
- `configs/training/plate-ocr-finetune.yaml`
- `configs/training/vehicle-color-classifier.yaml`
- `configs/training/vehicle-color-classifier-efficientnet.yaml`
- `configs/training/vehicle-make-model-warmstart.yaml`
- `configs/training/vehicle-make-model-warmstart-v2.yaml`
- `configs/training/vehicle-make-model-warmstart-regularized.yaml`
- `configs/training/vehicle-make-model-warmstart-cpu.yaml`
- `configs/training/vehicle-make-model-reviewed-seed-cpu.yaml`

## Current Make/Model Baseline

The strongest completed make/model warm-start run on this workstation is currently:

- run: `runtime/training/vehicle-make-model-warmstart-v2_20260409_141756`
- validation accuracy: `0.8534`
- Stanford Cars holdout accuracy: `0.8493`

Treat CPU-only runs such as `vehicle-make-model-warmstart-cpu` as workflow validation unless they beat that baseline. For production promotion, prefer field-reviewed make/model crops and qualified long-range / low-light holdouts over another Stanford-only comparison.

## Detection Dataset Promotion

Detector fine-tuning should not point at loose staged capture folders.

Use this flow instead:

1. reviewed `generic_capture` manifest
2. optional session-aware split manifest
3. `scripts/export_detection_label_index.py`
4. mirrored YOLO labels root
5. `scripts/promote_detection_dataset.py`
6. `scripts/train_detection_model.py`

This keeps detection training, holdout protection, and later regression evaluation tied back to typed manifests instead of ad hoc folder edits.

## Framework Expectations

- `ultralytics` for detection fine-tuning
- `torch` and `torchvision` for attribute classifiers
- `PaddleOCR` checkout for OCR fine-tuning
- `scipy` is also required when executing the Stanford Cars warm-start path

Current warm-start defaults:

- vehicle detector: `yolo11n.pt`
- plate detector: `yolo11s.pt`
- make/model warm start: `efficientnet_b0`
- make/model CPU fallback: `resnet18` at `192px`
- color classifier baseline: `resnet18`, with an `efficientnet_b0` profile available for harder lighting drift cases

## Example Commands

Prepare a plate-detector run:

```powershell
.\.venv\Scripts\python.exe .\scripts\train_detection_model.py `
  --profile .\configs\training\plate-detector-finetune.yaml `
  --dataset-manifest C:\path\to\plate-dataset.yaml `
  --run-name plate_detector_run_01 `
  --dry-run
```

That dry-run now prints both the training command and the expected ONNX export command so the promoted-runtime handoff stays reviewable before execution.

Prepare a vehicle make/model warm-start run from an imported legacy manifest:

```powershell
.\.venv\Scripts\python.exe .\scripts\train_attribute_classifier.py `
  --profile .\configs\training\vehicle-make-model-warmstart.yaml `
  --dataset-manifest C:\path\to\legacy-stanford-cars-warmstart.yaml `
  --run-name make_model_warmstart_01
```

On CPU-bound development machines, use the lighter warm-start profile instead:

```powershell
.\.venv\Scripts\python.exe .\scripts\train_attribute_classifier.py `
  --profile .\configs\training\vehicle-make-model-warmstart-cpu.yaml `
  --dataset-manifest C:\path\to\legacy-stanford-cars-warmstart.yaml `
  --run-name make_model_warmstart_cpu_01
```

Launch a prepared training job with live output in the same terminal:

```powershell
.\.venv\Scripts\python.exe .\scripts\launch_training_run.py `
  --run-manifest .\runtime\training\make_model_warmstart_01\run_manifest.json
```

That launcher now streams the child process into the current terminal and also keeps writing:

For attribute-classifier runs, monitor:

- `runtime/training/<run-name>/training_status.json`
- `runtime/training/<run-name>/training_events.log`
- `runtime/training/logs/<run-name>.stdout.log`
- `runtime/training/logs/<run-name>.stderr.log`
- `runtime/training/<run-name>/evaluation_summary.json`

For Stanford Cars warm-start runs:

- the per-epoch `val_acc` used for early stopping is an internal seeded split from `cars_train`
- when a manifest `holdout` split is available and labeled, the workflow now evaluates the best checkpoint against that holdout after training completes
- the resulting best-checkpoint metrics are written to `evaluation_summary.json` so internal validation and holdout accuracy stay distinguishable

If you need the run to survive terminal closure instead, launch it explicitly in detached mode:

```powershell
.\.venv\Scripts\python.exe .\scripts\launch_training_run.py `
  --run-manifest .\runtime\training\make_model_warmstart_01\run_manifest.json `
  --detached
```

If training completed but export failed, rerun export only from the saved checkpoint:

```powershell
.\.venv\Scripts\python.exe .\scripts\train_attribute_classifier.py `
  --profile .\configs\training\vehicle-make-model-warmstart-cpu.yaml `
  --dataset-manifest .\data\manifests\legacy\legacy-stanford-cars-warmstart.yaml `
  --run-name vehicle_make_model_warmstart_cpu_20260401_rerun1 `
  --export-only
```

Practical hardware note:

- on this repo's typical CPU-only Windows development machine, `efficientnet_b0` profiles above `224px` and long post-unfreeze runs can take hours per epoch
- use `vehicle-make-model-warmstart-cpu.yaml` for local workflow validation and CPU-bound iteration
- reserve larger regularized profiles such as `vehicle-make-model-warmstart-v2.yaml` for GPU-backed training comparisons

Build a canonical make/model/year catalog from a markdown seed list before collecting or promoting field data:

```powershell
.\.venv\Scripts\python.exe .\scripts\build_vehicle_recognition_catalog.py `
  --seed .\configs\datasets\example-vehicle-recognition-seed.md `
  --overrides .\configs\datasets\example-vehicle-recognition-overrides.yaml `
  --placeholder-mode make-all-models `
  --output .\runtime\vehicle_catalogs\us-vehicle-recognition-catalog.yaml `
  --expanded-seed-csv .\runtime\vehicle_catalogs\us-vehicle-recognition-expanded-seed.csv `
  --labels-csv .\runtime\vehicle_catalogs\us-vehicle-recognition-labels.csv
```

That workflow caches the official model-year lookups locally, can expand placeholder make-coverage rows into explicit model rows, emits a canonical catalog, expands training-ready labels of the form `Make Model Year`, and accepts a narrow alias/override file for source-name mismatches without weakening the year-validation path.

Prepare an OCR fine-tuning run:

```powershell
.\.venv\Scripts\python.exe .\scripts\train_ocr_recognizer.py `
  --profile .\configs\training\plate-ocr-finetune.yaml `
  --dataset-manifest C:\path\to\plate-ocr-dataset.yaml `
  --run-name plate_ocr_run_01
```

When a PaddleOCR checkout is supplied, the workflow now prefers a PP-OCRv5 English recognition config if one is available under that checkout and falls back to PP-OCRv4 or PP-OCRv3 otherwise.

Prepare an OCR fine-tuning run with supplemental synthetic support data:

```powershell
.\.venv\Scripts\python.exe .\scripts\train_ocr_recognizer.py `
  --profile .\configs\training\plate-ocr-finetune.yaml `
  --dataset-manifest C:\path\to\reviewed-field-ocr.yaml `
  --support-dataset-manifest .\data\staged\synthetic_ok_ocr_run_01\manifest.yaml `
  --run-name plate_ocr_with_support_01 `
  --allow-pending
```

## Augmentation Policy

All profiles carry an explicit augmentation policy covering:

- motion blur
- defocus blur
- brightness and contrast changes
- noise
- compression artifacts
- perspective distortion
- capped synthetic support ratio

This keeps augmentation reviewable instead of burying it in ad hoc trainer code.

## Synthetic OCR Dataset Generator

`scripts/generate_synthetic_ok_ocr_dataset.py` generates RepoScan-compatible synthetic Oklahoma plate crops for OCR support training. It produces a manifest with `format=ocr_manifest` and `review_status=pending` by default.

```powershell
.\.venv\Scripts\python.exe .\scripts\generate_synthetic_ok_ocr_dataset.py `
  --count 300 `
  --output-root .\data\staged\synthetic_ok_ocr_run_01 `
  --seed 42
```

The generated dataset plugs directly into the OCR prepare workflow with `--allow-pending`. Synthetic support data should stay supplemental to reviewed field plate crops, matching the `synthetic_support_ratio` cap in the OCR profile.

When `--support-dataset-manifest` is supplied to the OCR workflow:

- the primary dataset remains the source of validation and holdout lists
- synthetic support rows are only mixed into the training list
- the profile `augmentation.synthetic_support_ratio` caps how many synthetic training rows are added
- the workspace records the applied mix in `ocr_support_mix_summary.json`

## Legacy Dataset Integration

The imported `C:\LPR_Training` manifests fit directly into these workflows:

- Stanford Cars into the make/model warm-start profile
- Oklahoma synthetic OCR renders into the OCR profile
- Oklahoma staged detection captures into future labeled YOLO datasets after annotation

## Public Real-Data Intake

When public data is needed before synthetic support is mixed in, use real datasets first and keep their provenance explicit.

- Vehicle make/model warm start: Stanford Cars remains the current wired source on this machine and is already represented by `data/manifests/legacy/legacy-stanford-cars-warmstart.yaml`.
- US plate OCR benchmark: `scripts/import_openalpr_us_ocr_dataset.py` can convert the public OpenALPR US benchmark mirror from `lawrencexli/USLicensePlateOCR/train_data` into a RepoScan `ocr_manifest`.
- Additional real-data candidates worth reviewing before more synthetic generation: VMMRdb for broader real make/model coverage and the UCSD stills dataset for real vehicle images with make/model and plate metadata, subject to access and license review.

Example import for the public US OCR benchmark:

```powershell
.\.venv\Scripts\python.exe .\scripts\import_openalpr_us_ocr_dataset.py `
  --source-root .\tmp\USLicensePlateOCR\train_data `
  --output-root .\data\staged\openalpr_us_benchmark `
  --manifest-path .\data\manifests\public\openalpr-us-benchmark.yaml
```

That benchmark is small, so it should usually be the primary real OCR dataset plus synthetic support manifests, not the only OCR training source.

Before using an imported OCR dataset as a real-data source, keep these checks green:

- `import_summary.json` has `missing_source_image_count` at `0` or every missing file is reviewed and accepted
- the generated manifest validates with `scripts/validate_training_dataset_manifest.py`
- train, validation, and holdout splits are non-empty
- labels normalize to `0-9A-Z` and match the configured OCR character dictionary
- duplicate count is `0` in the import or preparation manifest

Do not promote failed OCR training workspaces just because they contain checkpoints. For OCR promotion, require:

- `training_status.json` state is `completed`
- a PaddleOCR `output/best_accuracy` checkpoint exists
- `inference_export/` was produced successfully
- validation or holdout accuracy is recorded in the run notes, benchmark report, or release handoff

Historical failed probes under `runtime/training` are useful only as debugging evidence. They should stay out of release manifests and promoted bundles.

## What This Does Not Prove Yet

- that the required training frameworks are installed on every machine
- that the resulting trained models outperform the current fixture/demo stack
- that field-relevant evaluation reports are complete
- that long-range and low-light holdouts are sufficiently populated yet

## Classifier Export Notes

The attribute-classifier workflow now exports:

- `model.onnx` with a `logits` output for the trained single-task classifier
- `labels.json` metadata describing the task and class-to-attribute mapping

That metadata sidecar is required when packaging a promoted bundle from a trained single-task classifier export. Use:

```powershell
.\.venv\Scripts\python.exe .\scripts\assemble_promoted_onnx_bundle.py `
  --template-model-config .\configs\models\local-onnx-runtime.yaml `
  --vehicle-detector-artifact C:\exports\vehicle-detector.onnx `
  --plate-detector-artifact C:\exports\plate-detector.onnx `
  --ocr-artifact C:\exports\ocr.onnx `
  --classifier-artifact C:\exports\classifier.onnx `
  --classifier-label-metadata C:\exports\labels.json `
  --output-dir C:\artifacts\models\promoted\exported-bundle
```
