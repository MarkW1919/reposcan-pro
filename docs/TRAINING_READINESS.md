# TRAINING_READINESS.md — what we can train now, and the path to commercial-grade

A grounded status of the training program as of 2026-06-11: what is launch-ready
today, what is blocked and why, and the exact data targets that separate a
baseline from a system that beats a commercial pro ALPR. Pairs with
[VEHICLE_RECOGNITION_PIPELINE_STATUS.md](VEHICLE_RECOGNITION_PIPELINE_STATUS.md)
(accuracy) and [MODEL_INVENTORY.md](MODEL_INVENTORY.md) (artifacts).

## The binding constraint: GPU

The current dev box is **CPU-only** (`torch ... +cpu`, `cuda.is_available()=False`).
That is why every run to date is named `*_cpu_smoke`. Training is not blocked on
data or code — it is blocked on a CUDA GPU. On CPU a real detector run takes days
and cannot iterate; on a single RTX-class GPU it is hours.

**Recommended training box:** RTX 4090 24 GB (or RTX 6000 Ada 48 GB for larger
batches), 64–128 GB RAM, fast NVMe. Buy this first — it converts the data we
already have into accuracy.

## What is launch-ready NOW (warmstart) — one command on a GPU

The vehicle detector is the biggest single detection gap (today it is a 1-class
"smoke" model). A proper baseline is **ready to train** — verified 2026-06-11 via
the readiness auditor (warmstart gate = Ready) and a real `--dry-run` prep:

- Profile: [`configs/training/vehicle-detector-open-images-gpu-warmstart.yaml`](../configs/training/vehicle-detector-open-images-gpu-warmstart.yaml)
  (YOLO11s, 640 px, 50 epochs, fp16, motion/defocus-blur + noise augmentation —
  aligned to the long-range / low-light priority).
- Data: `data/manifests/public/fiftyone-open-images-vehicle-detection-warmstart.yaml`
  (3,000 images, split 2,400 / 300 / 300).

```bash
# On a GPU box — prepare + run (swap --dry-run for --execute):
python scripts/train_detection_model.py \
    --profile configs/training/vehicle-detector-open-images-gpu-warmstart.yaml \
    --dataset-manifest data/manifests/public/fiftyone-open-images-vehicle-detection-warmstart.yaml \
    --run-name vehicle-detector-warmstart-v1 --allow-pending --execute
```

The workflow auto-exports ONNX (`opset=17 dynamic=True`) into the run's
`weights/`, which drops straight into a model stack config (mirror
[`local-onnx-full-real.yaml`](../configs/models/local-onnx-full-real.yaml), swap the
`vehicle_detector.artifact_path`). After training, re-run
`python scripts/inventory_trained_models.py` to catalog the new weights.

Other heads with data already curated (train on the same GPU box): make/model
rebalance (11.5k images), color real-image validation (1.4k), year-bucket.

## Blocked, and why

- **Our 97% PaddleOCR → ONNX export.** The trained reader
  (`lpr_ocr_openalpr_support_continue_20260503_0002`, 97.37% exact-match) is in
  Paddle inference format. Converting it to ONNX (to supersede the interim global
  reader) requires `paddle2onnx`, whose prebuilt extension **fails to load on this
  Windows box** (DLL import error vs. Paddle 3.3.1). Do this conversion on
  **Linux or the Jetson** where the PaddleOCR toolchain is supported:
  `paddle2onnx --model_dir <inference_export> --model_filename inference.json
  --params_filename inference.pdiparams --save_file en_ppocrv4_rec.onnx
  --opset_version 14`, then write a CTC-greedy-decode OCR adapter (the model is
  `en_PP-OCRv4_mobile_rec`, BGR `3x48x320`, blank at index 0). Until then the
  pipeline uses the `fast_alpr` global reader (verified working on benchmark
  plates).
- **TensorRT engines.** Build on the Orin (`scripts/build_tensorrt_engines.py`,
  see [JETSON_DEPLOYMENT.md](JETSON_DEPLOYMENT.md)).

## The path to beating a commercial system (data targets)

The readiness auditor encodes the **Oklahoma-commercial** gate. Audited against
the current detection dataset (2026-06-11), here is the gap — and it maps exactly
to the IR multi-camera rig being acquired (every shortfall below is *field
capture*, not code):

| Requirement | Commercial gate | Have now |
|---|---:|---:|
| Total samples | 50,000 | 3,000 |
| Train / val / holdout | 35,000 / 5,000 / 7,500 | 2,400 / 300 / 300 |
| Capture sessions | 75 | 3 |
| **Low-light assets** | **5,000** | **0** |
| **Long-range assets** | **5,000** | **0** |
| Pickups | 10,000 | 0 (untagged) |
| SUV / crossover | 12,000 | 0 (untagged) |
| Passenger car | 8,000 | 0 (untagged) |
| Van / minivan | 1,500 | 0 (untagged) |
| make_model: Ford F-series | 2,500 | 0 |
| make_model: Chevrolet Silverado | 2,000 | 0 |
| make_model: RAM pickup | 1,500 | 0 |
| make_model: GMC Sierra | 1,000 | 0 |
| make_model: Toyota Tacoma | 750 | 0 |
| make_model: Tahoe/Suburban | 750 | 0 |

Plus dataset review/approval and a resolved license tier. Audit any dataset
yourself with:

```bash
python scripts/audit_training_dataset_readiness.py \
    --dataset-manifest <manifest>.yaml --level oklahoma-commercial
```

**The takeaway:** the model architecture and training pipeline are ready; the
remaining accuracy comes from **field data captured with the IR / global-shutter
/ long-range rig** — the low-light and long-range buckets (10k assets combined)
are the two priorities that 0 data exists for today and that no public dataset
fills. That capture program, run on the recommended camera hardware, is what
takes this from baseline to ahead-of-commercial.

## Recommended sequence

1. Acquire the GPU box → train the detector baseline now (data is ready).
2. Acquire the IR multi-camera rig → capture the low-light + long-range +
   Oklahoma-vehicle field data the commercial gate requires.
3. Convert the 97% OCR to ONNX (on Linux/Jetson) to replace the global reader.
4. Field-tune detector + plate + OCR on captured data; build TensorRT engines on
   the Orin; pass the field-eval gate
   ([FIELD_EVAL_QUALIFICATION.md](FIELD_EVAL_QUALIFICATION.md)).
