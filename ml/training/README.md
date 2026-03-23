# ML Training

Reserve training plans, experiment drivers, and evaluation harnesses for detectors, OCR, and classifiers.

Constraints:
- do not commit datasets or model weights
- document experiment inputs, outputs, and promotion criteria
- keep benchmark manifests and reports reviewable even when the underlying datasets stay outside git
- initialize the local dataset workspace with `scripts/init_dataset_workspace.py`
- validate and split dataset manifests before starting fine-tuning
- import legacy Seen-It-First sources through `scripts/import_legacy_training_sources.py` rather than wiring the old codebase directly
- use `configs/training/` profiles plus `train_*` scripts for make/model, color, detection, and OCR runs
- prefer `prepare-only` and `dry-run` checks before using `--execute`
