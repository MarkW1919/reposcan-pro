# Training Run Design Skill

## Purpose
Design a training run that produces useful field metrics instead of demo-friendly but misleading results.

## Inputs
- target task
- dataset summary
- edge deployment constraints

## Workflow
1. Define the task-specific objective and the operational metric that matters.
2. Choose transfer-learning and augmentation strategy that match field conditions.
3. Separate train, validation, and holdout data with realistic night and long-range coverage.
4. Define export and promotion gates before the run starts.

## Output
- training run specification
- metric plan
- promotion criteria

