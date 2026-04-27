# PRODUCT.md

RepoScan Pro is a repossession-focused, edge-first LPR and vehicle intelligence system for long-range and low-light vehicle observation, plate capture, OCR, vehicle attribute classification, local hotlist matching, and evidence handoff.

## Problem Statement

Generic OCR demos fail in repossession deployments because the mission is constrained by distance, blur, low light, glare, reflective plates, motion, unreliable connectivity, and short operator decision windows. RepoScan Pro is being designed for those hostile conditions first, with the edge node treated as the authoritative system during a field run.

## Primary Users

- field operators monitoring live detections and recovery account hits
- investigators reviewing historical reads, vehicle attributes, and hotlist events
- deployment engineers managing cameras, hardware, and runtime health
- recovery managers exporting evidence packages for client or compliance review

## V1 Outcomes

- detect vehicles in real time
- localize license plates reliably enough for downstream OCR
- preserve usable OCR under realistic low-light conditions
- classify vehicle color and make/model when possible
- match reads against local recovery-account and hotlist data without requiring internet
- attach GPS, timestamp, camera, and media metadata to each detection
- store results locally and sync only when connectivity permits
- export a self-contained detection package for account review, dispute handling, or chain-of-custody handoff

## Product Principles

- edge first
- local first
- hardware-aware
- data-realistic
- modular and replaceable
- operator-safe and evidence-oriented
- Jetson Orin Nano Super deployable

## Success Definition

The first version is successful only if it can:
- detect a relevant vehicle at useful distance
- isolate a plate with enough usable pixels
- recover readable text under realistic night or near-night conditions
- provide useful vehicle attributes when OCR confidence is weak
- store detections and media references locally without internet dependency
- run the qualified TensorRT edge profile on a Jetson Orin Nano Super appliance within the declared latency and memory budgets
- preserve a defensible audit trail for hotlist hits, operator decisions, media retention, and exports

## Non-Goals

- cloud-only inference
- screenshot-friendly demo systems that ignore night performance
- one-model-does-everything shortcuts that reduce robustness
- automatic repossession decisions without human operator review
- bypassing state, client, or agency compliance requirements

## Related Documents

- [Architecture](ARCHITECTURE.md)
- [Requirements](REQUIREMENTS.md)
- [Models](MODELS.md)
- [UI Workflows](UI_WORKFLOWS.md)
