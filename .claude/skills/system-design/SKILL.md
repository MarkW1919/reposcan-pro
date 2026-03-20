# System Design Skill

## Purpose
Design system architecture before implementation.

## Focus
- performance under real-world conditions
- long-range constraints
- low-light constraints

## Workflow
1. Start from mission requirements, not framework preference.
2. Separate capture, preprocessing, inference, storage, API, and UI concerns.
3. Preserve replaceable model boundaries and config-driven loading.
4. Document runtime and data flow before proposing code structure.

## Output
- pipeline design
- module interactions
- data flow diagram

## Constraints
- must support edge deployment
- must support offline operation

