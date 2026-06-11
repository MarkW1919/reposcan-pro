# Preprocessing Service

Own image conditioning for long-range and low-light scenes before plate-centric inference.

Current integrated slice:
- emits a dedicated prepared-frame contract for inference while preserving the raw evidence path
- writes preprocessing artifacts to a local runtime folder for headless ingest and debugging
- applies exposure-aware tuning plus low-light-oriented contrast enhancement when valid images are available
- supports an OpenCV-oriented CLAHE path when the runtime has OpenCV available, with a safe Pillow fallback
- provides plate-crop rectification helpers for downstream OCR preparation
- exposes plate-crop preprocessing metadata for OCR benchmark reporting
- degrades safely to passthrough behavior when the source frame is missing or not decodable

Repo-tracked evidence:
- `services/preprocessing/fixtures/reports/openalpr-us-holdout.preprocessing-ocr.json`
- `services/preprocessing/fixtures/reports/synthetic-oklahoma-holdout.preprocessing-ocr.json`
