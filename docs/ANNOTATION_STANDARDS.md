# ANNOTATION_STANDARDS.md

RepoScan Pro annotation standards exist to keep training labels usable across detection, OCR, attribute classification, and benchmark review.

## Core Rules

- annotate what the deployed cameras actually see, not idealized crops
- keep uncertain labels reviewable instead of guessing
- preserve capture-session context so training and holdout splits do not leak
- record lighting and distance metadata whenever it can be trusted

## Vehicle Detection

- draw one vehicle box per visible vehicle target that is relevant to LPR workflow
- keep the box tight to the visible vehicle body
- do not merge adjacent vehicles into one box
- do not label vehicles that are too small to matter for the target runtime

## Plate Detection

- draw one plate box per readable or plausibly readable plate
- keep the box tight to the physical plate edges
- include angled plates if the plate is still a real candidate for OCR
- skip decorative, printed, or non-vehicle signage that is not an actual plate

## OCR Text

- transcription is uppercase by default
- preserve only characters that are actually visible and supported by the chosen OCR label policy
- if a character is genuinely uncertain, quarantine the sample instead of inventing the text
- OCR datasets should be plate crops only, not full-scene images

## Vehicle Attributes

- `vehicle_color` should represent the dominant visible body color, not reflections
- `vehicle_make` should only be labeled when the make can be trusted
- `vehicle_model` should only be labeled when the model can be trusted
- `vehicle_year` should stay optional and conservative

## Lighting And Distance Metadata

- each capture-intake asset should record at least one lighting condition
- use `daylight`, `dusk`, `night`, `no_light`, `ir_assisted`, `glare`, or `unknown`
- use `near`, `medium`, or `long_range` for distance bands when known
- tag likely benchmark candidates with `low_light`, `long_range`, or other reviewable subset tags

## Review Rules

- approved dataset manifests must include reviewer identity, review timestamp, and accepted tasks
- raw staged captures may stay `pending` until provenance and annotation review are complete
- synthetic support data must be labeled as synthetic so it is not mistaken for field evidence

## Related Documents

- [Datasets](DATASETS.md)
- [Dataset Intake Workflow](DATASET_INTAKE_WORKFLOW.md)
- [Training](TRAINING.md)
