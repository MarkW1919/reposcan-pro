# TRAINING_WORKFLOWS.md

RepoScan Pro training workflows are profile-driven and dataset-manifest-driven.

## What Exists Today

- detection training workflow via `scripts/train_detection_model.py`
- attribute classifier workflow via `scripts/train_attribute_classifier.py`
- OCR workflow via `scripts/train_ocr_recognizer.py`
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
- `configs/training/vehicle-make-model-warmstart.yaml`

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

## Example Commands

Prepare a plate-detector run:

```powershell
.\.venv\Scripts\python.exe .\scripts\train_detection_model.py `
  --profile .\configs\training\plate-detector-finetune.yaml `
  --dataset-manifest C:\path\to\plate-dataset.yaml `
  --run-name plate_detector_run_01 `
  --dry-run
```

Prepare a vehicle make/model warm-start run from an imported legacy manifest:

```powershell
.\.venv\Scripts\python.exe .\scripts\train_attribute_classifier.py `
  --profile .\configs\training\vehicle-make-model-warmstart.yaml `
  --dataset-manifest C:\path\to\legacy-stanford-cars-warmstart.yaml `
  --run-name make_model_warmstart_01
```

Prepare an OCR fine-tuning run:

```powershell
.\.venv\Scripts\python.exe .\scripts\train_ocr_recognizer.py `
  --profile .\configs\training\plate-ocr-finetune.yaml `
  --dataset-manifest C:\path\to\plate-ocr-dataset.yaml `
  --run-name plate_ocr_run_01
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

## Legacy Dataset Integration

The imported `C:\LPR_Training` manifests fit directly into these workflows:

- Stanford Cars into the make/model warm-start profile
- Oklahoma synthetic OCR renders into the OCR profile
- Oklahoma staged detection captures into future labeled YOLO datasets after annotation

## What This Does Not Prove Yet

- that the required training frameworks are installed on every machine
- that the resulting trained models outperform the current fixture/demo stack
- that field-relevant evaluation reports are complete
- that long-range and low-light holdouts are sufficiently populated yet
