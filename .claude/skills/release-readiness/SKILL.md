# Release Readiness Skill

## Purpose
Decide whether a planned release is safe to ship to field testing or deployment.

## Inputs
- current diff or release candidate
- test evidence
- operational risks and rollback plan

## Workflow
1. Confirm logging, validation, and rollback notes exist for changed areas.
2. Review test coverage and manual field checks for long-range and low-light behavior.
3. Verify no datasets, model weights, or generated artifacts are entering git.
4. Surface unresolved blockers before release approval.

## Output
- release readiness assessment
- blocking issues
- final go/no-go notes
