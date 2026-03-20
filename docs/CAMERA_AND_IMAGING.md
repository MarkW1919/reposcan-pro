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

## Related Documents

- [Product](PRODUCT.md)
- [Models](MODELS.md)
- [Low-Light Validation Skill](../.claude/skills/low-light-validation/SKILL.md)

