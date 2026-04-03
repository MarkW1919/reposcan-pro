from __future__ import annotations

import argparse
import csv
import json
import random
import shutil
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml


OCR_ALLOWED_CHARS = set("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ")
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


@dataclass(frozen=True)
class OcrSample:
    filename: str
    text: str
    state_code: str


def _configure_pythonpath(repo_root: Path) -> None:
    source_roots = [
        repo_root / "packages" / "contracts" / "src",
    ]
    for source_root in reversed(source_roots):
        sys.path.insert(0, str(source_root))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import the OpenALPR US benchmark mirror into a RepoScan OCR manifest workspace."
    )
    parser.add_argument("--source-root", required=True, help="Directory containing groundtruth.csv and usimages/")
    parser.add_argument("--output-root", required=True, help="Destination root for train/validation/holdout splits")
    parser.add_argument("--manifest-path", required=True, help="Output RepoScan dataset manifest path")
    parser.add_argument("--dataset-name", default="openalpr-us-benchmark")
    parser.add_argument(
        "--dataset-version",
        default=f"public-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--train-ratio", type=float, default=0.8)
    parser.add_argument("--validation-ratio", type=float, default=0.1)
    parser.add_argument("--holdout-ratio", type=float, default=0.1)
    parser.add_argument("--copy-mode", choices=["copy", "hardlink"], default="hardlink")
    return parser.parse_args()


def _normalize_label(text: str) -> str:
    return "".join(character for character in text.upper().strip() if character in OCR_ALLOWED_CHARS)


