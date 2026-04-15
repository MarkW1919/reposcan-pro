# Internet Vehicle Image Pipeline

This workflow uses FiftyOne as the packaged intake, review, and export layer for
internet-sourced vehicle images. Public images are treated as candidate data
until a reviewer confirms provenance, vehicle labels, and RepoScan export fields.

## Setup

Install the optional dataset tooling:

```powershell
.\.venv\Scripts\python.exe -m pip install ".[dataset]"
```

Create the local data workspace if it does not already exist:

```powershell
.\.venv\Scripts\python.exe .\scripts\init_dataset_workspace.py --root .\data
```

FiftyOne keeps its dataset database and Open Images cache outside git by
default under the user profile. Use `--zoo-dir` when you want the source-image
cache on a larger data drive.

## Pull Candidate Images

Start with broad vehicle classes from Open Images, then review them into the
Oklahoma-priority classes used by RepoScan:

```powershell
.\.venv\Scripts\python.exe .\scripts\fiftyone_vehicle_dataset_pipeline.py pull-open-images `
  --dataset-name reposcan_open_images_ok_vehicle_candidates `
  --split validation `
  --classes Car Truck Bus Motorcycle `
  --max-samples 5000
```

For larger runs, pull each split separately or use a distinct dataset name per
source batch. Do not mix reviewed and unreviewed samples in the same export.

## Review Labels

Open the review app:

```powershell
.\.venv\Scripts\python.exe .\scripts\fiftyone_vehicle_dataset_pipeline.py launch-app `
  --dataset-name reposcan_open_images_ok_vehicle_candidates `
  --port 5151
```

Set these fields before export:

- `reposcan_accepted`: `true` only after visual and provenance review
- `reposcan_reviewed`: `true` after the row is ready for training export
- `reposcan_class_label`: canonical ImageFolder label, such as `ford_f_series`
- `reposcan_vehicle_make`: make label required for make/model training
- `reposcan_vehicle_model`: model or model-family label required for make/model training
- `reposcan_vehicle_year`: year or generation when available
- `reposcan_vehicle_color`: color label when building a color classifier
- `reposcan_oklahoma_tags`: tags such as `vehicle_class:pickup` and `make_model:ford_f_series`

For batch review, write a CSV template, fill it, and apply it back to the
FiftyOne dataset:

```powershell
.\.venv\Scripts\python.exe .\scripts\fiftyone_vehicle_dataset_pipeline.py write-review-template `
  --dataset-name reposcan_open_images_ok_vehicle_candidates `
  --output-csv .\data\staged\review_templates\open_images_ok_vehicle_review.csv

.\.venv\Scripts\python.exe .\scripts\fiftyone_vehicle_dataset_pipeline.py apply-review-csv `
  --dataset-name reposcan_open_images_ok_vehicle_candidates `
  --review-csv .\data\staged\review_templates\open_images_ok_vehicle_review.csv
```

## Export To RepoScan

After review, export approved samples into an ImageFolder dataset plus a typed
RepoScan manifest:

```powershell
.\.venv\Scripts\python.exe .\scripts\fiftyone_vehicle_dataset_pipeline.py export-reviewed `
  --dataset-name reposcan_open_images_ok_vehicle_candidates `
  --output-root .\data\curated\fiftyone_open_images_ok_vehicle_reviewed `
  --manifest-path .\data\manifests\public\fiftyone-open-images-ok-vehicle-reviewed.yaml `
  --task vehicle_make_model_classification `
  --copy-mode hardlink `
  --reviewer reviewer_01 `
  --review-status approved `
  --overwrite
```

Validate the exported manifest:

```powershell
.\.venv\Scripts\python.exe .\scripts\validate_training_dataset_manifest.py `
  --manifest .\data\manifests\public\fiftyone-open-images-ok-vehicle-reviewed.yaml `
  --verify-files `
  --require-approved
```

Then run the Oklahoma readiness audit. Early batches are expected to fail until
the dataset has enough reviewed samples, low-light coverage, long-range
coverage, session diversity, and Oklahoma-priority class balance:

```powershell
.\.venv\Scripts\python.exe .\scripts\audit_training_dataset_readiness.py `
  --dataset-manifest .\data\manifests\public\fiftyone-open-images-ok-vehicle-reviewed.yaml `
  --level oklahoma-commercial `
  --verify-files `
  --report-output .\runtime\dataset_readiness\fiftyone-open-images-ok-vehicle-reviewed.json
```

## Vehicle Detector Warm-Start

Open Images detection labels can also warm-start a one-class `vehicle` detector.
This does not replace reviewed Oklahoma field data, but it proves the detector
training path and gives us a public-data baseline:

```powershell
.\.venv\Scripts\python.exe .\scripts\fiftyone_vehicle_dataset_pipeline.py export-detections-yolo `
  --dataset-name reposcan_open_images_ok_vehicle_candidates `
  --output-root .\data\curated\fiftyone_open_images_vehicle_detection_warmstart `
  --manifest-path .\data\manifests\public\fiftyone-open-images-vehicle-detection-warmstart.yaml `
  --source-labels Car Truck Bus Motorcycle Van Taxi `
  --target-class-name vehicle `
  --copy-mode hardlink `
  --review-status pending `
  --overwrite
```

Run the CPU smoke detector profile to validate YOLO training and ONNX export:

```powershell
.\.venv\Scripts\python.exe .\scripts\audit_training_dataset_readiness.py `
  --dataset-manifest .\data\manifests\public\fiftyone-open-images-vehicle-detection-warmstart.yaml `
  --level warmstart `
  --verify-files `
  --report-output .\runtime\dataset_readiness\fiftyone-open-images-vehicle-detection-warmstart.json

.\.venv\Scripts\python.exe .\scripts\train_detection_model.py `
  --profile .\configs\training\vehicle-detector-open-images-cpu-smoke.yaml `
  --dataset-manifest .\data\manifests\public\fiftyone-open-images-vehicle-detection-warmstart.yaml `
  --run-name vehicle_detector_open_images_cpu_smoke_20260415 `
  --execute
```

When GPU training hardware is available, switch to the warm-start GPU profile:

```powershell
.\.venv\Scripts\python.exe .\scripts\train_detection_model.py `
  --profile .\configs\training\vehicle-detector-open-images-gpu-warmstart.yaml `
  --dataset-manifest .\data\manifests\public\fiftyone-open-images-vehicle-detection-warmstart.yaml `
  --run-name vehicle_detector_open_images_gpu_warmstart_20260415 `
  --execute
```

The smoke profile is intentionally small. It should be treated as a pipeline
validation run, not a deployable detector.

## Accuracy Notes

Open Images is useful for broad real-image coverage, but it is not enough by
itself for professional-grade Oklahoma vehicle recognition. Treat it as a
candidate pool that supports the real target set:

- field-captured Oklahoma images for final validation and holdout evidence
- Oklahoma-common vehicle mix targets from `configs/datasets/oklahoma-vehicle-coverage-targets.yaml`
- reviewed labels for priority families: Ford F-Series, Silverado, Ram pickups,
  GMC Sierra, Tacoma, Tahoe, and Suburban
- synthetic data only as supplemental support, never as the dominant validation
  or holdout source
