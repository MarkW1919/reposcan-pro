# TRAINING.md

RepoScan Pro training is task-specific. Do not train the entire pipeline as a monolith.

## Training Strategy

- use transfer learning wherever practical
- train vehicle detection, plate detection, OCR, and classification as separate workstreams
- design experiments around operational metrics, not vanity metrics
- keep training outputs and checkpoints outside git

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

## Promotion Rules

- document dataset versions and assumptions
- export promoted models to ONNX
- generate and retain per-stage artifact manifests outside git
- validate promoted bundles against their runtime config before deployment handoff
- record runtime implications for TensorRT or equivalent deployment targets
- keep a rollback path to the previously accepted model

## Related Documents

- [Datasets](DATASETS.md)
- [Models](MODELS.md)
- [Inference](INFERENCE.md)
- [Model Promotion Workflow](MODEL_PROMOTION_WORKFLOW.md)
