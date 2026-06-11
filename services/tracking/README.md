# Tracking Service

Maintain multi-frame association, best-read promotion, and duplicate suppression for vehicle detections before storage and alerting.

Current capabilities:
- configurable `sort`, `byte_tracker`, and `deep_sort`-style matching policies
- OCR candidate fusion with configurable promotion thresholds
- best-frame evidence selection across the life of a track
- duplicate suppression for quick repeated passes from the same camera
- deterministic strategy benchmarking for crowded crossings, camera motion, and repeat-pass workloads

Refresh the repo-tracked Section 5 evidence report with:

```powershell
.\.venv\Scripts\python.exe .\scripts\generate_tracking_evidence.py --output-root .\services\tracking\fixtures --overwrite
```