def _copy_or_link_file(source: Path, destination: Path, *, copy_mode: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        destination.unlink()
    if copy_mode == "hardlink":
        try:
            destination.hardlink_to(source)
            return
        except OSError:
            pass
    shutil.copy2(source, destination)


def _round_split_counts(count: int, *, train_ratio: float, validation_ratio: float, holdout_ratio: float) -> dict[str, int]:
    if count <= 0:
        return {"train": 0, "validation": 0, "holdout": 0}

    validation_count = int(round(count * validation_ratio))
    holdout_count = int(round(count * holdout_ratio))

    if count >= 5 and validation_ratio > 0.0:
        validation_count = max(1, validation_count)
    if count >= 8 and holdout_ratio > 0.0:
        holdout_count = max(1, holdout_count)

    if validation_count + holdout_count >= count:
        overflow = validation_count + holdout_count - (count - 1)
        while overflow > 0 and holdout_count > 0:
            holdout_count -= 1
            overflow -= 1
        while overflow > 0 and validation_count > 0:
            validation_count -= 1
            overflow -= 1

    train_count = count - validation_count - holdout_count
    return {
        "train": train_count,
        "validation": validation_count,
        "holdout": holdout_count,
    }


def _assign_splits(
    samples: list[OcrSample],
    *,
    train_ratio: float,
    validation_ratio: float,
    holdout_ratio: float,
    seed: int,
) -> dict[str, list[OcrSample]]:
    by_state: dict[str, list[OcrSample]] = defaultdict(list)
    for sample in samples:
        by_state[sample.state_code].append(sample)

    randomizer = random.Random(seed)
    split_map = {"train": [], "validation": [], "holdout": []}
    for state_code in sorted(by_state):
        state_samples = list(by_state[state_code])
        randomizer.shuffle(state_samples)
        counts = _round_split_counts(
            len(state_samples),
            train_ratio=train_ratio,
            validation_ratio=validation_ratio,
            holdout_ratio=holdout_ratio,
        )
        train_end = counts["train"]
        validation_end = train_end + counts["validation"]
        split_map["train"].extend(state_samples[:train_end])
        split_map["validation"].extend(state_samples[train_end:validation_end])
        split_map["holdout"].extend(state_samples[validation_end:])
    return split_map


def _write_labels_csv(path: Path, rows: list[tuple[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["image_file", "plate_text"])
        writer.writeheader()
        for image_file, plate_text in rows:
            writer.writerow({"image_file": image_file, "plate_text": plate_text})


def _load_samples(source_root: Path) -> tuple[list[OcrSample], list[str]]:
    labels_path = source_root / "groundtruth.csv"
    images_root = source_root / "usimages"
    if not labels_path.exists():
        raise FileNotFoundError(f"missing groundtruth.csv under {source_root}")
    if not images_root.exists():
        raise FileNotFoundError(f"missing usimages directory under {source_root}")

    samples: list[OcrSample] = []
    missing_images: list[str] = []
    with labels_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        for row in reader:
            if len(row) < 2:
                continue
            raw_filename = row[0].strip()
            raw_text = row[1].strip()
            if not raw_filename:
                continue
            if raw_filename.lower() in {"image_file", "filename"}:
                continue
            image_path = images_root / raw_filename
            if image_path.suffix.lower() not in IMAGE_SUFFIXES:
                continue
            if not image_path.exists():
                missing_images.append(raw_filename)
                continue
            text = _normalize_label(raw_text)
            if not text:
                continue
            state_code = raw_filename[:2].lower()
            samples.append(OcrSample(filename=raw_filename, text=text, state_code=state_code))
    return samples, missing_images


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    _configure_pythonpath(repo_root)

    from reposcan_contracts.dataset import (
        DatasetFormat,
        DatasetLicenseTier,
        DatasetProvenance,
        DatasetReviewStatus,
        DatasetSourceKind,
        DatasetSplit,
        DatasetSplitSource,
        DatasetTask,
        TrainingDatasetManifest,
    )

    args = parse_args()
    source_root = Path(args.source_root).resolve()
    output_root = Path(args.output_root).resolve()
    manifest_path = Path(args.manifest_path).resolve()

    ratio_total = args.train_ratio + args.validation_ratio + args.holdout_ratio
    if abs(ratio_total - 1.0) > 1e-6:
        raise ValueError("train, validation, and holdout ratios must add up to 1.0")

    samples, missing_images = _load_samples(source_root)
    if not samples:
        raise ValueError(f"no OCR samples were found under {source_root}")

    split_map = _assign_splits(
        samples,
        train_ratio=args.train_ratio,
        validation_ratio=args.validation_ratio,
        holdout_ratio=args.holdout_ratio,
        seed=args.seed,
    )

    images_root = source_root / "usimages"
    split_rows: dict[str, list[tuple[str, str]]] = {"train": [], "validation": [], "holdout": []}
    for split_name, split_samples in split_map.items():
        split_images_root = output_root / split_name / "images"
        split_images_root.mkdir(parents=True, exist_ok=True)
        for sample in split_samples:
            source_image = images_root / sample.filename
            destination_image = split_images_root / sample.filename
            _copy_or_link_file(source_image, destination_image, copy_mode=args.copy_mode)
            split_rows[split_name].append((sample.filename, sample.text))
        _write_labels_csv(output_root / split_name / "labels.csv", split_rows[split_name])

    summary = {
        "source_root": str(source_root),
        "output_root": str(output_root),
        "dataset_name": args.dataset_name,
        "dataset_version": args.dataset_version,
        "sample_count": len(samples),
        "split_counts": {name: len(rows) for name, rows in split_rows.items()},
        "missing_source_images": missing_images,
        "missing_source_image_count": len(missing_images),
        "unique_state_prefixes": sorted({sample.state_code for sample in samples}),
        "character_set": "".join(sorted({character for sample in samples for character in sample.text})),
    }
    summary_path = output_root / "import_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    manifest = TrainingDatasetManifest(
        dataset_name=args.dataset_name,
        dataset_version=args.dataset_version,
        task=DatasetTask.plate_ocr,
        format=DatasetFormat.ocr_manifest,
        storage_root=str(output_root),
        review_status=DatasetReviewStatus.pending,
        provenance=DatasetProvenance(
            source_name="OpenALPR US benchmark via USLicensePlateOCR mirror",
            source_kind=DatasetSourceKind.public_benchmark,
            license_tier=DatasetLicenseTier.unknown,
            license_name="review required",
            license_reference="https://github.com/lawrencexli/USLicensePlateOCR ; derived from https://github.com/openalpr/benchmarks",
            region="us",
            notes="Real US plate crops imported into RepoScan format. Treat as a small public benchmark, not a full production dataset.",
        ),
        splits=[
            DatasetSplitSource(
                split=DatasetSplit.train,
                relative_path="train/images",
                label_path="train/labels.csv",
                sample_count=len(split_rows["train"]),
                tags=["public_benchmark", "openalpr", "us", "real"],
            ),
            DatasetSplitSource(
                split=DatasetSplit.validation,
                relative_path="validation/images",
                label_path="validation/labels.csv",
                sample_count=len(split_rows["validation"]),
                tags=["public_benchmark", "openalpr", "us", "real"],
            ),
            DatasetSplitSource(
                split=DatasetSplit.holdout,
                relative_path="holdout/images",
                label_path="holdout/labels.csv",
                sample_count=len(split_rows["holdout"]),
                tags=["public_benchmark", "openalpr", "us", "real"],
            ),
        ],
        notes=(
            "Imported from a public US plate OCR benchmark mirror. "
            "Prefer local field captures as the primary production source once labeled."
        ),
    )

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        yaml.safe_dump(manifest.model_dump(mode="json", exclude_none=True), sort_keys=False),
        encoding="utf-8",
    )

    print(f"Output root: {output_root}")
    print(f"Manifest: {manifest_path}")
    print(f"Summary: {summary_path}")
    for split_name in ("train", "validation", "holdout"):
        print(f"{split_name}: {len(split_rows[split_name])}")
    if missing_images:
        print(f"Skipped missing source images: {len(missing_images)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
