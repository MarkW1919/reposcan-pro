#!/usr/bin/env python
"""Catalog every trained model under runtime/ so the hard-won weights are never lost.

The trained model weights live under ``runtime/`` which is gitignored (repo
policy: no_model_weight_commits). That keeps multi-gigabyte weights out of git
but means the only record of *what we trained, how good it was, and where it
lives* is the filesystem on one machine. This script produces a TRACKED catalog
of those artifacts — path, size, SHA-256, modified time, and any accuracy
metadata it can parse — written to:

    docs/model_inventory.json   (machine-readable, committed)
    docs/MODEL_INVENTORY.md     (human-readable table, committed)

The weights stay gitignored; the *catalog with checksums* is committed, so the
assets are documented, integrity-verifiable, and recoverable-by-description even
on a fresh clone or new machine.

Usage:
    python scripts/inventory_trained_models.py            # regenerate the catalog
    python scripts/inventory_trained_models.py --verify   # re-hash, report drift/missing (non-zero exit on mismatch)
    python scripts/inventory_trained_models.py --no-hash  # fast scan, skip SHA-256

Run from the repo root.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Artifact file types worth cataloging (trained weights / exports / engines).
WEIGHT_SUFFIXES = {".pt", ".pth", ".onnx", ".engine", ".pdparams", ".pdmodel"}
# Roots scanned for trained artifacts (all under the gitignored runtime/ store).
SCAN_ROOTS = ("runtime/training", "runtime/models")
# Tiny test fixtures masquerade as models; anything below this is not a real weight.
MIN_REAL_WEIGHT_BYTES = 50_000


def _iso_mtime(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - missing/corrupt metadata is non-fatal
        return {}


def _run_accuracy(run_dir: Path) -> dict:
    """Best-effort accuracy/metadata for a training run directory."""
    out: dict = {}
    summary = _load_json(run_dir / "evaluation_summary.json")
    if summary:
        for key in ("best_validation_accuracy", "holdout_accuracy", "evaluated_at_utc"):
            if summary.get(key) is not None:
                out[key] = summary[key]
    # OCR runs record dataset composition rather than a single accuracy field.
    ocr = _load_json(run_dir / "ocr_support_mix_summary.json")
    if ocr:
        out["ocr_primary_dataset"] = ocr.get("primary_dataset_name")
        out["ocr_primary_train_rows"] = ocr.get("primary_train_rows")
    return out


def collect(repo_root: Path, *, do_hash: bool) -> dict:
    artifacts: list[dict] = []
    for root_rel in SCAN_ROOTS:
        root = repo_root / root_rel
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in WEIGHT_SUFFIXES:
                continue
            size = path.stat().st_size
            rel = path.relative_to(repo_root).as_posix()
            # Identify the owning training run (first dir under runtime/training).
            run_name = None
            parts = path.relative_to(repo_root).parts
            if parts[:2] == ("runtime", "training") and len(parts) >= 3:
                run_name = parts[2]
            record = {
                "path": rel,
                "run": run_name,
                "bytes": size,
                "is_fixture_sized": size < MIN_REAL_WEIGHT_BYTES,
                "modified_utc": _iso_mtime(path),
            }
            if do_hash:
                record["sha256"] = _sha256(path)
            artifacts.append(record)

    # Attach run-level accuracy metadata once per run.
    run_meta: dict = {}
    for art in artifacts:
        run = art.get("run")
        if run and run not in run_meta:
            run_meta[run] = _run_accuracy(repo_root / "runtime" / "training" / run)

    real = [a for a in artifacts if not a["is_fixture_sized"]]
    return {
        "generated_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "policy": "Weights are gitignored (no_model_weight_commits); this catalog is the tracked record. Restore weights from backup and verify with --verify against the recorded sha256.",
        "scan_roots": list(SCAN_ROOTS),
        "summary": {
            "artifact_count": len(artifacts),
            "real_weight_count": len(real),
            "total_bytes": sum(a["bytes"] for a in artifacts),
        },
        "run_metadata": run_meta,
        "artifacts": artifacts,
    }


def _fmt_mb(num_bytes: int) -> str:
    return f"{num_bytes / 1_048_576:.1f} MB"


def render_markdown(catalog: dict) -> str:
    lines: list[str] = []
    lines.append("# MODEL_INVENTORY.md")
    lines.append("")
    lines.append("> **Generated** by `scripts/inventory_trained_models.py` — do not edit by hand.")
    lines.append(f"> Last generated: `{catalog['generated_utc']}`")
    lines.append("")
    lines.append(catalog["policy"])
    lines.append("")
    s = catalog["summary"]
    lines.append(
        f"**{s['real_weight_count']} real trained weights** "
        f"({s['artifact_count']} artifacts incl. fixtures), total {_fmt_mb(s['total_bytes'])}."
    )
    lines.append("")
    lines.append("To verify integrity / detect loss after a clone or restore:")
    lines.append("")
    lines.append("```")
    lines.append("python scripts/inventory_trained_models.py --verify")
    lines.append("```")
    lines.append("")
    lines.append("## Trained runs (accuracy where recorded)")
    lines.append("")
    lines.append("| Run | Holdout | Val | Notes |")
    lines.append("|---|---:|---:|---|")
    for run, meta in sorted(catalog["run_metadata"].items()):
        holdout = meta.get("holdout_accuracy")
        val = meta.get("best_validation_accuracy")
        holdout_s = f"{holdout:.4f}" if isinstance(holdout, (int, float)) else "—"
        val_s = f"{val:.4f}" if isinstance(val, (int, float)) else "—"
        note = meta.get("ocr_primary_dataset") or ""
        lines.append(f"| `{run}` | {holdout_s} | {val_s} | {note} |")
    lines.append("")
    lines.append("## Artifacts (SHA-256 truncated to 16 chars)")
    lines.append("")
    lines.append("| Path | Size | SHA-256 | Modified |")
    lines.append("|---|---:|---|---|")
    for art in catalog["artifacts"]:
        if art["is_fixture_sized"]:
            continue
        sha = art.get("sha256", "")
        sha_s = sha[:16] if sha else "(not hashed)"
        lines.append(f"| `{art['path']}` | {_fmt_mb(art['bytes'])} | `{sha_s}` | {art['modified_utc']} |")
    lines.append("")
    return "\n".join(lines)


def verify(repo_root: Path, catalog_path: Path) -> int:
    prior = _load_json(catalog_path)
    if not prior or "artifacts" not in prior:
        print(f"No prior catalog at {catalog_path}; run without --verify first.", file=sys.stderr)
        return 2
    problems = 0
    for art in prior["artifacts"]:
        path = repo_root / art["path"]
        if not path.exists():
            print(f"MISSING: {art['path']}")
            problems += 1
            continue
        recorded = art.get("sha256")
        if recorded:
            actual = _sha256(path)
            if actual != recorded:
                print(f"CHANGED: {art['path']}\n  recorded {recorded}\n  actual   {actual}")
                problems += 1
    if problems:
        print(f"\n{problems} problem(s) found.")
        return 1
    print(f"OK: all {len(prior['artifacts'])} cataloged artifacts present and unchanged.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--verify", action="store_true", help="re-hash and report drift/missing against the committed catalog")
    parser.add_argument("--no-hash", action="store_true", help="skip SHA-256 (fast scan)")
    parser.add_argument("--repo-root", default=None)
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve() if args.repo_root else Path(__file__).resolve().parents[1]
    json_path = repo_root / "docs" / "model_inventory.json"
    md_path = repo_root / "docs" / "MODEL_INVENTORY.md"

    if args.verify:
        return verify(repo_root, json_path)

    catalog = collect(repo_root, do_hash=not args.no_hash)
    json_path.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(catalog), encoding="utf-8")
    s = catalog["summary"]
    print(f"Wrote {json_path.relative_to(repo_root)} and {md_path.relative_to(repo_root)}")
    print(f"Cataloged {s['real_weight_count']} real weights ({s['artifact_count']} artifacts), {_fmt_mb(s['total_bytes'])}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
