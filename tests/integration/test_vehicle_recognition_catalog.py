from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml

from reposcan_contracts.vehicle_catalog import VehicleCatalogOverrideEntry, VehicleCatalogSeedEntry
from reposcan_training.vehicle_catalog import (
    build_vehicle_recognition_catalog,
    expand_vehicle_seed_entries,
    extract_placeholder_models,
    parse_vehicle_seed_markdown,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_parse_vehicle_seed_markdown_supports_operator_table_shape():
    entries = parse_vehicle_seed_markdown(
        "\n".join(
            [
                "| Year | Make | Model |",
                "|------|------|-------|",
                "| 1999-2026 | Acura | MDX |",
                "| 1999-2026 | Ford | F-150 |",
                "| 1999-2026 | GMC | (all models from database coverage: Sierra 1500, Yukon, etc.) |",
            ]
        )
    )

    assert len(entries) == 3
    assert entries[0].make == "Acura"
    assert entries[0].model == "MDX"
    assert entries[0].start_year == 1999
    assert entries[0].end_year == 2026
    assert entries[2].placeholder is True


def test_build_vehicle_recognition_catalog_tracks_partial_and_placeholder_rows():
    seed_entries = [
        VehicleCatalogSeedEntry(make="Acura", model="MDX", start_year=2000, end_year=2003),
        VehicleCatalogSeedEntry(make="Ford", model="F-150", start_year=2000, end_year=2002),
        VehicleCatalogSeedEntry(
            make="GMC",
            model="(all models from database coverage: Sierra 1500, Yukon, etc.)",
            start_year=1999,
            end_year=2026,
        ),
    ]

    lookup = {
        ("Acura", 2000): [],
        ("Acura", 2001): ["MDX"],
        ("Acura", 2002): ["MDX"],
        ("Acura", 2003): ["MDX"],
        ("Ford", 2000): ["F-150"],
        ("Ford", 2001): ["F-150"],
        ("Ford", 2002): ["F-150"],
    }

    catalog = build_vehicle_recognition_catalog(
        catalog_name="vehicle-catalog-test",
        seed_entries=seed_entries,
        fetch_models_for_make_year_fn=lambda make, year: lookup.get((make, year), []),
    )

    mdx_entry = next(entry for entry in catalog.entries if entry.make == "Acura")
    ford_entry = next(entry for entry in catalog.entries if entry.make == "Ford")
    gmc_entry = next(entry for entry in catalog.entries if entry.make == "GMC")

    assert mdx_entry.status == "partial"
    assert mdx_entry.available_years == [2001, 2002, 2003]
    assert ford_entry.status == "matched"
    assert len(catalog.labels) == 6
    assert gmc_entry.status == "placeholder"


def test_build_vehicle_recognition_catalog_applies_alias_overrides():
    seed_entries = [
        VehicleCatalogSeedEntry(make="Audi", model="Q4 e-tron", start_year=2022, end_year=2023),
    ]
    overrides = {
        ("audi", "q4 e tron"): VehicleCatalogOverrideEntry(
            make="Audi",
            model="Q4 e-tron",
            aliases=["Q4 etron"],
            source_models=["Q4 E-TRON"],
        )
    }

    catalog = build_vehicle_recognition_catalog(
        catalog_name="vehicle-catalog-overrides-test",
        seed_entries=seed_entries,
        overrides=overrides,
        fetch_models_for_make_year_fn=lambda make, year: ["Q4 E-TRON"],
    )

    audi_entry = catalog.entries[0]
    assert audi_entry.status == "matched"
    assert audi_entry.available_years == [2022, 2023]
    assert audi_entry.matched_source_models == ["Q4 E-TRON"]


def test_extract_placeholder_models_reads_operator_examples():
    seed_entry = VehicleCatalogSeedEntry(
        make="GMC",
        model="(all models from database coverage: Acadia, Canyon, Sierra 1500, Yukon XL, etc. - full trims in source DB)",
        start_year=1999,
        end_year=2026,
    )

    assert extract_placeholder_models(seed_entry) == ["Acadia", "Canyon", "Sierra 1500", "Yukon XL"]


def test_expand_vehicle_seed_entries_supports_listed_and_make_all_models():
    seed_entries = [
        VehicleCatalogSeedEntry(
            make="GMC",
            model="(all models from database coverage: Acadia, Canyon, Sierra 1500, Yukon XL, etc.)",
            start_year=2020,
            end_year=2021,
        )
    ]

    listed_entries = expand_vehicle_seed_entries(
        seed_entries,
        placeholder_mode="listed",
        fetch_models_for_make_year_fn=lambda make, year: [],
    )
    assert [entry.model for entry in listed_entries] == ["Acadia", "Canyon", "Sierra 1500", "Yukon XL"]

    fetched_entries = expand_vehicle_seed_entries(
        seed_entries,
        placeholder_mode="make-all-models",
        fetch_models_for_make_year_fn=lambda make, year: ["Acadia", "Terrain"] if year == 2020 else ["Terrain", "Yukon XL"],
    )
    assert [entry.model for entry in fetched_entries] == ["Acadia", "Terrain", "Yukon XL"]


def test_build_vehicle_recognition_catalog_script_uses_offline_cache(tmp_path):
    seed_path = tmp_path / "vehicle-seed.md"
    seed_path.write_text(
        "\n".join(
            [
                "| Year | Make | Model |",
                "|------|------|-------|",
                "| 2000-2003 | Acura | MDX |",
                "| 2000-2002 | Ford | F-150 |",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    for year, models in {
        2000: [{"Model_Name": "F-150"}],
        2001: [{"Model_Name": "MDX"}, {"Model_Name": "F-150"}],
        2002: [{"Model_Name": "MDX"}, {"Model_Name": "F-150"}],
        2003: [{"Model_Name": "MDX"}],
    }.items():
        for make, payload_models in {"Acura": models if year >= 2001 else [], "Ford": models if year <= 2002 else []}.items():
            cache_path = cache_dir / f"{make.lower().replace('-', ' ').replace(' ', '_')}__{year}.json"
            cache_path.write_text(json.dumps({"Results": payload_models}, indent=2), encoding="utf-8")

    output_path = tmp_path / "catalog.yaml"
    labels_path = tmp_path / "labels.csv"
    result = _run_script(
        "scripts/build_vehicle_recognition_catalog.py",
        "--seed",
        str(seed_path),
        "--output",
        str(output_path),
        "--labels-csv",
        str(labels_path),
        "--cache-dir",
        str(cache_dir),
        "--offline-cache-only",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    catalog = yaml.safe_load(output_path.read_text(encoding="utf-8"))
    labels = labels_path.read_text(encoding="utf-8").strip().splitlines()

    assert catalog["catalog_name"] == "us-vehicle-recognition-catalog"
    assert len(catalog["entries"]) == 2
    assert labels[0] == "make,model,year,label"
    assert any("Acura,MDX,2001,Acura MDX 2001" in row for row in labels[1:])


def test_build_vehicle_recognition_catalog_script_expands_placeholders_to_seed_csv(tmp_path):
    seed_path = tmp_path / "vehicle-seed.md"
    seed_path.write_text(
        "\n".join(
            [
                "| Year | Make | Model |",
                "|------|------|-------|",
                "| 2020-2021 | GMC | (all models from database coverage: Acadia, Canyon, Yukon XL, etc.) |",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    for year, models in {
        2020: [{"Model_Name": "Acadia"}, {"Model_Name": "Terrain"}],
        2021: [{"Model_Name": "Terrain"}, {"Model_Name": "Yukon XL"}],
    }.items():
        cache_path = cache_dir / f"gmc__{year}.json"
        cache_path.write_text(json.dumps({"Results": models}, indent=2), encoding="utf-8")

    output_path = tmp_path / "catalog.yaml"
    expanded_seed_path = tmp_path / "expanded-seed.csv"
    result = _run_script(
        "scripts/build_vehicle_recognition_catalog.py",
        "--seed",
        str(seed_path),
        "--output",
        str(output_path),
        "--expanded-seed-csv",
        str(expanded_seed_path),
        "--placeholder-mode",
        "make-all-models",
        "--cache-dir",
        str(cache_dir),
        "--offline-cache-only",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    expanded_rows = expanded_seed_path.read_text(encoding="utf-8").strip().splitlines()

    assert expanded_rows[0] == "year_range,make,model,aliases,notes"
    assert any("2020-2021,GMC,Acadia,," in row for row in expanded_rows[1:])
    assert any("2020-2021,GMC,Terrain,," in row for row in expanded_rows[1:])
    assert any("2020-2021,GMC,Yukon XL,," in row for row in expanded_rows[1:])
