# PUBLIC_VEHICLE_DATASET_SOURCES.md

License-vetted public sources for vehicle make/model recognition training data.
This document captures what was investigated, what was rejected, and the
import paths that have been wired up.

The sources here feed the make/model classifier, not the LPR/OCR stage. Plate
data has its own provenance pipeline; see [PREBUILT_ALPR_INTEGRATION_GUIDE.md](PREBUILT_ALPR_INTEGRATION_GUIDE.md).

## Acquisition policy

Use a public source for ML training only when **all** of these hold:

- license is one of: CC0, Public Domain, CC BY, CC BY-SA, MIT, Apache 2.0
- license is recorded per image in `labels.csv` (image_file, class_label,
  vehicle_make, vehicle_model, vehicle_year, source_url, license_name,
  license_url, original_path)
- a typed manifest under `data/manifests/public/` references the dataset
- the dataset stays `review_status: pending` until visually reviewed

CC BY-NC, "non-commercial," "research-only," and ambiguous licenses are
**rejected** for production training. They may be used for warm-start
experiments only with explicit approval and `review_status: pending`.

## Approved sources

### 1. Kaggle VMMRdb mirror (`prabashwara/vmmrdb-dataset`)

- License: **CC0-1.0** (per dataset metadata, fetched via `kaggle datasets metadata`)
- Origin paper: Tafazzoli et al., "A Large and Diverse Dataset for Improved
  Vehicle Make and Model Recognition," CVPR 2017 Workshops
- Coverage: 9,170 year-specific class folders, 291,752 images, 1950–2016
- Total zip size: 12.38 GiB
- Per-image source URL recorded as the Kaggle dataset page; original VMMRdb
  folder path is preserved in `tags` and `labels.csv` so reviewers can trace
  back to the source

**Acquisition workflow:**

1. Download with the resumable downloader (Kaggle CLI does not retry on
   `IncompleteRead`):

   ```powershell
   .\.venv\Scripts\python.exe .\scripts\download_kaggle_dataset_resumable.py `
     --dataset prabashwara/vmmrdb-dataset `
     --output-path .\data\raw\kaggle_vmmrdb_full_<date>\vmmrdb-dataset.zip
   ```

2. Selectively extract priority classes:

   ```powershell
   .\.venv\Scripts\python.exe .\scripts\import_kaggle_vmmrdb_target_classes.py `
     --zip-path .\data\raw\kaggle_vmmrdb_full_<date>\vmmrdb-dataset.zip `
     --output-root .\data\curated\kaggle_vmmrdb_target_classes_<date> `
     --manifest-path .\data\manifests\public\kaggle-vmmrdb-target-classes-<date>.yaml `
     --max-per-class 400
   ```

3. Validate and generate the contact sheet:

   ```powershell
   .\.venv\Scripts\python.exe .\scripts\validate_training_dataset_manifest.py `
     --manifest .\data\manifests\public\kaggle-vmmrdb-target-classes-<date>.yaml `
     --verify-files

   .\.venv\Scripts\python.exe .\scripts\generate_dataset_contact_sheet.py `
     --storage-root .\data\curated\kaggle_vmmrdb_target_classes_<date>
   ```

The selective extractor maps VMMRdb folder patterns (`<make>_<model>_<year>`)
to RepoScan canonical class labels in [scripts/import_kaggle_vmmrdb_target_classes.py](../scripts/import_kaggle_vmmrdb_target_classes.py).

### 2. Wikimedia Commons (per-image license metadata)

- License: per image — accept only `cc0`, `cc by`, `cc by-sa`, `public domain`
- Importer: [scripts/import_wikimedia_vehicle_dataset.py](../scripts/import_wikimedia_vehicle_dataset.py)
  (priority make/model targets) and [scripts/import_wikimedia_gmc_sierra_gap_20260503.py](../scripts/import_wikimedia_gmc_sierra_gap_20260503.py)
  (focused gmc_sierra gap-fill)
- Per-image source URL is the Commons file description page; the API-returned
  thumbnail URL is used for transfer
- The downloader strips `utm_*` tracking parameters from image URLs and
  retries on HTTP 429, since Commons rate-limits the original-file endpoint;
  it skips records that lack a thumbnail URL because those resolve to the
  rate-limited path

### 3. NHTSA new-car assessment program imagery

- License: U.S. government work — public domain
- Coverage: clean year/make/model metadata, but image context is crash-test
- Use as supplemental robustness data only; do not mix into the primary
  clean-exterior training set without weighting
- Importer: [scripts/import_nhtsa_vehicle_dataset.py](../scripts/import_nhtsa_vehicle_dataset.py)

### 4. OpenALPR US benchmark (OCR side, not make/model)

- License: per-image metadata
- Imported via [scripts/import_openalpr_us_ocr_dataset.py](../scripts/import_openalpr_us_ocr_dataset.py)
- OCR training only; not in the make/model pipeline

## Investigated and held

These are usable in principle but not currently wired into an importer.

### FraunhoferIOSB/Synset-Boulevard (Hugging Face)

- License: **CC-BY-4.0**
- Coverage: ~260k synthetic VMMR images, 43 makes / 157 models, designed for
  surveillance scenarios with degradations (Bayer/Bloom good/bad variants)
- Status: **synthetic** — usable as supplemental support per the synthetic
  data policy in [INTERNET_VEHICLE_IMAGE_PIPELINE.md](INTERNET_VEHICLE_IMAGE_PIPELINE.md#accuracy-notes); never as the dominant validation/holdout source

## Rejected sources

- **Stanford Cars**: research-only license, not usable for production training
- **CompCars**: academic-only restrictions, not usable for production training
- **Unit293/car_models_3887** (Hugging Face): license `other`; would need
  per-image clarification before use
- **Google Images / Bing / Yandex scraping**: provenance and per-image license
  cannot be reliably preserved
- **Dealer listings, Facebook Marketplace, Reddit threads, OEM marketing
  galleries**: copyrighted source material, not licensed for ML reuse
- **Stock photo sites** (Getty, Shutterstock, Adobe): commercial license fees
  required; not used

## Class balance considerations

The Oklahoma-popular target list is 20 make/model classes. VMMRdb does not
cover model years past 2016, so 2017+ generations require Wikimedia Commons,
field captures, or other current-vehicle sources. NHTSA crash-test imagery
extends to current model years but is not a clean-exterior source.

When promoting a manifest from `pending` to `approved`, check the per-class
sample distribution against the Oklahoma coverage targets in
[configs/datasets/oklahoma-vehicle-coverage-targets.yaml](../configs/datasets/oklahoma-vehicle-coverage-targets.yaml)
and rebalance with the existing Wikimedia priority importer or new field
captures rather than dumping more of one class into training.

## Related Documents

- [Internet Vehicle Image Pipeline](INTERNET_VEHICLE_IMAGE_PIPELINE.md)
- [Datasets](DATASETS.md)
- [Dataset Intake Workflow](DATASET_INTAKE_WORKFLOW.md)
- [Annotation Standards](ANNOTATION_STANDARDS.md)
