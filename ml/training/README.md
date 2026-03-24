# ML Training

Reserve training plans, experiment drivers, and evaluation harnesses for detectors, OCR, and classifiers.

Constraints:
- do not commit datasets or model weights
- document experiment inputs, outputs, and promotion criteria
- keep benchmark manifests and reports reviewable even when the underlying datasets stay outside git
- initialize the local dataset workspace with `scripts/init_dataset_workspace.py`
- validate and split dataset manifests before starting fine-tuning
- import legacy Seen-It-First sources through `scripts/import_legacy_training_sources.py` rather than wiring the old codebase directly
- export detector label indexes with `scripts/export_detection_label_index.py` and promote reviewed YOLO labels with `scripts/promote_detection_dataset.py`
- feed approved `eval_holdout` manifests into `scripts/benchmark_promoted_bundle.py` to generate benchmark inputs and evaluation reports tied to reviewed datasets
- gate reviewed holdouts with `scripts/qualify_field_eval_dataset.py` before treating them as real regression sets
- use `configs/training/` profiles plus `train_*` scripts for make/model, color, detection, and OCR runs
- prefer `prepare-only` and `dry-run` checks before using `--execute`
