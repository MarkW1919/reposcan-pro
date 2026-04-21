# Prebuilt ALPR Integration Guide

RepoScan should treat prebuilt ALPR as a replaceable provider inside the existing
capture and review pipeline. The goal is to improve license plate detection and
OCR quickly without throwing away the dataset, review, and promotion work already
in the repo.

## Decision

The first integrated provider is **FastALPR**.

Why:

- local Python package, no hosted API required
- MIT licensed project
- uses ONNX Runtime backends
- includes out-of-the-box plate detection and OCR models
- matches the current RepoScan CSV/review pipeline with minimal changes

Primary source:

- FastALPR: https://github.com/ankandrew/fast-alpr
- FastALPR docs: https://ankandrew.github.io/fast-alpr/latest/

FastALPR does not solve vehicle year/make/model/color. It replaces only the
plate detection plus plate OCR portion of the mobile capture pipeline. Vehicle
attributes still flow through reviewed crops and VLM/classifier suggestions.

## Provider Ranking

1. **FastALPR**
   - Best no-subscription first integration.
   - Runs locally through Python and ONNX Runtime.
   - Integrated in `scripts/suggest_capture_detections.py` through
     `--plate-ocr-provider fast-alpr`.

2. **DTK LPR SDK + DTK VMMR SDK**
   - Best paid local candidate if license terms and pricing are acceptable.
   - DTK LPR supports Python, Windows, Linux, United States plates, and state
     detection for United States and Canada.
   - DTK VMMR adds vehicle type, color, view, make/model, generation, and model
     years for more than 2K models.
   - Sources:
     - https://www.dtksoft.com/lprsdk
     - https://www.dtksoft.com/vmmrsdk

3. **Plate Recognizer SDK perpetual license**
   - Best all-in-one commercial fallback, especially if make/model/color must be
     included in a supported SDK.
   - Requires contacting vendor for perpetual pricing.
   - Source: https://platerecognizer.com/pricing/

4. **Rekor Vehicle Recognition SDK**
   - Strong local commercial SDK with Python bindings.
   - Returns plate/state plus vehicle make, model, color, body type, year, and
     orientation.
   - Sales-driven license access and pricing make it a second paid quote, not the
     first implementation target.
   - Source: https://www.rekor.ai/intelligence-services/vehicle-recognition-sdk

5. **SimpleLPR**
   - Attractive one-time-license LPR SDK on paper.
   - Downgraded for RepoScan because the current Python quickstart lists North
     America as Canada-only and notes USA/Mexico are not currently supported.
   - Keep as a vendor-confirmation item only.
   - Sources:
     - https://www.warelogic.com/
     - https://www.warelogic.com/doc/simplelpr_python_quickstart_guide.htm

6. **NVIDIA TAO / DeepStream**
   - Strong NVIDIA edge stack with LPRNet, LPDNet, VehicleMakeNet, VehicleTypeNet,
     DashCamNet, and TrafficCamNet.
   - More infrastructure-heavy than RepoScan needs for the first integration.
   - VehicleMakeNet covers 20 makes, not exact year/model/trim.
   - Sources:
     - https://docs.nvidia.com/metropolis/TLT/tlt-user-guide/text/purpose_built_models/lprnet.html
     - https://docs.nvidia.com/tao/tao-toolkit-archive/tao-30-2202/text/model_zoo/cv_models/vehiclemakenet.html

7. **CodeProject.AI ALPR / ALPR Database**
   - Useful for experiments and dashboards.
   - Not selected as the RepoScan core because licensing and operational
     integration are less clean than a Python provider adapter.
   - Sources:
     - https://github.com/codeproject/CodeProject.AI-ALPR
     - https://www.alprdatabase.org/

## Current RepoScan Wiring

FastALPR is wired into:

- `scripts/suggest_capture_detections.py`
  - new `--plate-ocr-provider runtime|fast-alpr`
  - new FastALPR model/device options
  - emits standard `detection_review.csv` rows
  - writes `plate_detector_provider=fast-alpr` and `ocr_provider=fast-alpr`
  - preserves the existing plate OCR review app format

