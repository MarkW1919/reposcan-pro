# Model Selection Skill

## Purpose
Choose models for each task.

## Tasks
- evaluate model options
- compare speed vs accuracy
- ensure edge compatibility

## Preferred stack
- YOLOv8 (detection)
- LPRNet (OCR)
- EfficientNet (classification)
- DeepSORT (tracking)

## Workflow
1. Check whether the imaging stack can support the intended task.
2. Compare candidate models against long-range, low-light, and edge constraints.
3. Favor models with clean export paths to ONNX and TensorRT.
4. Document tradeoffs, failure modes, and integration assumptions.

## Output
- selected model
- justification
- expected performance
- integration notes

