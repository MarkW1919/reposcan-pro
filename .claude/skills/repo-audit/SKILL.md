# Repo Audit Skill

## Purpose
Review the repository for architectural consistency, missing foundations, and drift from the documented mission.

## Inputs
- `CLAUDE.md`
- canonical docs under `docs/`
- current repo tree and recent diffs

## Workflow
1. Compare the repo shape to the documented subsystem boundaries.
2. Flag mismatches between code placement, config placement, and deployment intent.
3. Identify missing validation, logging, or rollback paths.
4. Prefer targeted findings over broad cleanup suggestions.

## Output
- repo health summary
- prioritized findings
- recommended next steps

