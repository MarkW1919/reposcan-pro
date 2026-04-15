# Oklahoma Dataset Readiness

RepoScan Pro should not be shipped against a vehicle-recognition dataset unless
the dataset reflects the vehicles and capture conditions an Oklahoma operator is
likely to see.

## Coverage Target

The current Oklahoma target is captured in
`configs/datasets/oklahoma-vehicle-coverage-targets.yaml`.

It uses Oklahoma vehicle registration body-style mix from the Alliance for
Automotive Innovation Oklahoma state facts page:

- UVs / SUVs / crossovers: 37.2% of registered vehicles
- Cars: 28.5%
- Pickups: 27.0%
- Vans / minivans: 5.7%

The commercial gate intentionally overweights pickups and UV/SUV/crossover
coverage because repossession and rural-road deployments will see those classes
often, and because truck generation differences matter for vehicle recognition.

## Required Tags

Vehicle detection and vehicle recognition datasets should tag asset records with
these body-style tags where known:

- `vehicle_class:pickup`
- `vehicle_class:suv_crossover`
- `vehicle_class:passenger_car`
- `vehicle_class:van_minivan`

High-priority Oklahoma make/model-family tags:

- `make_model:ford_f_series`
- `make_model:chevrolet_silverado`
- `make_model:ram_pickup`
- `make_model:gmc_sierra`
- `make_model:toyota_tacoma`
- `make_model:chevrolet_tahoe_suburban`

These tags are not a replacement for structured make/model/year labels. They are
a release-gate coverage signal that lets us prove the dataset is not dominated
by easy public benchmark sedans or unrelated regions.

## Shipping Gate

Run the Oklahoma commercial readiness audit against every primary dataset
manifest before using it to train a model that will ship:

```powershell
.\.venv\Scripts\python.exe .\scripts\audit_training_dataset_readiness.py `
  --dataset-manifest C:\path\to\oklahoma-training-dataset.yaml `
  --level oklahoma-commercial `
  --verify-files `
  --report-output .\runtime\dataset_readiness\oklahoma-training-dataset.json
```

For local smoke tests only, use `--level development`. Do not use that level to
claim deployment readiness.

## What Must Be True Before Shipping

- primary training datasets are approved, not pending
- license tier is known and usable
- train, validation, holdout, and field-eval splits are session-separated
- labels are reviewed for the task being trained
- synthetic data is capped and supplemental only
- low-light, long-range, glare, rain, dirty-plate, and partial-occlusion cases
  are represented
- Oklahoma body-style and priority truck/SUV coverage passes the readiness gate
- benchmark reports are generated from approved holdouts, not ad hoc folders

## Current State

The existing local Silverado dataset and example manifests are useful for
pipeline development, but they are not yet Oklahoma commercial training
datasets. The readiness gate is expected to fail them until we add reviewed
Oklahoma field captures and label coverage at the required scale.
