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

## Attribute Crop Review

Year, make, model, and color are vehicle attributes, not detector classes. Use
vehicle detections to create one crop per vehicle, review those crops, then
export task-specific ImageFolder manifests for attribute-classifier training.

Create a crop review queue from Open Images detections:

```powershell
.\.venv\Scripts\python.exe .\scripts\fiftyone_vehicle_dataset_pipeline.py export-attribute-crop-review `
  --dataset-name reposcan_open_images_ok_vehicle_candidates `
  --output-root .\data\staged\attribute_crops\open_images_vehicle_attribute_review_20260415 `
  --review-csv .\data\staged\review_templates\open_images_vehicle_attribute_crop_review_20260415.csv `
  --source-labels Car Truck Bus Motorcycle Van Taxi `
  --min-width-px 64 `
  --min-height-px 64 `
  --overwrite
```

Fill the crop CSV with conservative labels:

- `reposcan_accepted`: `true` when the crop contains one usable vehicle
- `reposcan_reviewed`: `true` after visual/provenance review
- `reposcan_class_label`: make/model class such as `ford_f_series`
- `reposcan_vehicle_make`: normalized make such as `ford`
- `reposcan_vehicle_model`: normalized model or family such as `f_series`
- `reposcan_vehicle_year`: exact year or generation range when defensible
- `reposcan_vehicle_color`: dominant body color
- `reposcan_oklahoma_tags`: tags such as `vehicle_class:pickup`

Optionally add review suggestions from deterministic color analysis and the
local Stanford Cars make/model warm-start model. Suggestions are reviewer aids;
they do not mark rows accepted or reviewed:

```powershell
.\.venv\Scripts\python.exe .\scripts\fiftyone_vehicle_dataset_pipeline.py suggest-attribute-labels `
  --review-csv .\data\staged\review_templates\open_images_vehicle_attribute_crop_review_20260415.csv `
  --output-csv .\data\staged\review_templates\open_images_vehicle_attribute_crop_suggestions_20260415.csv `
  --make-model-onnx .\runtime\training\vehicle-make-model-warmstart-v2_20260409_141756\exports\model.onnx `
  --make-model-labels .\runtime\training\vehicle-make-model-warmstart-v2_20260409_141756\exports\labels.json `
  --make-model-top-k 5 `
  --overwrite
```

For faster crop triage, add pretrained VLM suggestions on top of the local
suggestions. This stage reads the same crop CSV, adds `suggested_vlm_*`
columns, and leaves the authoritative RepoScan review fields untouched:

```powershell
.\.venv\Scripts\python.exe .\scripts\label_vehicle_attribute_crops_with_vlm.py label-crops `
  --review-csv .\data\staged\review_templates\open_images_vehicle_attribute_crop_suggestions_20260415.csv `
  --output-csv .\data\staged\review_templates\open_images_vehicle_attribute_crop_vlm_suggestions_20260415.csv `
  --provider openai `
  --model gpt-4o `
  --overwrite
```

For GPU-backed local or Colab runs, use Qwen2.5-VL instead:

```powershell
.\.venv\Scripts\python.exe .\scripts\label_vehicle_attribute_crops_with_vlm.py label-crops `
  --review-csv .\data\staged\review_templates\open_images_vehicle_attribute_crop_suggestions_20260415.csv `
  --output-csv .\data\staged\review_templates\open_images_vehicle_attribute_crop_vlm_suggestions_20260415.csv `
  --provider qwen2_5_vl `
  --model Qwen/Qwen2.5-VL-7B-Instruct `
  --overwrite
```

When GPU access or cloud credits are unavailable, use the local Oklahoma-tuned
CLIP fallback. It runs on CPU, emits `suggested_vlm_*` columns in the same
shape as the VLM workflow, and stays conservative by keeping generic body-type
matches in `needs_human_review`:

```powershell
.\.venv\Scripts\python.exe .\scripts\label_vehicle_attribute_crops_with_vlm.py label-crops `
  --review-csv .\data\staged\review_templates\open_images_vehicle_attribute_crop_suggestions_20260415.csv `
  --output-csv .\data\staged\review_templates\open_images_vehicle_attribute_clip_oklahoma_suggestions_20260416.csv `
  --provider clip_oklahoma `
  --clip-batch-size 16 `
  --clip-accept-confidence 0.80 `
  --overwrite
