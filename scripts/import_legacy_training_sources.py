from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
SKIP_IMAGE_NAMES = {
    "contact_sheet.jpg",
    "staging_preview.jpg",
    "dataset_preview.jpg",
    "render_preview.jpg",
}


def _configure_pythonpath(repo_root: Path) -> None:
    source_roots = [
        repo_root / "packages" / "contracts" / "src",
    ]
    for source_root in reversed(source_roots):
        sys.path.insert(0, str(source_root))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import legacy Seen-It-First training sources as RepoScan Pro dataset manifests.")
    parser.add_argument("--legacy-training-root", default=r"C:\LPR_Training")
    parser.add_argument("--output-dir", required=True)
    return parser.parse_args()


def _count_images(root: Path) -> int:
    if not root.exists():
        return 0
    return sum(1 for path in root.rglob("*") if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES)


def _write_manifest(path: Path, manifest) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(manifest.model_dump(mode="json", exclude_none=True), sort_keys=False),
        encoding="utf-8",
    )


def _iter_staged_assets(root: Path):
    asset_index = 1
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        if path.name.lower() in SKIP_IMAGE_NAMES:
            continue
        relative_path = path.relative_to(root)
        parts = relative_path.parts
        session_id = parts[0] if parts else "legacy_session"
        yield asset_index, session_id, relative_path
        asset_index += 1


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    _configure_pythonpath(repo_root)

    from reposcan_contracts.dataset import (
        DatasetAssetRecord,
        DatasetFormat,
        DatasetLicenseTier,
        DatasetProvenance,
        DatasetReviewStatus,
        DatasetSourceKind,
        DatasetSplit,
        DatasetSplitSource,
        DatasetTask,
        LightingCondition,
        TrainingDatasetManifest,
    )

    args = parse_args()
    legacy_root = Path(args.legacy_training_root).resolve()
    output_dir = Path(args.output_dir).resolve()

    manifests: list[tuple[Path, TrainingDatasetManifest]] = []

    stanford_root = legacy_root / "Datasets" / "stanford_cars" / "stanford_cars"
    stanford_manifest = TrainingDatasetManifest(
        dataset_name="legacy-stanford-cars-warmstart",
        dataset_version="legacy-2026-03-23",
        task=DatasetTask.vehicle_make_model_classification,
        format=DatasetFormat.imagefolder,
        storage_root=str(stanford_root),
        review_status=DatasetReviewStatus.pending,
        provenance=DatasetProvenance(
            source_name="Stanford Cars",
            source_kind=DatasetSourceKind.public_benchmark,
            license_tier=DatasetLicenseTier.unknown,
            license_name="review required",
            license_reference="legacy import pending provenance review",
            region="us",
            notes="Imported from the legacy Seen-It-First training workspace as a warm-start source.",
        ),
        splits=[
            DatasetSplitSource(
                split=DatasetSplit.train,
                relative_path="cars_train",
                sample_count=_count_images(stanford_root / "cars_train"),
                tags=["legacy_import", "warm_start"],
            ),
            DatasetSplitSource(
                split=DatasetSplit.holdout,
                relative_path="cars_test",
                sample_count=_count_images(stanford_root / "cars_test"),
                tags=["legacy_import", "warm_start"],
            ),
        ],
        notes="Warm-start source only. This is not a roadside field benchmark.",
    )
    manifests.append((output_dir / "legacy-stanford-cars-warmstart.yaml", stanford_manifest))

    detection_root = legacy_root / "Datasets" / "us_plate_detection" / "oklahoma" / "incoming_raw"
    staged_assets = [
        DatasetAssetRecord(
            asset_id=f"legacy_raw_{index:04d}",
            relative_path=relative_path.as_posix(),
            capture_session_id=session_id,
            lighting_conditions=[LightingCondition.unknown],
            annotations=[],
            tags=["legacy_import", "unlabeled_raw", "oklahoma"],
        )
        for index, session_id, relative_path in _iter_staged_assets(detection_root)
    ]
    detection_manifest = TrainingDatasetManifest(
        dataset_name="legacy-oklahoma-detection-staging",
        dataset_version="legacy-2026-03-23",
        task=DatasetTask.plate_detection,
        format=DatasetFormat.generic_capture,
        storage_root=str(detection_root),
        review_status=DatasetReviewStatus.pending,
        provenance=DatasetProvenance(
            source_name="Legacy Oklahoma capture staging",
            source_kind=DatasetSourceKind.field_capture,
            license_tier=DatasetLicenseTier.internal,
            license_name="internal field capture",
            license_reference="legacy seen-it-first import pending review",
            region="us-ok",
            notes="Unlabeled raw captures imported for review and future annotation.",
        ),
        assets=staged_assets,
        notes="These are staged raw frames and should pass the new intake workflow before training use.",
    )
    manifests.append((output_dir / "legacy-oklahoma-detection-staging.yaml", detection_manifest))

    for bundle_name, bundle_root, tags in (
        (
            "legacy-oklahoma-ocr-synthetic-standard",
            legacy_root / "Datasets" / "us_plate_ocr" / "oklahoma" / "synthetic_rendered" / "rendered_20260318_062012",
            ["legacy_import", "synthetic", "oklahoma"],
        ),
        (
            "legacy-oklahoma-ocr-synthetic-tribal",
            legacy_root / "Datasets" / "us_plate_ocr" / "oklahoma" / "synthetic_rendered" / "tribal_rendered_20260318_064909",
            ["legacy_import", "synthetic", "oklahoma", "tribal"],
        ),
    ):
        manifest = TrainingDatasetManifest(
            dataset_name=bundle_name,
            dataset_version="legacy-2026-03-23",
            task=DatasetTask.plate_ocr,
            format=DatasetFormat.ocr_manifest,
            storage_root=str(bundle_root),
            review_status=DatasetReviewStatus.pending,
            provenance=DatasetProvenance(
                source_name="Legacy Oklahoma synthetic OCR renders",
                source_kind=DatasetSourceKind.synthetic,
                license_tier=DatasetLicenseTier.internal,
                license_name="internal generated synthetic support data",
                license_reference="legacy seen-it-first synthetic import pending review",
                region="us-ok",
                notes="Synthetic OCR support data carried forward from the old project.",
            ),
            splits=[
                DatasetSplitSource(
                    split=DatasetSplit.train,
                    relative_path="train/images",
                    label_path="train/labels.csv",
                    sample_count=_count_images(bundle_root / "train" / "images"),
                    tags=tags,
                ),
                DatasetSplitSource(
                    split=DatasetSplit.validation,
                    relative_path="valid/images",
                    label_path="valid/labels.csv",
                    sample_count=_count_images(bundle_root / "valid" / "images"),
                    tags=tags,
                ),
                DatasetSplitSource(
                    split=DatasetSplit.holdout,
                    relative_path="test/images",
                    label_path="test/labels.csv",
                    sample_count=_count_images(bundle_root / "test" / "images"),
                    tags=tags,
                ),
            ],
            notes="Synthetic OCR support only. Use as augmentation support, not as a replacement for real captures.",
        )
        manifests.append((output_dir / f"{bundle_name}.yaml", manifest))

    for path, manifest in manifests:
        _write_manifest(path, manifest)
        print(path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
