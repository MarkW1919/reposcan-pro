# DATASET_INTAKE_WORKFLOW.md

RepoScan Pro uses manifest-driven dataset intake so external datasets, staged field captures, and synthetic support data can be reviewed through one path.

## 1. Create The Local Workspace

```powershell
.\.venv\Scripts\python.exe .\scripts\init_dataset_workspace.py --root .\data
```

This creates:

```text
data/
|-- raw/
|-- staged/
|-- curated/
|-- eval/
`-- manifests/
```

## 2. Register Or Write A Dataset Manifest

Use one of these approaches:

- write a new manifest by hand under `data/manifests/`
- start from the example manifests in `configs/datasets/`
- import legacy Seen-It-First sources into local manifests with:

```powershell
.\.venv\Scripts\python.exe .\scripts\import_legacy_training_sources.py --output-dir .\data\manifests\legacy
```

## 3. Validate Intake

```powershell
.\.venv\Scripts\python.exe .\scripts\validate_training_dataset_manifest.py --manifest .\configs\datasets\example-capture-intake.yaml
```

Add `--verify-files` when the manifest points at real local media and you want existence checks too.

## 4. Plan Session-Aware Splits

For capture-based manifests with asset-level records:

```powershell
.\.venv\Scripts\python.exe .\scripts\plan_training_dataset_split.py `
  --manifest .\configs\datasets\example-capture-intake.yaml `
  --output .\data\manifests\example-capture-split.yaml `
  --field-eval-tag long_range `
  --field-eval-tag low_light
```

This keeps capture sessions together and can reserve dedicated `field_eval` samples when assets are tagged for benchmark use.

## Mobile Capture Intake

Foreground phone captures collected through the separate mobile PWA can be
imported into RepoScan as a pending `generic_capture` intake bundle:

```powershell
.\.venv\Scripts\python.exe .\scripts\import_mobile_capture_intake.py `
  --capture-root C:\ReposcanCaptureData\incoming `
  --output-root .\data\staged\mobile_capture_intake_20260418 `
  --manifest-path .\data\manifests\staged\mobile-capture-intake-20260418.yaml `
  --review-csv .\data\staged\mobile_capture_intake_20260418\metadata\review_index.csv `
  --dataset-name mobile-capture-intake-20260418 `
  --state-path .\runtime\capture_import_state\mobile_capture_import_state.json `
  --task vehicle_detection `
  --copy-mode hardlink `
  --overwrite-manifest
```

The importer:

- preserves raw uploaded images and JSON sidecars under the staged output root
- rewrites a pending `generic_capture` manifest from all imported assets
- emits `metadata/review_index.csv` for review workflows
- tracks previously-imported source metadata files in a small state file so reruns
  only ingest new captures

## Detection Suggestion Queue

Once a mobile-capture intake bundle exists, generate a review-ready detection queue.
For a stronger vehicle bootstrap, use the Ultralytics COCO detector. For quick local
passes `yolov8n.pt` is fine; for better field recall use `yolov8s.pt` with a larger
inference size. Use FastALPR for the local prebuilt plate detection/OCR path:

```powershell
.\.venv\Scripts\python.exe .\scripts\suggest_capture_detections.py `
  --dataset-manifest .\data\manifests\staged\mobile-capture-intake-20260418.yaml `
  --output-root .\data\staged\mobile_capture_detection_review_20260419 `
  --vehicle-detector-provider ultralytics-coco `
  --ultralytics-model yolov8s.pt `
  --ultralytics-imgsz 960 `
  --detection-kind both `
  --plate-ocr-provider fast-alpr `
  --overwrite
```

This generates:

- `metadata/detection_review.csv` with one row per suggested vehicle / plate box
- `metadata/frame_summary.csv` with per-frame detection counts and latency
- `metadata/inference_candidates.jsonl` with full per-frame inference payloads
- `crops/vehicle/...` and `crops/plate/...` for fast review

For deterministic local smoke tests, point `--model-config` at
`.\configs\models\local-demo-runtime.yaml` and leave the detector provider at the default `runtime`.
If FastALPR is not installed, install the optional local ALPR extra first:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[prebuilt-alpr]"
```

The live mobile watcher defaults to `--plate-ocr-provider fast-alpr`; pass
`--plate-ocr-provider runtime` only when you intentionally want the old fixture
plate detector/OCR path for deterministic smoke tests.

Review the generated boxes with the local detection reviewer:

```powershell
.\.venv\Scripts\python.exe .\scripts\launch_capture_detection_review_app.py `
  --review-csv .\data\staged\mobile_capture_detection_review_20260419\metadata\detection_review.csv `
  --port 7861
```

The reviewer shows the full frame with the current box, a crop preview, and lets you:

- accept / reject the detection
- edit `class_label`
- correct `bbox_x`, `bbox_y`, `bbox_w`, and `bbox_h`
- save the row and rewrite the crop on disk

## Vehicle Attribute Bootstrap

Convert accepted or pending vehicle detections into the crop-review format used by the
vehicle attribute labelers:

```powershell
.\.venv\Scripts\python.exe .\scripts\prepare_mobile_capture_attribute_review.py `
  --detection-review-csv .\data\staged\mobile_capture_detection_review_20260419\metadata\detection_review.csv `
  --output-csv .\data\staged\mobile_capture_detection_review_20260419\metadata\vehicle_attribute_review.csv `
  --drop-runtime-attribute-suggestions `
  --overwrite
