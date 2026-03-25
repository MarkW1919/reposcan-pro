# Alerting Service

Evaluate detections against local hotlists and generate operator-visible alerts.

Current capabilities:
- exact and normalized hotlist matching
- configurable alert thresholding from the pipeline config
- alert record creation for downstream storage and UI retrieval
- optional webhook delivery transport for alert fan-out beyond the local UI
