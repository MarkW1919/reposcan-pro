# Model Integration Skill

## Purpose
Integrate a detector, OCR model, classifier, or tracker into the runtime without coupling the whole system to one model family.

## Inputs
- exported model artifact metadata
- runtime target and config surface
- expected input and output contract

## Workflow
1. Confirm the model's IO contract, normalization rules, and export format.
2. Route model loading through configuration rather than hardcoded paths.
3. Normalize outputs into shared detection and confidence contracts.
4. Document runtime assumptions, fallbacks, and validation checks.

## Output
- integration notes
- runtime contract mapping
- deployment caveats