```

Use `--drop-runtime-attribute-suggestions` for mobile field captures unless the
runtime classifier has already been validated on similar captures. The current
local ONNX/runtime attribute fixture is useful for plumbing only and should not
drive make/model review decisions.

Then run a pretrained attribute suggester over those crops. Highest-accuracy
OpenAI path:

```powershell
.\.venv\Scripts\python.exe .\scripts\label_vehicle_attribute_crops_with_vlm.py label-crops `
  --review-csv .\data\staged\mobile_capture_detection_review_20260419\metadata\vehicle_attribute_review.csv `
  --output-csv .\data\staged\mobile_capture_detection_review_20260419\metadata\vehicle_attribute_openai_suggestions.csv `
  --provider openai `
  --model gpt-4o `
  --overwrite
```

Use `gpt-4o` when accuracy matters more than labeling cost. Use
`gpt-4o-mini` for lower-cost bulk triage, then reserve `gpt-4o` for
ambiguous crops or final pre-review passes.

Best free local path:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[free-vehicle-attrs]"

.\.venv\Scripts\python.exe .\scripts\label_vehicle_attribute_crops_with_vlm.py label-crops `
  --review-csv .\data\staged\mobile_capture_detection_review_20260419\metadata\vehicle_attribute_review.csv `
  --output-csv .\data\staged\mobile_capture_detection_review_20260419\metadata\vehicle_attribute_hf_free_suggestions.csv `
  --provider hf_vehicle_classifier `
  --overwrite
```

This uses the MIT-licensed `Jordo23/vehicle-classifier` EfficientNet-B4 checkpoint
from Hugging Face for make/model/year suggestions and a local color heuristic for
color suggestions. Treat these as review accelerators only; the model reports about
50% top-1 and 75-80% top-5 accuracy on its source benchmark, so accepted training
labels still require review.

Stronger pretrained options when available:

- `--provider qwen2_5_vl` for local / Colab GPU batch labeling
- `--provider openai --model gpt-4o` when an `OPENAI_API_KEY` with quota is available locally
- `--provider clip_oklahoma` for a very light CPU fallback when the HF classifier is too slow

Both should still be treated as suggestion generators, not ground truth.

## Plate OCR Review

Review plate OCR rows with a dedicated local app instead of the generic box editor:

```powershell
.\.venv\Scripts\python.exe .\scripts\launch_plate_ocr_review_app.py `
  --review-csv .\data\staged\mobile_capture_detection_review_20260419\metadata\detection_review.csv `
  --port 7862
```

The plate reviewer filters to `detection_kind=plate`, lets you edit OCR text and box
coordinates, and writes the corrected crop back to disk on save.

When a driving session generates many near-duplicate rows, reduce the queue before
reviewing it:

```powershell
.\.venv\Scripts\python.exe .\scripts\prepare_mobile_capture_priority_review.py plate-ocr `
  --input-csv .\data\staged\mobile_capture_detection_review_20260419\metadata\detection_review.csv `
  --output-csv .\data\staged\mobile_capture_detection_review_20260419\metadata\plate_ocr_priority_review.csv `
  --max-per-group 5 `
  --overwrite
```

This groups rows by OCR text and keeps the strongest representatives first.

For vehicle attributes, build a reduced priority queue from the attribute suggestion CSV:

```powershell
.\.venv\Scripts\python.exe .\scripts\prepare_mobile_capture_priority_review.py vehicle-attributes `
  --input-csv .\data\staged\mobile_capture_detection_review_20260419\metadata\vehicle_attribute_hf_free_suggestions.csv `
  --output-csv .\data\staged\mobile_capture_detection_review_20260419\metadata\vehicle_attribute_priority_review.csv `
  --max-per-group 5 `
  --prefer-accept-suggestions `
  --overwrite
```

This groups rows by VLM make/model suggestion or body type and keeps a small set of
representative crops for each group.

## 5. Promote Into Curated Training Sets

- `raw/` keeps untouched drops
- `staged/` is for reviewed but not yet finalized data
- `curated/` is for training-ready datasets with accepted labels
- `eval/` is for protected holdouts and field-eval sets

For plate-detection capture sets:

1. export a label-review index with `scripts/export_detection_label_index.py`
2. place YOLO labels under a mirrored labels root
3. promote the reviewed labels with `scripts/promote_detection_dataset.py`

Do not move data into a training plan until the manifest passes provenance, license, and annotation review.

## Legacy Source Notes

The old `Seen-It-First` assets on this machine are worth using through manifests, not by importing the old runtime code wholesale.

Today the most reusable legacy sources are:

- Stanford Cars as a vehicle make/model warm-start dataset
- Oklahoma staged raw captures for future plate-detection labeling
- Oklahoma synthetic OCR support renders for augmentation and pretraining support

## Related Documents

- [Datasets](DATASETS.md)
- [Annotation Standards](ANNOTATION_STANDARDS.md)
- [Detection Dataset Curation](DETECTION_DATASET_CURATION.md)
- [Training](TRAINING.md)
- [Prebuilt ALPR Integration Guide](PREBUILT_ALPR_INTEGRATION_GUIDE.md)
