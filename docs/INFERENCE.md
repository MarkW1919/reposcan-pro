# INFERENCE.md

Inference is edge-first and local-first. Cloud services may augment analysis later, but they must not become a prerequisite for the primary operational path.

## Runtime Principles

- deterministic startup
- config-driven model loading
- graceful failure and restart behavior
- low-latency local processing
- temporal aggregation across frames when it improves read quality

## Planned Inference Flow

1. Acquire frame and camera metadata.
2. Apply preprocessing suitable for the scene and hardware profile.
3. Detect vehicles.
4. Detect plates in full-frame or vehicle crops, depending on configuration.
5. Crop, rectify, and normalize the best plate candidates.
6. Run OCR and preserve alternate candidates with confidence.
7. Run vehicle attribute classification when image quality allows.
8. Fuse confidence and pass enriched detections to tracking and storage.

## Runtime Contracts

- normalize model IO through shared contracts
- keep detector, OCR, classifier, and tracker replaceable
- record model version metadata with detections where practical
- protect throughput from blocking sync or UI work

## Failure Handling

- camera loss must not crash the full stack
- model load failure must surface clearly and degrade safely
- GPS failure should not block detection storage
- sync failure must not interrupt local recording

## Related Documents

- [Architecture](ARCHITECTURE.md)
- [Models](MODELS.md)
- [Deployment](DEPLOYMENT.md)
- [API Contracts](API_CONTRACTS.md)

