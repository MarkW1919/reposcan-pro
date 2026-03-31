# DATASETS.md

RepoScan Pro must be trained and validated with data that reflects real deployment conditions, not only curated daytime benchmarks.

## Data Principles

- do not commit datasets into the repository
- record provenance, license, region coverage, and collection assumptions
- favor real night and long-range data over synthetic approximations
- quarantine questionable or weakly labeled data until reviewed

## Priority Data Domains

- long-range vehicle scenes
- small and angled license plates
- low-light and no-light scenes
- IR-assisted captures
- glare, halation, and retroreflective bloom
- motion blur and off-axis targets
- region-relevant US plate styles for V1

## Expected Local Layout

```text
data/
|-- raw/
|-- staged/
|-- curated/
|-- eval/
`-- manifests/
```

Create it locally with:

```powershell
.\.venv\Scripts\python.exe .\scripts\init_dataset_workspace.py --root .\data
```

## Annotation Requirements

- vehicle bounding boxes for detection
- plate bounding boxes for plate localization
- OCR text labels with auditability for uncertain characters
- vehicle attribute labels separated by task where practical
- metadata for lighting condition, distance band, and scene quality when available

## Vehicle Recognition Catalog

Make/model/year recognition should not rely on ad hoc label strings copied from mixed sources.

Use a canonical seed list plus a year-validation pass to build the training taxonomy:

1. start with a markdown or CSV seed list of `Year | Make | Model`
2. validate model-year availability against a reviewed source
3. emit a canonical catalog plus expanded per-year labels

The repo now includes `scripts/build_vehicle_recognition_catalog.py` for this step. It accepts the same markdown-table shape the operator team is already compiling, can expand placeholder rows such as `all models from database coverage`, and validates year availability against the official NHTSA vehicle catalog API while caching results locally for repeatable offline use.

## Split Strategy

- separate training, validation, and holdout data by capture session when possible
- protect night and long-range holdouts from contamination
- maintain dedicated field-eval sets for regression checks

## Intake Gate

No dataset enters a training plan until it passes provenance, annotation quality, and imaging realism review.

Legacy Seen-It-First training assets on this machine should enter RepoScan Pro through typed manifests and review, not through direct code reuse.

For plate detection, reviewed captures should be promoted into curated YOLO datasets and eval holdouts with the workflow in [Detection Dataset Curation](DETECTION_DATASET_CURATION.md).

Approved `eval_holdout` manifests are also the preferred source for promoted-bundle benchmark runs. The benchmark CLI can derive a tagged frame manifest directly from an approved holdout manifest so evaluation stays tied to reviewed dataset records instead of ad hoc path lists.

Before a holdout is treated as a real regression gate, run the qualification workflow in [Field Eval Qualification](FIELD_EVAL_QUALIFICATION.md). That step verifies minimum coverage for `long_range`, `low_light`, session spread, and benchmark-ready labeling.

## Related Documents

- [Training](TRAINING.md)
- [Annotation Standards](ANNOTATION_STANDARDS.md)
- [Dataset Intake Workflow](DATASET_INTAKE_WORKFLOW.md)
- [Detection Dataset Curation](DETECTION_DATASET_CURATION.md)
- [Requirements](REQUIREMENTS.md)
- [Dataset Intake Skill](../.claude/skills/dataset-intake/SKILL.md)