- `scripts/watch_mobile_capture_pipeline.py`
  - live mobile captures now default to `--plate-ocr-provider fast-alpr`
  - generated live queues keep the same output layout:
    - `metadata/detection_review.csv`
    - `metadata/plate_ocr_priority_review.csv`
    - `metadata/vehicle_attribute_review_no_runtime_attrs.csv`
    - `metadata/vehicle_attribute_priority_review_no_runtime_attrs.csv`

- `pyproject.toml`
  - new optional extra: `prebuilt-alpr`

The old runtime/ONNX plate path remains available as `--plate-ocr-provider runtime`
because it is still needed for deterministic tests, fixture validation, and future
promoted ONNX bundles. It is not the live mobile default anymore.

## Install

CPU/local install:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[prebuilt-alpr]"
```

NVIDIA GPU install after adding a CUDA-capable GPU:

```powershell
.\.venv\Scripts\python.exe -m pip install "fast-alpr[onnx-gpu]>=0.4,<0.5"
```

Use the CPU package first on the current HP machine. Move to `onnx-gpu` only after
an NVIDIA card and drivers are installed.

## One-Shot Detection Pass

```powershell
.\.venv\Scripts\python.exe .\scripts\suggest_capture_detections.py `
  --dataset-manifest .\data\manifests\staged\mobile-capture-live-intake-20260420.yaml `
  --output-root .\data\staged\mobile_capture_live_detection_review_20260420 `
  --vehicle-detector-provider ultralytics-coco `
  --ultralytics-model .\runtime\models\ultralytics\yolov8s.pt `
  --ultralytics-imgsz 960 `
  --detection-kind both `
  --plate-ocr-provider fast-alpr `
  --fast-alpr-detector-confidence 0.30 `
  --fast-alpr-ocr-device auto `
  --disable-preprocessing `
  --min-vehicle-confidence 0.10 `
  --overwrite
```

The first FastALPR run may download model files. After that, inference should use
the local model cache.

## Live Mobile Watcher

The watcher uses FastALPR by default:

```powershell
.\.venv\Scripts\python.exe .\scripts\watch_mobile_capture_pipeline.py `
  --interval-seconds 60 `
  --settle-seconds 20
```

Fallback to the previous runtime OCR path:

```powershell
.\.venv\Scripts\python.exe .\scripts\watch_mobile_capture_pipeline.py `
  --plate-ocr-provider runtime `
  --interval-seconds 60 `
  --settle-seconds 20
```

## Review And Promotion

FastALPR predictions are still suggestions. The promotion rule does not change:

1. ingest mobile captures
2. run vehicle detector and FastALPR
3. generate detection and OCR review queues
4. review plate crops in `launch_plate_ocr_review_app.py`
5. promote only accepted human-reviewed labels into curated training manifests
6. evaluate field accuracy before any promoted model replacement

Do not train plate OCR directly from unreviewed FastALPR output. That would copy
FastALPR mistakes into RepoScan's own model.

## Future Provider Interface

If FastALPR underperforms on Oklahoma mobile captures, keep the same CSV contract
and add another provider behind `--plate-ocr-provider`:

- `dtk-lpr`
- `plate-recognizer-sdk`
- `rekor-sdk`
- `simple-lpr` only if Warelogic confirms current USA support
- `nvidia-tao`

Each provider should output the same internal structures:

- `PlateDetection`
- `PlateCandidate`
- provider name in `plate_detector_provider`
- provider name in `ocr_provider`
- normal `detection_review.csv` rows

This keeps frontend review apps, dataset promotion, and model training unchanged.

## Acceptance Checklist

- `detection_review.csv` contains `detection_kind=plate` rows from `fast-alpr`
- plate rows include `ocr_text` when OCR succeeds
- `plate_detector_provider` is `fast-alpr`
- plate crops are written under `crops/plate/...`
- `ocr_provider` is `fast-alpr`
- `plate_ocr_priority_review.csv` groups OCR suggestions as before
- review apps open existing CSVs without schema changes
- runtime provider remains available for tests and fixtures
