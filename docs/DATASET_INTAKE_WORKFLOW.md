# DATASET_INTAKE_WORKFLOW.md

RepoScan Pro uses manifest-driven dataset intake so external datasets, staged field captures, and synthetic support data can be reviewed through one path.

## 1. Create The Local Workspace

```powershell
.\.venv\Scripts\python.exe .\scripts\init_dataset_workspace.py --root .\data
```

This creates:

```text
data/
|-- raw/
|-- staged/
|-- curated/
|-- eval/
`-- manifests/
```

## 2. Register Or Write A Dataset Manifest

Use one of these approaches:

- write a new manifest by hand under `data/manifests/`
- start from the example manifests in `configs/datasets/`
- import legacy Seen-It-First sources into local manifests with:

```powershell
.\.venv\Scripts\python.exe .\scripts\import_legacy_training_sources.py --output-dir .\data\manifests\legacy
```

## 3. Validate Intake

```powershell
.\.venv\Scripts\python.exe .\scripts\validate_training_dataset_manifest.py --manifest .\configs\datasets\example-capture-intake.yaml
```

Add `--verify-files` when the manifest points at real local media and you want existence checks too.

## 4. Plan Session-Aware Splits

For capture-based manifests with asset-level records:

```powershell
.\.venv\Scripts\python.exe .\scripts\plan_training_dataset_split.py `
  --manifest .\configs\datasets\example-capture-intake.yaml `
  --output .\data\manifests\example-capture-split.yaml `
  --field-eval-tag long_range `
  --field-eval-tag low_light
```

This keeps capture sessions together and can reserve dedicated `field_eval` samples when assets are tagged for benchmark use.

## 5. Promote Into Curated Training Sets

- `raw/` keeps untouched drops
- `staged/` is for reviewed but not yet finalized data
- `curated/` is for training-ready datasets with accepted labels
- `eval/` is for protected holdouts and field-eval sets

For plate-detection capture sets:

1. export a label-review index with `scripts/export_detection_label_index.py`
2. place YOLO labels under a mirrored labels root
3. promote the reviewed labels with `scripts/promote_detection_dataset.py`

Do not move data into a training plan until the manifest passes provenance, license, and annotation review.

## Legacy Source Notes

The old `Seen-It-First` assets on this machine are worth using through manifests, not by importing the old runtime code wholesale.

Today the most reusable legacy sources are:

- Stanford Cars as a vehicle make/model warm-start dataset
- Oklahoma staged raw captures for future plate-detection labeling
- Oklahoma synthetic OCR support renders for augmentation and pretraining support

## Related Documents

- [Datasets](DATASETS.md)
- [Annotation Standards](ANNOTATION_STANDARDS.md)
- [Detection Dataset Curation](DETECTION_DATASET_CURATION.md)
- [Training](TRAINING.md)
