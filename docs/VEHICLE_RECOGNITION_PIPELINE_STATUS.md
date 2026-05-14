# VEHICLE_RECOGNITION_PIPELINE_STATUS.md

End-to-end status of the LPR + YMM (year/make/model) + color recognition
pipeline as of 2026-05-14. All training is complete and exported; remaining
work is production wiring and the schema design conversation for multi-head
classifier dispatch.

## What is trained, exported, and ready

| Stage | Run | Holdout | ONNX path |
|---|---|---:|---|
| **Plate OCR** | `lpr_ocr_openalpr_support_continue_20260503_0002` | 97.37% exact-match | `runtime/training/.../inference_export/` (Paddle inference format) |
| **Make/Model primary** | `vehicle-make-model-canonical-v4_20260510_run1` | **88.76%** (30 classes) | `runtime/training/.../exports/model.onnx` |
| **Chevy SUV re-rank** | `vehicle-rerank-gm-fullsize-suv-v1_20260512_run1` | **83.82%** (3 classes) | exports/model.onnx |
| **Jeep re-rank** | `vehicle-rerank-jeep-realonly-v1_20260514_run1` | **93.75%** (2 classes) | exports/model.onnx |
| **Year-bucket** | `vehicle-year-bucket-canonical-v1_20260509_run1` | **67.73%** (5 buckets) | exports/model.onnx |
| **Color (synth)** | `vehicle-color-canonical-v1_20260512_run1` | 98.79% val (synthetic only) | exports/model.onnx |

All ONNX outputs are EfficientNet-B0 at 260×260 input, dynamic batch,
fp32, ImageNet normalization mean/std. They share preprocessing so a
single cropped vehicle image can be routed through all four heads.

## Effective accuracy with re-rank dispatch

Deferred-pipeline make/model dispatch policy: run canonical-v4 first;
when v4 predicts one of the configured cluster classes, run the matching
re-rank head and take its prediction.

| Class | v4 alone | + Re-rank | Δ |
|---|---:|---:|---:|
| chevrolet_suburban | 58.3% | **75.0%** | +16.7pp |
| gmc_yukon | 62.5% | **87.5%** | +25.0pp |
| **jeep_grand_cherokee** | 25.0% | **87.5%** | **+62.5pp** |
| chevrolet_tahoe | 86.1% | 83.3% | −2.8pp |
| jeep_wrangler | 100% | 100% | 0 |

The other 25 classes inherit v4's accuracy directly (no re-rank applied).
Estimated overall holdout with re-rank dispatch: **~91-92%**, up from
v4's 88.76%.

## Hardware mapping

Per the dual-camera scan workflow already wired in
`configs/deployments/jetson-orin-nano-super.yaml`:

- **IMX585 LPR primary** runs the real-time pipeline (vehicle/plate
  detect + PaddleOCR) inside the scan radius.
- **IMX678 wide context** captures frames in parallel; after the scan
  radius is exited, the deferred recognition pipeline (canonical-v4
  + re-rank + year + color) runs against those stored frames and
  attaches the enrichment to the LPR detections recorded during the
  scan.

This means make/model/color/year inference does NOT need to fit inside
the 250 ms p95 real-time latency budget — they run during the
post-scan window when only one camera (or no camera) is generating
new frames.

## Open items before production deployment

### 1. Multi-head classifier wiring (schema decision required)

The existing `ClassifierModelConfig`
([packages/contracts/src/reposcan_contracts/config/model.py:57](../packages/contracts/src/reposcan_contracts/config/model.py#L57))
treats classifier as a single model with `color_labels` and `make_labels`
fields. To wire the trained stack as-is, we need to either:

- **Option A**: Extend `ClassifierModelConfig` with optional
  `make_model_classifier`, `year_classifier`, `color_classifier`, and
  `rerank_classifiers` blocks. Backwards-compatible (existing single-head
  configs still validate), but touches the inference service (adapters,
  service, promotion, release_registry, deployment_validation).
- **Option B**: Define a parallel `DeferredRecognitionConfig` block on
  `ModelStackConfig` so the LPR classifier slot stays single-head and the
  deferred pipeline gets its own config root. Cleaner separation between
  real-time and deferred stacks.
- **Option C**: Bundle the trained heads into a SINGLE compound ONNX
  that emits make_model + color + year + cluster_rerank from one forward
  pass. More work upfront but matches the existing single-classifier slot
  shape.

Recommend **Option B** because it mirrors the dual-camera architecture
(real-time and deferred are already separate pipelines).

### 2. Color head real-data validation

The color classifier is trained 100% on Synset-Boulevard synthetic
imagery (98.79% val on the synthetic carve-out). A real-image color
holdout does not exist yet. Two paths:

- VLM auto-labeling on a sample of canonical-v4 holdout assets (~200
  images) to produce a real validation set.
- Manual labeling gate on the same sample by a reviewer.

Either path produces a real-data accuracy number; until then, color
head is review_status: pending and should not be promoted as a final
attribute.

### 3. Remaining weak make/model classes

Three classes are below 70% on holdout and could use a future canonical-v5:

- **toyota_corolla** (37.5%, 3/8 holdout). Has 64 real train samples
  total. Needs more real Corolla photos — Wikimedia coverage was thin.
- **dodge_durango** (40.0%, 2/5 holdout). Only 5 holdout samples; the
  number is noisy. Could re-rank against Ram-cluster but train data
  is also thin (190 total, mostly synthetic).
- **toyota_4runner** (62.5%, 5/8 holdout). Confused with Wrangler and
  Expedition. A tall-boxy-SUV re-rank (4Runner / Wrangler / Expedition)
  is the textbook fix.

These don't block deployment but are next-cycle improvement targets.

### 4. Field validation

Per ADR-028 and [docs/FIELD_EVAL_QUALIFICATION.md](FIELD_EVAL_QUALIFICATION.md),
holdout numbers are runtime evidence, not field-acceptance proof. A
field eval pass on real Oklahoma vehicles in long-range / low-light /
glare / IR-assisted scenes is the final acceptance gate before promotion.

## Recommended next step

Pick one of:

1. **Extend `ClassifierModelConfig` schema (Option A or B above)** and
   wire the trained heads into a `configs/models/canonical-v4-deferred.yaml`
   model stack. ~1 day of careful engineering plus test updates.
2. **Real-image color labeling pass** so the color head can be
   validated and promoted. ~1 day.
3. **Field validation rig** — capture the FIELD_CAPTURE_KIT scene matrix
   and run the assembled deferred pipeline against it. Multi-day field
   work.
4. **Canonical-v5 with real-data scale-up for toyota_corolla,
   dodge_durango, toyota_4runner**. ~2 days acquisition + training.

The training work in this iteration is complete. The remaining work is
either engineering (schema + wiring) or field operations (validation
rig), neither of which is best executed autonomously without explicit
direction.

## Related docs

- [PUBLIC_VEHICLE_DATASET_SOURCES.md](PUBLIC_VEHICLE_DATASET_SOURCES.md)
- [DEPLOYMENT.md](DEPLOYMENT.md)
- [CAMERA_AND_IMAGING.md](CAMERA_AND_IMAGING.md)
- [MODELS.md](MODELS.md)
- [MODEL_PROMOTION_WORKFLOW.md](MODEL_PROMOTION_WORKFLOW.md)
- [FIELD_EVAL_QUALIFICATION.md](FIELD_EVAL_QUALIFICATION.md)
