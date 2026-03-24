# MODELS.md

## Detection

YOLOv8

## OCR

LPRNet

## Classification

EfficientNet

## Color

ResNet18

## Tracking

DeepSORT

## Output formats

ONNX
TensorRT

## Current Repo Runtime Split

- `configs/models/local-onnx-runtime.yaml` is a tracked ONNX runtime fixture stack that proves real backend-loaded inference execution in the repo today
- `configs/models/local-demo-runtime.yaml` is a tracked builtin runtime stack for no-hardware demos and integration tests
- `configs/models/example-model-stack.yaml` remains the placeholder shape for future exported model artifacts
- `configs/models/promoted-onnx-template.yaml` shows the expected shape for a promoted external ONNX bundle with per-stage artifact manifests and `path_base: config_dir`
- `configs/models/promoted-tensorrt-template.yaml` shows the expected shape for a promoted external TensorRT bundle with per-stage engine manifests and compatibility metadata
- `ml/inference/fixtures/promoted-onnx-runtime/` is the repo-tracked promoted ONNX fixture bundle used for Section 4 runtime evidence
- `ml/inference/fixtures/promoted-tensorrt-runtime/` is the repo-tracked TensorRT contract-validation fixture bundle used for deployment-profile checks

## Selection Notes

- vehicle and plate detection prioritize edge-friendly inference and strong recall
- OCR remains plate-specific; generic text models are not the default path
- classification stays modular so color and make/model can evolve independently
- tracking must improve multi-frame evidence quality without dominating latency

## Alternate Candidates To Evaluate

- PaddleOCR for OCR benchmarking and fallback comparison
- ByteTrack-style tracking when it improves throughput or stability
- smaller or larger YOLO variants depending on target hardware and plate size

## Promotion Criteria

- export cleanly to ONNX
- remain practical for TensorRT or equivalent edge acceleration
- demonstrate field-relevant gains in long-range and low-light scenes

## Related Documents

- [Architecture](ARCHITECTURE.md)
- [Training](TRAINING.md)
- [Inference](INFERENCE.md)
- [Model Promotion Workflow](MODEL_PROMOTION_WORKFLOW.md)
