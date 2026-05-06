# CAMERA_AND_IMAGING.md

Camera and imaging quality set the upper bound on RepoScan Pro performance. If the plate does not occupy enough usable pixels, software cannot recover the read reliably.

## Imaging Priorities

- high-sensitivity sensor selection
- sufficient plate pixel density at target distance
- low-noise exposure strategy for moving targets
- optics that preserve usable detail in low light
- optional IR-assisted illumination without hotspot blowout

## Capture Rules

- optimize for readable plate pixels, not wide-field marketing shots
- control blur before attempting AI compensation
- preserve dynamic range where headlights, shadows, and reflective plates coexist
- validate camera placement for motion, vibration, and angle of incidence

## Required Validation Scenes

- long standoff distance with small plate occupancy
- oncoming headlights and retroreflective bloom
- dark vehicles in low-contrast scenes
- moving targets at varying shutter and gain settings
- IR-assisted scenes with hotspot and halation risk

## Operational Guidance

- treat optics, exposure, illumination, and sensor choice as part of the AI system
- reject hardware or mounting plans that cannot produce usable plate evidence
- review capture examples before approving model changes

## Two-Camera Scan Workflow

The truck-edge profile is designed around two physical cameras but one primary real-time AI budget on Jetson Orin Nano Super:

- the long-range LPR camera is the primary AI stream inside the configured address radius
- the wide low-light camera records context and can run lower-rate or deferred vehicle recognition
- when the operator exits the scan radius, vehicle make/model/color enrichment runs against the saved scan-session frames and is attached to the same GPS/address evidence package
- do not size the Nano profile as a continuous two-camera full-inference appliance; use Orin NX/AGX only if both cameras must run heavy AI concurrently

## Related Documents

- [Product](PRODUCT.md)
- [Models](MODELS.md)
- [Low-Light Validation Skill](../.claude/skills/low-light-validation/SKILL.md)
