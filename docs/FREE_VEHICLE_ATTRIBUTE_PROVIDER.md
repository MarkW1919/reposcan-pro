# Free Vehicle Attribute Provider

RepoScan's best current free local vehicle-attribute suggestion path is
`hf_vehicle_classifier`.

It uses the MIT-licensed Hugging Face model
`Jordo23/vehicle-classifier`, an EfficientNet-B4 classifier trained for vehicle
make, model, and year combinations.

Source:

- https://huggingface.co/Jordo23/vehicle-classifier

## What It Solves

- make suggestions
- model suggestions
- broad model-family suggestions for common Oklahoma vehicles
- year suggestions from the predicted class
- color suggestions from a local crop color heuristic

## What It Does Not Solve

This provider is not commercial-grade by itself. The model card reports about
50% top-1 accuracy and 75-80% top-5 accuracy on its benchmark. RepoScan therefore
uses it as a review assistant, not as training truth.

Do not promote rows from this provider unless they have been reviewed.

## Install

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[free-vehicle-attrs]"
```

## Label A Review CSV

```powershell
.\.venv\Scripts\python.exe .\scripts\label_vehicle_attribute_crops_with_vlm.py label-crops `
  --review-csv .\data\staged\mobile_capture_live_detection_review_20260421\metadata\vehicle_attribute_priority_review_no_runtime_attrs.csv `
  --output-csv .\data\staged\mobile_capture_live_detection_review_20260421\metadata\vehicle_attribute_priority_review_hf_free_suggestions.csv `
  --provider hf_vehicle_classifier `
  --hf-vehicle-batch-size 8 `
  --hf-vehicle-accept-confidence 0.80 `
  --hf-vehicle-device auto `
  --overwrite
```

The first run downloads the checkpoint into the local Hugging Face cache. Later
runs reuse the cached files.

## Live Watcher

The mobile capture watcher now applies this provider to the small vehicle
priority review queue by default:

```powershell
.\.venv\Scripts\python.exe .\scripts\watch_mobile_capture_pipeline.py `
  --interval-seconds 60 `
  --settle-seconds 20
```

The full vehicle crop queue remains available without runtime attribute
suggestions. This avoids rerunning a CPU-heavy classifier over every historical
crop on every upload cycle.

Disable free suggestions:

```powershell
.\.venv\Scripts\python.exe .\scripts\watch_mobile_capture_pipeline.py `
  --vehicle-attribute-suggestion-provider disabled
```

Use the older light CLIP fallback:

```powershell
.\.venv\Scripts\python.exe .\scripts\watch_mobile_capture_pipeline.py `
  --vehicle-attribute-suggestion-provider clip_oklahoma
```