```

That path is useful for building a priority review queue when manual review is
the real bottleneck, but it should still be treated as AI-assisted draft data
rather than approved production labels.

When the AI-assisted draft queue is ready for human review, launch the local
review app instead of editing the CSV directly. Point `--review-csv` at the
most recent suggestions CSV for the batch you want to review — typically the
CLIP fallback output above, the OpenAI/Qwen VLM suggestions CSV, or a
hand-filtered subset of either:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[review-ui]"
.\.venv\Scripts\python.exe .\scripts\launch_vehicle_attribute_review_app.py `
  --review-csv .\data\staged\review_templates\open_images_vehicle_attribute_clip_oklahoma_suggestions_20260416.csv `
  --host 127.0.0.1 `
  --port 7860 `
  --inbrowser
```

The app creates a `.bak` backup alongside the review CSV on first launch and
lets the reviewer apply AI-assisted prefills, mark rows rejected, save changes,
and jump to the next pending row.

Install the optional API path locally with:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[openai-labeling]"
```

Install the optional Hugging Face VLM path in a GPU runtime with:

```powershell
python -m pip install -e ".[vlm-labeling]"
```

The VLM stage can draft high-confidence pending labels for a specific task.
Pending rows are useful for warm-start experiments, but they are not approved
production labels unless `--mark-reviewed` is passed intentionally:

```powershell
.\.venv\Scripts\python.exe .\scripts\label_vehicle_attribute_crops_with_vlm.py apply-consensus `
  --input-csv .\data\staged\review_templates\open_images_vehicle_attribute_crop_vlm_suggestions_20260415.csv `
  --output-csv .\data\staged\review_templates\open_images_vehicle_make_model_ai_consensus_pending_20260415.csv `
  --task vehicle_make_model_classification `
  --min-vlm-confidence 0.75 `
  --overwrite
```

Use [Vehicle Attribute VLM Labeling Colab](../notebooks/vehicle_attribute_vlm_labeling_colab.ipynb)
when the local machine does not have a GPU. The notebook installs the optional
VLM dependencies, labels the crop CSV, applies a pending consensus CSV, and
zips the results for download.

Export reviewed crop labels for each attribute task:

```powershell
.\.venv\Scripts\python.exe .\scripts\fiftyone_vehicle_dataset_pipeline.py export-reviewed-crops `
  --review-csv .\data\staged\review_templates\open_images_vehicle_attribute_crop_review_20260415.csv `
  --output-root .\data\curated\fiftyone_open_images_vehicle_color_reviewed `
  --manifest-path .\data\manifests\public\fiftyone-open-images-vehicle-color-reviewed.yaml `
  --dataset-name fiftyone-open-images-vehicle-color-reviewed `
  --task vehicle_color_classification `
  --copy-mode hardlink `
  --reviewer reviewer_01 `
  --review-status approved `
  --overwrite

.\.venv\Scripts\python.exe .\scripts\fiftyone_vehicle_dataset_pipeline.py export-reviewed-crops `
  --review-csv .\data\staged\review_templates\open_images_vehicle_attribute_crop_review_20260415.csv `
  --output-root .\data\curated\fiftyone_open_images_vehicle_make_model_reviewed `
  --manifest-path .\data\manifests\public\fiftyone-open-images-vehicle-make-model-reviewed.yaml `
  --dataset-name fiftyone-open-images-vehicle-make-model-reviewed `
  --task vehicle_make_model_classification `
  --copy-mode hardlink `
  --reviewer reviewer_01 `
  --review-status approved `
  --overwrite

.\.venv\Scripts\python.exe .\scripts\fiftyone_vehicle_dataset_pipeline.py export-reviewed-crops `
  --review-csv .\data\staged\review_templates\open_images_vehicle_attribute_crop_review_20260415.csv `
  --output-root .\data\curated\fiftyone_open_images_vehicle_year_reviewed `
  --manifest-path .\data\manifests\public\fiftyone-open-images-vehicle-year-reviewed.yaml `
  --dataset-name fiftyone-open-images-vehicle-year-reviewed `
  --task vehicle_year_classification `
  --copy-mode hardlink `
  --reviewer reviewer_01 `
  --review-status approved `
  --overwrite
```

For AI-assisted warm-start experiments before full human review, point
`--review-csv` at a consensus CSV, set `--review-status pending`, and pass
`--allow-unreviewed`. Do not use that pending manifest as a release gate or
production-quality benchmark until the rows have been reviewed and re-exported
with `--review-status approved`.

Train the exported crop datasets with `scripts/train_attribute_classifier.py`
and the existing attribute profiles:

- `configs/training/vehicle-color-classifier-efficientnet.yaml`
- `configs/training/vehicle-make-model-warmstart-v2.yaml` for warm starts
- `configs/training/vehicle-make-model-reviewed-seed-cpu.yaml` for small reviewed
  ImageFolder make/model seed runs on CPU
- `configs/training/vehicle-year-classifier.yaml`

Keep year labels conservative; year ranges or generation labels are preferable
when the exact model year is not visible.

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
