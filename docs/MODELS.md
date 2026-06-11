# MODELS.md

## Detection

- Ultralytics YOLO11 warm starts for vehicle and plate detector fine-tuning
- previously exported YOLOv8-family artifacts remain valid if already promoted and benchmarked

## OCR

- PaddleOCR recognition training workflow with PP-OCRv5 config discovery
- synthetic OCR support stays supplemental to reviewed field plate crops
- public OpenALPR US OCR imports are valid real-data candidates when their import summary and manifest validation are clean
- failed OCR probe workspaces are not promotion candidates unless they have a completed status, `best_accuracy` checkpoint, exported inference directory, and recorded validation or holdout metric

## Classification

- torchvision backbones for single-task attribute training
- supported warm starts: `resnet18`, `resnet50`, `efficientnet_b0`, `mobilenet_v3_large`, `convnext_tiny`
- metadata-backed ONNX classifier exports allow modular color and make/model/year models to plug into the current runtime

## Color

- baseline: ResNet18
- stronger warm-start profile available with EfficientNet-B0

## Tracking

- ByteTrack-style tracker in the current edge pipeline

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
