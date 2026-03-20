# PRODUCT.md

RepoScan Pro is a field-grade, edge-first vehicle intelligence system for long-range and low-light vehicle observation, plate capture, OCR, and vehicle attribute classification.

## Problem Statement

Generic OCR demos fail in real deployments because the mission is constrained by distance, blur, low light, glare, reflective plates, motion, and unreliable connectivity. RepoScan Pro is being designed for those hostile conditions first.

## Primary Users

- field operators monitoring live detections
- investigators reviewing historical reads and hotlist events
- deployment engineers managing cameras, hardware, and runtime health

## V1 Outcomes

- detect vehicles in real time
- localize license plates reliably enough for downstream OCR
- preserve usable OCR under realistic low-light conditions
- classify vehicle color and make/model when possible
- attach GPS, timestamp, camera, and media metadata to each detection
- store results locally and sync only when connectivity permits

## Product Principles

- edge first
- local first
- hardware-aware
- data-realistic
- modular and replaceable

## Success Definition

The first version is successful only if it can:
- detect a relevant vehicle at useful distance
- isolate a plate with enough usable pixels
- recover readable text under realistic night or near-night conditions
- provide useful vehicle attributes when OCR confidence is weak
- store detections and media references locally without internet dependency

## Non-Goals

- cloud-only inference
- screenshot-friendly demo systems that ignore night performance
- one-model-does-everything shortcuts that reduce robustness

## Related Documents

- [Architecture](ARCHITECTURE.md)
- [Requirements](REQUIREMENTS.md)
- [Models](MODELS.md)
- [UI Workflows](UI_WORKFLOWS.md)

