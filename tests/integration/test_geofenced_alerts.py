"""Geofenced make/model alerts: zone membership, profile match + scoring, and
the 2-tier evaluate (CONFIRMED plate vs IN-ZONE LEAD)."""

from __future__ import annotations

from reposcan_contracts.config.loader import load_pipeline_config
from reposcan_contracts.detection import BoundingBox, PlateCandidate
from reposcan_contracts.hotlist import HotlistEntry
from reposcan_contracts.inference import AttributePredictions
from reposcan_contracts.tracking import TrackedDetection
from reposcan_contracts.types import HotlistMatchKind
from reposcan_alerting.geo import entries_within_zone, haversine_feet
from reposcan_alerting.service import AlertingService


PIPELINE = "configs/pipelines/default-edge.yaml"
# Target address (a lot in Oklahoma City) and a point ~150 ft away.
TARGET_LAT, TARGET_LON = 35.4676, -97.5164
NEAR_LAT, NEAR_LON = 35.46801, -97.5164  # ~150 ft north
FAR_LAT, FAR_LON = 35.4900, -97.5164  # ~1.6 mi north


def _service() -> AlertingService:
    return AlertingService(load_pipeline_config(PIPELINE))


def _entry(**kw) -> HotlistEntry:
    base = dict(
        entry_id="e1",
        active=True,
        created_at_utc="2026-06-03T00:00:00Z",
        updated_at_utc="2026-06-03T00:00:00Z",
    )
    base.update(kw)
    return HotlistEntry(**base)


def _tracked(*, plate: str | None, attrs: AttributePredictions | None) -> TrackedDetection:
    return TrackedDetection(
        detection_id="d1",
        tracker_id="t1",
        camera_id="cam_01",
        timestamp_utc="2026-06-03T12:00:00Z",
        vehicle_bbox=BoundingBox(x=0, y=0, w=100, h=80),
        frame_number=0,
        best_plate_candidate=PlateCandidate(text=plate, confidence=0.97) if plate else None,
        vehicle_attributes=attrs,
    )


# --- geofence helper -------------------------------------------------------


def test_haversine_feet_reasonable():
    d = haversine_feet(TARGET_LAT, TARGET_LON, NEAR_LAT, NEAR_LON)
    assert 100 < d < 200  # ~150 ft


def test_entries_within_zone_membership():
    near = _entry(entry_id="near", vehicle_make="Chevrolet", vehicle_model="Suburban",
                  address_latitude=TARGET_LAT, address_longitude=TARGET_LON)
    far = _entry(entry_id="far", vehicle_make="Ford", vehicle_model="F Series",
                 address_latitude=FAR_LAT, address_longitude=FAR_LON)
    no_coords = _entry(entry_id="nocoord", vehicle_make="Honda", vehicle_model="Pilot")
    in_zone = entries_within_zone(NEAR_LAT, NEAR_LON, [near, far, no_coords], radius_feet=300)
    assert in_zone == {"near"}


# --- profile matching + scoring -------------------------------------------


def test_profile_requires_make_and_model():
    svc = _service()
    entry = _entry(vehicle_make="Chevrolet", vehicle_model="Suburban",
                   address_latitude=TARGET_LAT, address_longitude=TARGET_LON)
    # make matches, model differs -> no match
    attrs = AttributePredictions(make="chevrolet", model="tahoe")
    result, matched = svc.match_profile_in_zone(attrs, [entry], {"e1"})
    assert result.matched is False and matched is None


def test_profile_scores_color_and_year_bonus():
    svc = _service()
    entry = _entry(vehicle_make="Chevrolet", vehicle_model="Suburban", vehicle_color="white",
                   vehicle_year="2019", address_latitude=TARGET_LAT, address_longitude=TARGET_LON)
    base = AttributePredictions(make="Chevrolet", model="Suburban")
    full = AttributePredictions(make="Chevrolet", model="Suburban", color="White", year="2019")

    r_base, _ = svc.match_profile_in_zone(base, [entry], {"e1"})
    r_full, _ = svc.match_profile_in_zone(full, [entry], {"e1"})

    assert r_base.matched and abs(r_base.score - 0.6) < 1e-6
    assert r_base.matched_dimensions == ["make", "model"]
    assert r_full.matched and abs(r_full.score - 1.0) < 1e-6
    assert r_full.matched_dimensions == ["make", "model", "color", "year"]


def test_profile_ignores_out_of_zone_entries():
    svc = _service()
    entry = _entry(vehicle_make="Chevrolet", vehicle_model="Suburban",
                   address_latitude=TARGET_LAT, address_longitude=TARGET_LON)
    attrs = AttributePredictions(make="chevrolet", model="suburban")
    # entry exists but is NOT in the in-zone set -> no lead
    result, matched = svc.match_profile_in_zone(attrs, [entry], set())
    assert result.matched is False and matched is None


