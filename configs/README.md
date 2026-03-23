# Configs

Reserve configuration sources for cameras, datasets, models, deployments, benchmark manifests, and environment-specific overrides.

Design rule:
- keep runtime behavior config-driven instead of hardcoding camera and model choices

Current examples include:
- local workstation development under `deployments/local-dev.yaml`
- Jetson Orin edge deployment tuning under `deployments/jetson-orin-edge.yaml`
- RTSP camera registration under `cameras/example-camera.yaml`
- USB camera registration under `cameras/example-usb-camera.yaml`
- capture-intake, curated detection, eval holdout, and integrated training dataset examples under `datasets/`
- training workflow profiles under `training/`
- promoted-bundle benchmark scaffolding under `benchmarks/example-promoted-onnx-benchmark.yaml`
