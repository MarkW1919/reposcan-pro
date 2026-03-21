# Preprocessing Service

Own image conditioning for long-range and low-light scenes before plate-centric inference.

Current integrated slice:
- emits a dedicated prepared-frame contract for inference while preserving the raw evidence path
- writes preprocessing artifacts to a local runtime folder for headless ingest and debugging
- applies denoising plus low-light-oriented contrast enhancement when valid images are available
- degrades safely to passthrough behavior when the source frame is missing or not decodable

Planned responsibilities:
- exposure-aware enhancement
- denoising and contrast normalization
- rectification support for downstream OCR crops
