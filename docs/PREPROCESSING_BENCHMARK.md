# PREPROCESSING_BENCHMARK.md

This document defines the current preprocessing benchmark harness for RepoScan Pro.

It is intentionally scoped as a preprocessing-quality benchmark, not a final OCR-accuracy benchmark. The real Section 3 checklist item stays open until the team benchmarks preprocessing against a real OCR-capable runtime and a representative low-light corpus.

## Current Harness

Use the local benchmark script to measure:

- frame count processed
- artifact generation count
- average brightness before preprocessing
- average brightness after preprocessing
- how often exposure compensation triggered
- how often the OpenCV CLAHE path was used when available

Run:

```powershell
.\.venv\Scripts\python.exe .\scripts\benchmark_preprocessing.py --frames-dir C:\path\to\frames
```

## What This Proves Today

- the preprocessing service can run across a real folder of local images
- artifact generation is stable across a batch
- exposure-aware tuning changes can be observed numerically
- low-light lift can be compared between preprocessing revisions

## What This Does Not Prove Yet

- exact-match OCR gains
- character-error-rate gains
- field-valid long-range performance gains
- production-ready low-light acceptance behavior

Those remain blocked on:

- a real OCR runtime in the inference stack
- representative labeled low-light and long-range evaluation frames
- benchmark runs tied to accepted holdout sets

## Recommended Next Benchmark Step

Once the real OCR path is integrated:

1. assemble a labeled low-light evaluation subset
2. run OCR on raw plate crops
3. run OCR on rectified and preprocessed plate crops
4. compare exact match, character accuracy, and latency
5. record the result before promoting new preprocessing defaults

## Related Documents

- [Training](TRAINING.md)
- [Models](MODELS.md)
- [Project Status Checklist](PROJECT_STATUS_CHECKLIST.md)