# --- 2-tier evaluate -------------------------------------------------------


def test_evaluate_confirmed_plate_takes_priority():
    svc = _service()
    entry = _entry(plate_text="ABC123", vehicle_make="Chevrolet", vehicle_model="Suburban",
                   address_latitude=TARGET_LAT, address_longitude=TARGET_LON)
    det = _tracked(plate="ABC123", attrs=AttributePredictions(make="chevrolet", model="suburban"))
    alert = svc.evaluate(det, [entry], in_zone_entry_ids={"e1"})
    assert alert is not None
    assert alert.match_kind == HotlistMatchKind.plate
    assert alert.matched_plate_text == "ABC123"


def test_evaluate_in_zone_lead_when_no_plate_match():
    svc = _service()
    entry = _entry(vehicle_make="Chevrolet", vehicle_model="Suburban", vehicle_color="white",
                   address_latitude=TARGET_LAT, address_longitude=TARGET_LON)
    # plate read but does not match any entry; make/model match in zone
    det = _tracked(plate="ZZZ999", attrs=AttributePredictions(make="chevrolet", model="suburban", color="white"))
    alert = svc.evaluate(det, [entry], in_zone_entry_ids={"e1"})
    assert alert is not None
    assert alert.match_kind == HotlistMatchKind.in_zone_profile
    assert alert.match_type is None
    assert "make" in alert.matched_attributes and "color" in alert.matched_attributes
    assert abs(alert.match_confidence - 0.8) < 1e-6


def test_evaluate_no_lead_without_zone_context():
    # Backward compatible: no in_zone_entry_ids -> profile never fires.
    svc = _service()
    entry = _entry(vehicle_make="Chevrolet", vehicle_model="Suburban",
                   address_latitude=TARGET_LAT, address_longitude=TARGET_LON)
    det = _tracked(plate="ZZZ999", attrs=AttributePredictions(make="chevrolet", model="suburban"))
    assert svc.evaluate(det, [entry]) is None


# --- ephemeral quick-scan target ------------------------------------------


def test_quick_target_blank_is_plain_navigation():
    from reposcan_contracts.hotlist import QuickScanTarget

    target = QuickScanTarget(address_label="123 Main St", arm_mode="in_zone")
    assert target.has_scan_criteria() is False
    assert target.to_hotlist_entry(entry_id="q", timestamp="2026-06-03T00:00:00Z") is None


def test_quick_target_manual_scans_everywhere():
    from reposcan_contracts.hotlist import QuickScanTarget

    svc = _service()
    # Manual arm, no address, unit position far from anything -> still fires.
    target = QuickScanTarget(vehicle_make="Chevrolet", vehicle_model="Suburban", arm_mode="manual")
    det = _tracked(plate=None, attrs=AttributePredictions(make="chevrolet", model="suburban"))
    alert = svc.evaluate_quick_target(det, target, unit_latitude=FAR_LAT, unit_longitude=FAR_LON)
    assert alert is not None
    assert alert.match_kind == HotlistMatchKind.in_zone_profile


def test_quick_target_in_zone_requires_proximity():
    from reposcan_contracts.hotlist import QuickScanTarget

    svc = _service()
    target = QuickScanTarget(
        vehicle_make="Chevrolet", vehicle_model="Suburban", arm_mode="in_zone",
        address_latitude=TARGET_LAT, address_longitude=TARGET_LON,
    )
    det = _tracked(plate=None, attrs=AttributePredictions(make="chevrolet", model="suburban"))

    # Far away -> no alert.
    assert svc.evaluate_quick_target(det, target, unit_latitude=FAR_LAT, unit_longitude=FAR_LON, zone_radius_feet=300) is None
    # Inside the zone -> in-zone lead.
    near = svc.evaluate_quick_target(det, target, unit_latitude=NEAR_LAT, unit_longitude=NEAR_LON, zone_radius_feet=300)
    assert near is not None and near.match_kind == HotlistMatchKind.in_zone_profile


def test_quick_target_plate_match_confirmed_anywhere():
    from reposcan_contracts.hotlist import QuickScanTarget

    svc = _service()
    target = QuickScanTarget(plate_text="abc123", plate_state="ok", arm_mode="manual")
    assert target.plate_text == "ABC123" and target.plate_state == "OK"  # normalized
    det = _tracked(plate="ABC123", attrs=None)
    alert = svc.evaluate_quick_target(det, target, unit_latitude=FAR_LAT, unit_longitude=FAR_LON)
    assert alert is not None and alert.match_kind == HotlistMatchKind.plate
