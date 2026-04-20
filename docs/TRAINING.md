# TRAINING.md

RepoScan Pro training is task-specific. Do not train the entire pipeline as a monolith.

## Training Strategy

- use transfer learning wherever practical
- train vehicle detection, plate detection, OCR, and classification as separate workstreams
- design experiments around operational metrics, not vanity metrics
- keep training outputs and checkpoints outside git
- follow the pretrained stack and continual-learning direction in [Core Model Strategy](CORE_MODEL_STRATEGY.md)

## Required Workstreams

- vehicle detector fine-tuning
- plate detector fine-tuning for small, low-light targets
- plate OCR model training or fine-tuning
- vehicle color classification
- make/model classification

## Augmentation Rules

Use realistic augmentation only:
- motion blur
- defocus blur
- brightness and contrast shifts
- noise
- moderate compression artifacts
- realistic perspective distortion

Avoid:
- cartoonish synthetic artifacts
- unrealistic transforms that do not resemble field capture

## Evaluation Requirements

- exact-match plate accuracy
- character accuracy
- long-range subset performance
- low-light subset performance
- latency and export viability for edge targets
- evaluation reports that tie those metrics back to approved holdout manifests

## Promotion Rules

- document dataset versions and assumptions
- export promoted models to ONNX
- package promoted ONNX bundles outside git for deployment handoff
- generate and retain per-stage artifact manifests outside git
- for TensorRT engine bundles, record CUDA version, TensorRT version, precision, and target device capability in the manifest
- validate promoted bundles against their runtime config before deployment handoff
- benchmark promoted bundles against tagged long-range and low-light manifests before promotion decisions are treated as evidence-backed
- register accepted promoted bundles into an external release registry
- record runtime implications for TensorRT or equivalent deployment targets
- keep a rollback path to the previously accepted model

## Dataset Readiness Workflow

- initialize the local dataset workspace before importing or staging data
- validate every dataset manifest before a training run starts
- plan capture-derived splits by session where possible
- import legacy Seen-It-First assets through typed manifests instead of coupling to the old codebase
- promote reviewed capture labels into curated `yolo_detection` and `eval_holdout` manifests before detector fine-tuning
- derive benchmark manifests and evaluation reports from approved `eval_holdout` datasets rather than rebuilding ad hoc frame lists
- qualify reviewed `eval_holdout` manifests before treating them as real regression gates
- mix synthetic OCR support only into the training split and only through the profile-capped support path
- use training profiles under `configs/training/` so task settings and augmentation stay reviewable
- prefer `prepare-only` and `dry-run` validation before any long-running training job

## Related Documents

- [Datasets](DATASETS.md)
- [Annotation Standards](ANNOTATION_STANDARDS.md)
- [Dataset Intake Workflow](DATASET_INTAKE_WORKFLOW.md)
- [Detection Dataset Curation](DETECTION_DATASET_CURATION.md)
- [Core Model Strategy](CORE_MODEL_STRATEGY.md)
- [Training Workflows](TRAINING_WORKFLOWS.md)
- [Model Releases](MODEL_RELEASES.md)
- [Models](MODELS.md)
- [Inference](INFERENCE.md)
- [Model Promotion Workflow](MODEL_PROMOTION_WORKFLOW.md)
