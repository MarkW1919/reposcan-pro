from __future__ import annotations

import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen

import yaml

from reposcan_contracts.vehicle_catalog import (
    VehicleCatalogEntry,
    VehicleCatalogSeedEntry,
    VehicleRecognitionCatalog,
    VehicleRecognitionLabel,
)

_WHITESPACE_RE = re.compile(r"\s+")
_PUNCTUATION_RE = re.compile(r"[^a-z0-9]+")


def normalize_vehicle_text(value: str) -> str:
    cleaned = _PUNCTUATION_RE.sub(" ", value.lower())
    return _WHITESPACE_RE.sub(" ", cleaned).strip()


def slugify_vehicle_text(value: str) -> str:
    normalized = normalize_vehicle_text(value)
    return normalized.replace(" ", "_")


def parse_vehicle_seed_markdown(text: str) -> list[VehicleCatalogSeedEntry]:
    entries: list[VehicleCatalogSeedEntry] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 3 or cells[0].lower() == "year":
            continue
        if set(cells[0]) == {"-"}:
            continue
        year_text, make, model = cells[0], cells[1], cells[2]
        start_year, end_year = _parse_year_range(year_text)
        entries.append(
            VehicleCatalogSeedEntry(
                make=make,
                model=model,
                start_year=start_year,
                end_year=end_year,
                raw_row=raw_line,
            )
        )
    return entries


def parse_vehicle_seed_csv(text: str) -> list[VehicleCatalogSeedEntry]:
    rows = csv.DictReader(text.splitlines())
    entries: list[VehicleCatalogSeedEntry] = []
    for row in rows:
        year_text = str(row.get("Year") or row.get("year") or "").strip()
        make = str(row.get("Make") or row.get("make") or "").strip()
        model = str(row.get("Model") or row.get("model") or "").strip()
        if not year_text or not make or not model:
            continue
        start_year, end_year = _parse_year_range(year_text)
        aliases = [
            item.strip()
            for item in str(row.get("Aliases") or row.get("aliases") or "").split(";")
            if item.strip()
        ]
        entries.append(
            VehicleCatalogSeedEntry(
                make=make,
                model=model,
                start_year=start_year,
                end_year=end_year,
                aliases=aliases,
            )
        )
    return entries


def load_vehicle_seed_entries(path: str | Path) -> list[VehicleCatalogSeedEntry]:
    seed_path = Path(path)
    text = seed_path.read_text(encoding="utf-8")
    if seed_path.suffix.lower() in {".csv"}:
        return parse_vehicle_seed_csv(text)
    return parse_vehicle_seed_markdown(text)


def _parse_year_range(value: str) -> tuple[int, int]:
    normalized = value.replace(" ", "")
    if "-" in normalized:
        start_text, end_text = normalized.split("-", 1)
        return int(start_text), int(end_text)
    year = int(normalized)
    return year, year


def _utc_now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _cache_path(cache_dir: Path, *, make: str, year: int) -> Path:
    return cache_dir / f"{slugify_vehicle_text(make)}__{year}.json"


def fetch_nhtsa_models_for_make_year(
    make: str,
    year: int,
    *,
    cache_dir: Path,
    timeout_seconds: float = 20.0,
    offline_cache_only: bool = False,
) -> list[str]:
    cache_path = _cache_path(cache_dir, make=make, year=year)
    if cache_path.exists():
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    else:
        if offline_cache_only:
            raise FileNotFoundError(f"Cache miss for make='{make}' year={year} at '{cache_path}'")
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        url = f"https://vpic.nhtsa.dot.gov/api/vehicles/GetModelsForMakeYear/make/{quote(make)}/modelyear/{year}?format=json"
        with urlopen(url, timeout=timeout_seconds) as response:  # noqa: S310 - official NHTSA API endpoint
            payload = json.loads(response.read().decode("utf-8"))
        cache_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    results = payload.get("Results") or []
    return [str(item.get("Model_Name") or "").strip() for item in results if str(item.get("Model_Name") or "").strip()]


def _candidate_model_tokens(seed_entry: VehicleCatalogSeedEntry) -> set[str]:
    tokens = {normalize_vehicle_text(seed_entry.model)}
    tokens.update(normalize_vehicle_text(alias) for alias in seed_entry.aliases if alias.strip())
    return {token for token in tokens if token}


def _model_matches(seed_entry: VehicleCatalogSeedEntry, candidate_model: str) -> bool:
    candidate_token = normalize_vehicle_text(candidate_model)
    if not candidate_token:
        return False
    return candidate_token in _candidate_model_tokens(seed_entry)


def build_vehicle_recognition_catalog(
    *,
    catalog_name: str,
    seed_entries: list[VehicleCatalogSeedEntry],
    fetch_models_for_make_year_fn,
) -> VehicleRecognitionCatalog:
    catalog_entries: list[VehicleCatalogEntry] = []
    labels: list[VehicleRecognitionLabel] = []

    for seed_entry in seed_entries:
        if seed_entry.placeholder:
            catalog_entries.append(
                VehicleCatalogEntry(
                    make=seed_entry.make,
                    model=seed_entry.model,
                    requested_start_year=seed_entry.start_year,
                    requested_end_year=seed_entry.end_year,
                    status="placeholder",
                    notes=["Placeholder coverage row requires manual expansion before training."],
                )
            )
            continue

        matched_years: list[int] = []
        matched_models: set[str] = set()
        missing_years: list[int] = []

        for year in range(seed_entry.start_year, seed_entry.end_year + 1):
            available_models = fetch_models_for_make_year_fn(seed_entry.make, year)
            year_matches = sorted({model for model in available_models if _model_matches(seed_entry, model)})
            if year_matches:
                matched_years.append(year)
                matched_models.update(year_matches)
                labels.append(
                    VehicleRecognitionLabel(
                        make=seed_entry.make,
                        model=seed_entry.model,
                        year=year,
                        label=f"{seed_entry.make} {seed_entry.model} {year}",
                    )
                )
            else:
                missing_years.append(year)

        if not matched_years:
            status = "missing"
        elif missing_years:
            status = "partial"
        else:
            status = "matched"

        notes: list[str] = []
        if missing_years:
            notes.append(f"Unavailable years: {', '.join(str(year) for year in missing_years)}")

        catalog_entries.append(
            VehicleCatalogEntry(
                make=seed_entry.make,
                model=seed_entry.model,
                requested_start_year=seed_entry.start_year,
                requested_end_year=seed_entry.end_year,
                available_years=matched_years,
                matched_source_models=sorted(matched_models),
                status=status,
                notes=notes,
            )
        )

    return VehicleRecognitionCatalog(
        catalog_name=catalog_name,
        generated_at_utc=_utc_now_utc(),
        entries=catalog_entries,
        labels=labels,
    )


def write_vehicle_recognition_catalog(path: str | Path, catalog: VehicleRecognitionCatalog) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.suffix.lower() == ".json":
        output_path.write_text(catalog.model_dump_json(indent=2), encoding="utf-8")
        return
    output_path.write_text(yaml.safe_dump(catalog.model_dump(mode="json"), sort_keys=False), encoding="utf-8")


def write_vehicle_recognition_labels_csv(path: str | Path, labels: list[VehicleRecognitionLabel]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["make", "model", "year", "label"])
        for label in labels:
            writer.writerow([label.make, label.model, label.year, label.label])
