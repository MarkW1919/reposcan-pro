# Edge Optimization Skill

## Purpose
Optimize system for real-time edge inference.

## Focus
- latency reduction
- memory usage
- GPU utilization

## Methods
- ONNX conversion
- TensorRT optimization
- batching
- async pipelines

## Workflow
1. Measure baseline latency and memory use before optimizing.
2. Tune pipeline stages that block end-to-end throughput.
3. Keep recovery, startup, and watchdog behavior intact.
4. Record hardware assumptions alongside performance numbers.

## Output
- optimized pipeline
- performance metrics

