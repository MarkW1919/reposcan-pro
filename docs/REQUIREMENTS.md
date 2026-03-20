# REQUIREMENTS.md

## Must support

- long-range detection
- low-light detection
- real-time inference
- edge deployment

## Must include

- vehicle detection
- plate detection
- OCR
- classification
- GPS tagging

## Must NOT depend on

- cloud inference
- internet connectivity

## Operational Requirements

- function in day, dusk, night, shadowed, and no-light-assisted scenes
- support moving vehicles and moving camera platforms
- preserve local detection recording during sync outages
- survive camera reconnects and temporary runtime faults without silent data loss

## Quality Requirements

- every change must include logging impact notes
- every subsystem must define a validation path
- no feature is complete without test coverage or a manual field test plan
- architecture changes require explicit approval

## Acceptance Lens

A requirement is only satisfied when it improves usable field performance, not when it merely improves synthetic benchmark scores.

## Related Documents

- [Product](PRODUCT.md)
- [Architecture](ARCHITECTURE.md)
- [Deployment](DEPLOYMENT.md)

