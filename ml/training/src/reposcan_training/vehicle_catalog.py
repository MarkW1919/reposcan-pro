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
    VehicleCatalogOverrideEntry,
    VehicleCatalogSeedEntry,
    VehicleRecognitionCatalog,
    VehicleRecognitionLabel,
)

_WHITESPACE_RE = re.compile(r"\s+")
_PUNCTUATION_RE = re.compile(r"[^a-z0-9]+")
_PLACEHOLDER_SUFFIX_RE = re.compile(r"\s+-\s+full\s+trims.*$", re.IGNORECASE)
_PLACEHOLDER_ETC_RE = re.compile(r"\s*,?\s*etc\.?\s*$", re.IGNORECASE)


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


def load_vehicle_catalog_overrides(path: str | Path) -> dict[tuple[str, str], VehicleCatalogOverrideEntry]:
    override_path = Path(path)
    data = yaml.safe_load(override_path.read_text(encoding="utf-8")) or {}
    raw_entries = data.get("entries") if isinstance(data, dict) else data
    if not isinstance(raw_entries, list):
        raise ValueError("vehicle catalog overrides must contain a top-level list or an 'entries' list")

    overrides: dict[tuple[str, str], VehicleCatalogOverrideEntry] = {}
    for raw_entry in raw_entries:
        entry = VehicleCatalogOverrideEntry.model_validate(raw_entry)
        key = (normalize_vehicle_text(entry.make), normalize_vehicle_text(entry.model))
        overrides[key] = entry
    return overrides


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


def extract_placeholder_models(seed_entry: VehicleCatalogSeedEntry) -> list[str]:
    if not seed_entry.placeholder:
        return []
    model_text = seed_entry.model.strip()
    if ":" not in model_text:
        return []
    raw_list = model_text.split(":", 1)[1].strip().rstrip(")")
    raw_list = _PLACEHOLDER_SUFFIX_RE.sub("", raw_list)
    raw_list = _PLACEHOLDER_ETC_RE.sub("", raw_list)

    models: list[str] = []
    seen_tokens: set[str] = set()
    for candidate in raw_list.split(","):
        cleaned = candidate.strip().strip(".")
        token = normalize_vehicle_text(cleaned)
        if not token or token in seen_tokens:
            continue
        seen_tokens.add(token)
        models.append(cleaned)
    return models


def _model_matches(seed_entry: VehicleCatalogSeedEntry, candidate_model: str) -> bool:
    candidate_token = normalize_vehicle_text(candidate_model)
    if not candidate_token:
        return False
    return candidate_token in _candidate_model_tokens(seed_entry)


def _collect_make_models(
    seed_entry: VehicleCatalogSeedEntry,
    *,
    fetch_models_for_make_year_fn,
) -> list[str]:
    discovered_models: dict[str, str] = {}
    for year in range(seed_entry.start_year, seed_entry.end_year + 1):
        for model in fetch_models_for_make_year_fn(seed_entry.make, year):
            normalized = normalize_vehicle_text(model)
            if not normalized or normalized in discovered_models:
                continue
            discovered_models[normalized] = model.strip()
    return sorted(discovered_models.values(), key=normalize_vehicle_text)


def expand_vehicle_seed_entries(
    seed_entries: list[VehicleCatalogSeedEntry],
    *,
    fetch_models_for_make_year_fn,
    placeholder_mode: str = "preserve",
) -> list[VehicleCatalogSeedEntry]:
    if placeholder_mode not in {"preserve", "listed", "make-all-models"}:
        raise ValueError(f"Unsupported placeholder_mode '{placeholder_mode}'")

    expanded_entries: list[VehicleCatalogSeedEntry] = []
    for seed_entry in seed_entries:
        if not seed_entry.placeholder or placeholder_mode == "preserve":
            expanded_entries.append(seed_entry)
            continue

        listed_models = extract_placeholder_models(seed_entry)
        if placeholder_mode == "listed":
            expansion_models = listed_models
        else:
            expansion_models = _collect_make_models(
                seed_entry,
                fetch_models_for_make_year_fn=fetch_models_for_make_year_fn,
            )
            if not expansion_models:
                expansion_models = listed_models

        if not expansion_models:
            expanded_entries.append(seed_entry)
            continue

        for model in expansion_models:
            expanded_entries.append(
                VehicleCatalogSeedEntry(
                    make=seed_entry.make,
                    model=model,
                    start_year=seed_entry.start_year,
                    end_year=seed_entry.end_year,
                    notes=seed_entry.notes or "Expanded from placeholder coverage row.",
                    raw_row=seed_entry.raw_row,
                )
            )

    return expanded_entries


def build_vehicle_recognition_catalog(
    *,
    catalog_name: str,
    seed_entries: list[VehicleCatalogSeedEntry],
    fetch_models_for_make_year_fn,
    overrides: dict[tuple[str, str], VehicleCatalogOverrideEntry] | None = None,
) -> VehicleRecognitionCatalog:
    catalog_entries: list[VehicleCatalogEntry] = []
    labels: list[VehicleRecognitionLabel] = []
    overrides = overrides or {}

    for seed_entry in seed_entries:
        override = overrides.get((normalize_vehicle_text(seed_entry.make), normalize_vehicle_text(seed_entry.model)))
        if override is not None:
            seed_entry = seed_entry.model_copy(update={"aliases": [*seed_entry.aliases, *override.aliases]})

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
            year_matches = sorted(
                {
                    model
                    for model in available_models
                    if _model_matches(seed_entry, model)
                    or (
                        override is not None
                        and normalize_vehicle_text(model)
                        in {normalize_vehicle_text(item) for item in override.source_models}
                    )
                }
            )
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
        if override is not None and override.notes:
            notes.append(override.notes)

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


def write_vehicle_seed_entries_csv(path: str | Path, seed_entries: list[VehicleCatalogSeedEntry]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["year_range", "make", "model", "aliases", "notes"])
        for entry in seed_entries:
            year_range = (
                str(entry.start_year)
                if entry.start_year == entry.end_year
                else f"{entry.start_year}-{entry.end_year}"
            )
            writer.writerow(
                [
                    year_range,
                    entry.make,
                    entry.model,
                    ";".join(entry.aliases),
                    entry.notes or "",
                ]
            )
