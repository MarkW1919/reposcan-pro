# PREPROCESSING_BENCHMARK.md

This document records the current OCR-facing preprocessing benchmark evidence for RepoScan Pro.

The benchmark now uses a real PaddleOCR runtime against label-backed OCR crops. That closes the Section 3 requirement to benchmark preprocessing impact on OCR and low-light behavior.

It does not close any field-acceptance requirement by itself. These reports are still lab evidence, not deployed-camera proof.

## Repo-Tracked Evidence

- real OCR benchmark, public OpenALPR holdout:
  - [openalpr-us-holdout.preprocessing-ocr.json](../services/preprocessing/fixtures/reports/openalpr-us-holdout.preprocessing-ocr.json)
- low-light stress benchmark, synthetic Oklahoma holdout:
  - [synthetic-oklahoma-holdout.preprocessing-ocr.json](../services/preprocessing/fixtures/reports/synthetic-oklahoma-holdout.preprocessing-ocr.json)

## Current Results

From the public OpenALPR holdout report (`75` real plate crops):

- raw exact match: `0.627`
- preprocessed exact match: `0.600`
- raw character accuracy: `0.905`
- preprocessed character accuracy: `0.900`

From the synthetic Oklahoma holdout report (`30` support crops):

- raw exact match: `0.033`
- preprocessed exact match: `0.033`
- raw character accuracy: `0.255`
- preprocessed character accuracy: `0.297`

From the synthetic low-light subset (`19` metadata-flagged low-light crops):

- raw exact match: `0.000`
- preprocessed exact match: `0.053`
- raw character accuracy: `0.204`
- preprocessed character accuracy: `0.221`

## What This Proves

- preprocessing impact is now measured against a real OCR runtime, not only image-quality proxies
- the current default preprocessing profile is not a universal win for already-isolated real plate crops
- the same profile does improve controlled low-light OCR character accuracy and low-light exact match on the synthetic support holdout
- the benchmark can now be rerun before changing preprocessing defaults or OCR runtime assumptions

## Regenerate

Public OCR holdout:

```powershell
.\.venv\Scripts\python.exe .\scripts\benchmark_preprocessing_ocr.py `
  --dataset-manifest .\data\manifests\public\openalpr-us-benchmark-20260402.yaml `
  --split holdout `
  --pipeline-config .\configs\pipelines\default-edge.yaml `
  --paddleocr-root .\tmp\PaddleOCR `
  --checkpoint-dir .\tmp\PaddleOCR\en_PP-OCRv4_rec_train\best_accuracy `
  --character-dict-path .\tmp\PaddleOCR\ppocr\utils\en_dict.txt `
  --report-output .\services\preprocessing\fixtures\reports\openalpr-us-holdout.preprocessing-ocr.json
```

Synthetic Oklahoma support holdout with metadata-tagged low-light subset:

```powershell
.\.venv\Scripts\python.exe .\scripts\benchmark_preprocessing_ocr.py `
  --dataset-manifest .\data\staged\synthetic_ok_ocr_claude_handoff_2026-03-24\manifest.yaml `
  --split holdout `
  --pipeline-config .\configs\pipelines\default-edge.yaml `
  --paddleocr-root .\tmp\PaddleOCR `
  --checkpoint-dir .\tmp\PaddleOCR\en_PP-OCRv4_rec_train\best_accuracy `
  --character-dict-path .\tmp\PaddleOCR\ppocr\utils\en_dict.txt `
  --metadata-csv .\data\staged\synthetic_ok_ocr_claude_handoff_2026-03-24\metadata.csv `
  --report-output .\services\preprocessing\fixtures\reports\synthetic-oklahoma-holdout.preprocessing-ocr.json
```

## Interpretation

- default preprocessing should not be treated as automatically beneficial for every isolated OCR crop
- low-light-oriented preprocessing remains justified as a targeted support path for dark or degraded crops
- future preprocessing changes should be compared against both reports before becoming the default

## What This Does Not Prove

- deployed-camera low-light acceptance
- long-range field-read performance
- moving-platform OCR behavior
- target-hardware latency acceptance

## Related Documents

- [Training](TRAINING.md)
- [Models](MODELS.md)
- [Project Status Checklist](PROJECT_STATUS_CHECKLIST.md)
