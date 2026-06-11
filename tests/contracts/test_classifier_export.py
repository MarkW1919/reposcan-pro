"""Tests for classifier export metadata label parsing.

Regression coverage for the underscore-slug bug: canonical make/model classes
are underscore-joined (chevrolet_suburban) with no spaces, so a whitespace-only
parser left model null and stuffed the full slug into make.
"""

from __future__ import annotations

from reposcan_contracts.classifier_export import (
    build_classifier_export_metadata,
    parse_vehicle_make_model_year,
)
from reposcan_contracts.dataset import DatasetTask


def test_parse_underscore_slug_splits_make_and_model():
    assert parse_vehicle_make_model_year("chevrolet_suburban") == ("chevrolet", "suburban", None)
    assert parse_vehicle_make_model_year("jeep_grand_cherokee") == ("jeep", "grand cherokee", None)
    assert parse_vehicle_make_model_year("ford_f_series") == ("ford", "f series", None)
    assert parse_vehicle_make_model_year("honda_cr_v") == ("honda", "cr v", None)
    assert parse_vehicle_make_model_year("toyota_4runner") == ("toyota", "4runner", None)


def test_parse_space_separated_label_still_works():
    # Stanford-Cars style labels must keep working.
    assert parse_vehicle_make_model_year("Toyota Camry Sedan 2019") == ("toyota", "camry sedan", "2019")
    assert parse_vehicle_make_model_year("Acura RL Sedan 2012") == ("acura", "rl sedan", "2012")


def test_parse_single_token_has_no_model():
    assert parse_vehicle_make_model_year("ram") == ("ram", None, None)


def test_parse_empty_label():
    assert parse_vehicle_make_model_year("   ") == (None, None, None)


def test_build_metadata_bakes_split_make_model_for_slugs():
    meta = build_classifier_export_metadata(
        task=DatasetTask.vehicle_make_model_classification,
        classes=["chevrolet_suburban", "ford_f_series", "gmc_yukon"],
    )
    by_label = {r.label: r for r in meta.class_records}
    assert (by_label["chevrolet_suburban"].make, by_label["chevrolet_suburban"].model_label) == ("chevrolet", "suburban")
    assert (by_label["ford_f_series"].make, by_label["ford_f_series"].model_label) == ("ford", "f series")
    assert (by_label["gmc_yukon"].make, by_label["gmc_yukon"].model_label) == ("gmc", "yukon")
