# MODEL_RELEASES.md

RepoScan Pro keeps accepted model releases outside git in an external registry so promoted bundles can be versioned, benchmarked, and rolled back without losing audit history.

## Registry Layout

```text
registry-root/
|-- channels/
|   `-- <channel>.yaml
`-- releases/
    `-- <release-id>/
        |-- release-record.yaml
        |-- benchmark_report.json
        `-- snapshots/
            |-- promoted-onnx.yaml
            |-- local-dev.yaml
            `-- benchmark.yaml
```

The bundle artifacts themselves stay in their own promoted bundle directory. The registry stores:

- accepted release metadata
- benchmark output
- channel pointers
- config and manifest snapshots for audit

The benchmark output now carries more than just exact-match summaries. It can include:

- overall and per-tag accuracy metrics
- latency summary
- runtime / promotion / deployment readiness
- source dataset linkage when the benchmark came from an approved `eval_holdout` manifest

## Register A Release

```powershell
.\.venv\Scripts\python.exe .\scripts\register_model_release.py `
  --model-config C:\artifacts\models\promoted\fixture-local-dev\promoted-onnx.yaml `
  --deployment-config .\configs\deployments\local-dev.yaml `
  --benchmark-manifest C:\artifacts\models\benchmarks\oklahoma-night-long-range.yaml `
  --registry-root C:\artifacts\models\registry `
  --channel local-dev-demo `
  --notes "Promoted after benchmark and deployment validation"
```

Registration only succeeds when:

- the promoted bundle is runtime-ready
- promotion validation passes
- deployment validation passes
- the benchmark manifest executes successfully

## Roll Back A Channel

To roll back to the channel's previous accepted release:

```powershell
.\.venv\Scripts\python.exe .\scripts\rollback_model_release.py `
  --registry-root C:\artifacts\models\registry `
  --channel local-dev-demo `
  --reason "Regression discovered during operator validation"
```

You can also roll back to a specific older release by adding `--to-release-id`.

## Release Record Contents

Each release record captures:

- release id and channel
- promoted bundle config path
- deployment profile used for validation
- benchmark manifest and benchmark report path
- overall and per-tag benchmark metrics
- latency summary from the benchmark report artifact
- runtime, promotion, and deployment readiness summary
- source run ids, checkpoints, and dataset-manifest references when present
- superseded release id and operator notes

## What This Proves Today

- accepted promoted bundles can be registered into an external audit registry
- release channels can move forward and backward without rewriting git history
- benchmark and deployment validation can be tied to a concrete accepted release id

## What This Does Not Prove Yet

- that the accepted release is field-ready
- that remote update orchestration is finalized
- that target-hardware rollback has been exercised on a real deployed edge rig

Those remain separate deployment and field-validation gates.
