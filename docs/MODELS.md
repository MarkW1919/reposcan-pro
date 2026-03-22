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

- `configs/models/local-demo-runtime.yaml` is a tracked builtin runtime stack for no-hardware demos and integration tests
- `configs/models/example-model-stack.yaml` remains the placeholder shape for future exported model artifacts
- exported ONNX and TensorRT model stacks are still promotion targets, not completed repo assets today

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
