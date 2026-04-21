# RepoScan Core Model Strategy

RepoScan should use a pretrained model stack, not one monolithic model. The system
needs different strengths for vehicle/plate localization, OCR, make/model/color
classification, and field-deployment latency. Keeping those stages modular lets us
upgrade one weak stage without destabilizing the whole product.

## Recommended Architecture

1. **Vehicle and plate localization**
   - Near-term core: Ultralytics YOLO, because the repo already has YOLO training,
     detection review, ONNX export, and TensorRT packaging workflows.
   - License-clean research track: RT-DETRv2 or D-FINE from Hugging Face. Both have
     Apache-2.0 pretrained COCO checkpoints and are strong candidates if we need to
     avoid AGPL constraints.

2. **Plate OCR**
   - Core OCR family: PaddleOCR PP-OCR, with PP-OCRv5 as the target for new OCR
     experiments and PP-OCRv4 as the proven fallback already referenced by the repo.
   - Train/fine-tune OCR on real Oklahoma plate crops plus capped synthetic support.
   - Promote by exact plate match, character accuracy, and false-alert rate, not just
     validation loss.

3. **Vehicle attributes**
   - Use a high-accuracy VLM as a suggestion generator, not as ground truth. The
     current preferred hosted path is OpenAI `gpt-4o` once API quota is available.
   - Train the deployed edge attribute model separately from reviewed crops. Start
     with model-family, body type, and color. Treat exact year as a later-stage goal;
     for now, exact year should be human-reviewed or bucketed into year ranges.
   - Candidate backbones: DINOv3/timm, ConvNeXt, or CLIP/Stanford-Cars-derived
     encoders. Pick based on measured validation accuracy on our Oklahoma holdout,
     not model-card claims.

4. **Tracking and multi-frame fusion**
   - Run tracking across video/capture bursts so the system can merge repeated views
     of the same vehicle/plate.
   - OCR should use multi-frame consensus. One blurry crop should not drive a hit
     when five neighboring frames disagree.

## Pretrained Candidates To Evaluate

| Stage | Candidate | Why it matters | Risk / note |
| --- | --- | --- | --- |
| Vehicle detector | YOLO11 / current YOLOv8s path | Fast, integrated, exportable to ONNX/TensorRT, supports tracking workflows | Ultralytics open-source licensing is AGPL unless an enterprise license is used |
| Vehicle detector | `PekingU/rtdetr_v2_r18vd` or `PekingU/rtdetr_v2_r50vd` | Apache-2.0, real-time transformer detector, strong HF training path | Needs repo integration work before it can replace YOLO in deployment |
| Vehicle detector | `ustc-community/dfine-small-coco` or `dfine-large-coco` | Apache-2.0, efficient modern object detector, good fine-tuning candidate | Needs repo integration and export validation |
| Plate detector | YOLO11 license-plate detector checkpoints | Good bootstrap option for experiments and review queue generation | Common HF plate detector checkpoints are AGPL; use for experiments until licensing is settled |
| Plate OCR | PaddleOCR PP-OCRv5 mobile/server | Strong open OCR family with deployment and training support | PP-OCRv5 can be slower than PP-OCRv4; benchmark both on target hardware |
| Attribute classifier | DINOv3/timm or ConvNeXt | Strong visual backbone for make/model-family/color after we have labels | Needs a reviewed, balanced dataset; exact year is not reliable from small crops |
| VLM labeler | OpenAI `gpt-4o` | Best current hosted suggestion path for difficult vehicle crops | Requires API quota; output is still pending review, not training truth |

## Continual Learning Loop

Do not let the deployed model train directly from its own unreviewed predictions.
That creates feedback loops and will make mistakes permanent. Use this loop instead:

1. Capture raw phone/edge images into immutable storage.
2. Auto-ingest new captures into a live staged dataset.
3. Run detector/OCR/attribute suggestion pipelines.
4. Deduplicate near-identical frames and group by track/session.
5. Send uncertain, high-value, and representative crops to review.
6. Promote only human-approved labels into curated datasets.
7. Keep train/validation/field-eval splits session-aware so frames from the same
   drive do not leak across splits.
8. Train candidate models on curated data.
9. Evaluate against protected Oklahoma field holdouts:
   - vehicle/plate detector mAP and recall
   - plate exact-match and character accuracy
   - false-alert rate
   - make/model-family top-1 and top-3 accuracy
   - color accuracy
   - latency on target hardware
10. Promote only when the candidate improves quality without breaking latency or
    false-positive constraints.

## Practical Phases

### Phase 1: Stabilize The Current Pipeline

- Keep Ultralytics for detection because it is already wired into the repo.
- Keep runtime/ONNX make-model suggestions disabled until validated.
- Use the mobile capture watcher to build fresh pending review queues.
- Use OpenAI `gpt-4o` for attribute suggestions once quota is active.

### Phase 2: Build RepoScan's First Real Field Models

- Fine-tune a plate detector on reviewed RepoScan plate boxes.
- Fine-tune OCR on real Oklahoma plate crops plus capped synthetic support.
- Train attribute classifiers for body type, color, and model family.
- Export promoted artifacts to ONNX/TensorRT bundles already supported by the repo.

### Phase 3: Evaluate Apache-2.0 Detector Alternatives

- Train/evaluate RT-DETRv2 R18/R50 and D-FINE Small/Large on the same curated
  RepoScan detection data.
- Compare accuracy, latency, export behavior, and licensing.
- If one beats YOLO enough to justify the work, add it as a promoted model family.

### Phase 4: Continual Improvement

- Retrain on a cadence, not continuously:
  - nightly: ingest, crop, dedupe, queue reviews
  - weekly: train candidates if enough new approved labels exist
  - monthly or milestone-based: promote only after field-eval pass
- Preserve hard examples: glare, low light, motion blur, partial plates, small
  distant vehicles, dark pickup trucks, white/silver work trucks, and Oklahoma
  county/tribal/specialty plate variants.

## Decision

The best immediate path is:

1. **Use YOLO as the operational detector core now**, because it is already working
   in the RepoScan pipeline.
2. **Add a license-clean RT-DETRv2/D-FINE evaluation track**, so we are not trapped
   if AGPL/enterprise licensing becomes a problem.
3. **Use PaddleOCR PP-OCR as the OCR core**, with PP-OCRv5 as the next benchmark and
   PP-OCRv4 as a fallback.
4. **Use OpenAI `gpt-4o` and/or Qwen as label assistants only**, never as automatic
   training truth.
5. **Treat field captures as a continual data engine**, not a live self-training
   loop. Human-reviewed labels and protected holdouts are what make the system
   improve safely.

## Source Notes

- Ultralytics docs describe YOLO support for detection, tracking, classification,
  export, and edge deployment, but also note AGPL and enterprise licensing options.
- Hugging Face model cards list RT-DETRv2 and D-FINE COCO checkpoints under
  Apache-2.0 with object-detection support.
- PaddleOCR documentation and repository notes describe PP-OCRv5/PP-OCR deployment
  and Apache-2.0 licensing.
- Hugging Face model listings show available license-plate detectors, including
  YOLO11 plate checkpoints, but commonly under AGPL-3.0.
