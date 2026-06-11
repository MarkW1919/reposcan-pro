# DETECTION_DATASET_CURATION.md

RepoScan Pro promotes plate-detection datasets from reviewed capture manifests rather than treating loose image folders as training-ready by default.

## Goal

Take a reviewed `generic_capture` manifest plus YOLO label files and produce:

- a curated `yolo_detection` dataset manifest for train, validation, and holdout
- a protected `eval_holdout` manifest for any `field_eval` assignments

This keeps trainable data, holdouts, and label review all on the same typed path.

## 1. Export A Label Index

Start from a reviewed capture manifest and, optionally, a split manifest:

```powershell
.\.venv\Scripts\python.exe .\scripts\export_detection_label_index.py `
  --dataset-manifest .\data\manifests\legacy\legacy-oklahoma-detection-reviewed.yaml `
  --split-manifest .\data\manifests\legacy\legacy-oklahoma-detection-split.yaml `
  --output .\data\manifests\legacy\legacy-oklahoma-detection-label-index.csv
```

The exported CSV lists:

- source image path
- relative image path
- mirrored YOLO label path suggestion
- capture session
- planned split, when a split manifest is present
- lighting, distance, tags, and field-eval hints

## 2. Place YOLO Labels Under A Mirrored Root

The promotion workflow expects label files under a separate root that mirrors the capture-relative image paths.

Example:

```text
labels-root/
`-- session_20260322_ok_night/
    |-- frame_0001.txt
    `-- frame_0002.txt
```

Each label file should contain one or more YOLO rows:

```text
0 0.51 0.63 0.18 0.09
```

RepoScan validates:

- numeric class id
- 5-column YOLO shape
- normalized `[0, 1]` coordinates
- positive width and height

## 3. Promote Into Curated And Eval Datasets

```powershell
.\.venv\Scripts\python.exe .\scripts\promote_detection_dataset.py `
  --dataset-manifest .\data\manifests\legacy\legacy-oklahoma-detection-reviewed.yaml `
  --split-manifest .\data\manifests\legacy\legacy-oklahoma-detection-split.yaml `
  --labels-root C:\datasets\oklahoma_detection_labels `
  --output-root .\data\curated `
  --output-manifest .\data\manifests\legacy\legacy-oklahoma-detection-curated.yaml `
  --field-eval-manifest .\data\manifests\legacy\legacy-oklahoma-detection-field-eval.yaml `
  --reviewer qa_annotator_01
```

The script:

- validates the source capture manifest and split plan
- validates every YOLO label file
- copies or hard-links images and labels into curated dataset layout
- writes promoted image and label filenames by stable `asset_id` to avoid long Windows path issues
- writes an approved `yolo_detection` manifest for train, validation, and holdout
- writes an approved `eval_holdout` manifest when `field_eval` assignments exist

## 4. Use The Curated Manifest For Training

```powershell
.\.venv\Scripts\python.exe .\scripts\train_detection_model.py `
  --profile .\configs\training\plate-detector-finetune.yaml `
  --dataset-manifest .\data\manifests\legacy\legacy-oklahoma-detection-curated.yaml `
  --run-name ok_plate_detector_v1 `
  --dry-run
```

## Legacy Oklahoma Notes

The old `C:\LPR_Training` Oklahoma staging data is useful as a source manifest and image pool, but it is not already a finished training dataset:

- `incoming_raw/` contains staged captures
- `train/`, `valid/`, `test/`, and `us_eval/oklahoma_holdout/` are currently empty on this machine
- labels still need to be reviewed and promoted through the RepoScan workflow above

## What This Does Not Prove Yet

This workflow does not prove:

- that the current labels are correct
- that night and long-range holdouts are sufficiently populated
- that promoted models are accurate enough for field use

It does prove that reviewed labels can be turned into repeatable training and eval datasets without bypassing RepoScan’s manifest and review rules.
