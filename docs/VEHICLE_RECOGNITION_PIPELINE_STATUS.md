# VEHICLE_RECOGNITION_PIPELINE_STATUS.md

End-to-end status of the LPR + YMM (year/make/model) + color recognition
pipeline as of 2026-05-21. All training is complete and exported; remaining
work is production wiring and the schema design conversation for multi-head
classifier dispatch.

## What is trained, exported, and ready

| Stage | Run | Holdout | ONNX path |
|---|---|---:|---|
| **Plate OCR** | `lpr_ocr_openalpr_support_continue_20260503_0002` | 97.37% exact-match | `runtime/training/.../inference_export/` (Paddle inference format) |
| **Make/Model primary** | `vehicle-make-model-canonical-v5_20260519_run1` | **86.33%** (40 classes) | `runtime/training/.../exports/model.onnx` |
| Make/Model (prev) | `vehicle-make-model-canonical-v4_20260510_run1` | 88.76% (30 classes) | superseded by v5 |
| **Chevy SUV re-rank** | `vehicle-rerank-gm-fullsize-suv-v1_20260512_run1` | **83.82%** (3 classes) | exports/model.onnx |
| **Jeep re-rank** | `vehicle-rerank-jeep-realonly-v1_20260514_run1` | **93.75%** (2 classes) | exports/model.onnx |
| **Year-bucket** | `vehicle-year-bucket-canonical-v1_20260509_run1` | **67.73%** (5 buckets) | exports/model.onnx |
| **Color (synth)** | `vehicle-color-canonical-v1_20260512_run1` | 98.79% val (synthetic only) | exports/model.onnx |

### Canonical-v5 (current primary)

v5 expands the make/model taxonomy from 30 → 40 classes, adding
cadillac_escalade, lincoln_navigator, honda_pilot, ford_escape,
hyundai_elantra, subaru_outback, kia_sportage, hyundai_santa_fe,
chevrolet_malibu, and volkswagen_jetta. Best val 89.64% (epoch 15),
holdout **86.33%**, early-stopped at epoch 25.

The aggregate dip from v4's 88.76% is the expected cost of 10 additional
(harder) classes, **not** a regression: no carried-forward class with a
reliable holdout sample (n≥24) dropped more than ~8pp, and several
improved (toyota_corolla 37.5%→75.0%, jeep_grand_cherokee 25.0%→37.5%,
gmc_sierra 93.3%→97.8%). New-class mean accuracy is 75.5%; 7 of 10 land
≥75% (ford_escape and hyundai_elantra at 100%), with 3 soft classes —
see weak-classes section below.

- Loadable through the real config path via
  `configs/models/local-onnx-makemodel-v5.yaml` (classifier-integration
  stack: real v5 classifier on fixture detector/plate/OCR). All four
  stages report `ready=True` under `validate_model_stack`; the
  logits→make/model mapping was confirmed correct for all 40 indices.
- Per-class holdout report:
  `runtime/training/vehicle-make-model-canonical-v5_20260519_run1/per_class_holdout_report.json`
  (regenerate with `scripts/evaluate_make_model_per_class_holdout.py`).

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

> **v5 re-rank compatibility caveat.** The Jeep and GM-SUV re-rank heads
> were trained against v4's 30-class confusion structure. v5 shifts that
> structure: jeep_grand_cherokee's dominant v5 confusion is now
> **hyundai_santa_fe** (a new class the Jeep head never saw), and the new
> chevrolet_malibu confuses with nissan_altima. The existing re-rank heads
> still help the GM full-size SUV cluster (Suburban/Tahoe/Yukon/Escalade
> all carried forward), but the dispatch table and the Jeep head must be
> re-validated against the v5 taxonomy before claiming the ~91-92% figure
> for v5. Treat that number as v4-era until re-measured.

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

**RESOLVED (2026-05-21): Option B chosen.** Contracts slice landed:
`DeferredRecognitionConfig` + `RerankHeadConfig` added to
[packages/contracts/src/reposcan_contracts/config/model.py](../packages/contracts/src/reposcan_contracts/config/model.py)
as an optional `deferred_recognition` block on `ModelStackConfig`. It
holds the make_model primary, a list of re-rank heads (each with
`trigger_classes` → specialist classifier), and optional year/color
heads. A model-validator rejects ambiguous dispatch (one primary class
claimed by two heads) and empty trigger lists. The real-time
`classifier` slot is untouched, so existing single-head configs still
validate. Schema is locked by tests in
[tests/contracts/test_config_loaders.py](../tests/contracts/test_config_loaders.py)
and exercised by a real wiring config,
`configs/models/canonical-v5-deferred.yaml`, that composes v5 +
Jeep/GM-SUV re-rank + year + color.

Remaining for this item (next slice): inference-service support — a
deferred-recognition adapter/runner that executes make_model, applies
the re-rank dispatch, and attaches year/color, plus
`validate_model_stack` coverage for the deferred stages. The contracts
foundation above unblocks that work.

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

### 3. Remaining weak make/model classes (v5)

v5 fixed two of v4's three weak classes (toyota_corolla 37.5%→75.0%,
toyota_4runner 62.5%→75.0%). dodge_durango stays soft (20.0%, n=5 —
noisy). The remaining sub-70% classes on the v5 holdout are below.
**All sit in dense fine-grained-confusion neighborhoods, not data-volume
holes** (e.g. chevrolet_malibu has 196 train images yet scores 42.9%,
while hyundai_elantra scores 100% on only 64). Holdout sets for these
are tiny (n=5–8), so per-class percentages are noisy.

- **chevrolet_malibu** (42.9%, 3/7 holdout) — NEW in v5. Confuses with
  nissan_altima. Midsize-sedan cluster.
- **honda_pilot** (50.0%, 3/6 holdout) — NEW in v5. Confuses across
  midsize SUVs.
- **volkswagen_jetta** (50.0%, 4/8 holdout) — NEW in v5. Thin train data
  (64) and midsize-sedan confusion.
- **dodge_durango** (20.0%, 1/5 holdout) — carried forward, confuses with
  ram_pickup. Noisy (n=5).
- **gmc_yukon** (50.0%, 4/8 holdout) — carried forward, confuses with
  cadillac_escalade (a new v5 class). Covered by the GM full-size SUV
  re-rank head once the dispatch is re-validated for v5.

The structurally-correct fix for the malibu/jetta sedan cluster is a
**midsize-sedan re-rank head** (malibu / jetta / altima / camry / sonata
/ corolla), mirroring the proven Jeep and GM-SUV re-rank pattern — not a
full retrain (these are confusion problems, not volume problems). This
does not block deployment but is the highest-leverage next accuracy step.

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
