"""Fail-closed logical validation for the canonical website publication."""

from __future__ import annotations

import math
from typing import Any

import estimated_coverage as coverage
import scoring_engine as scoring
from master_dataset import to_scoring_project

REGION_BOUNDS = {"min_lng": -86.0, "max_lng": -78.0, "min_lat": 30.0, "max_lat": 36.0}
MAX_TIMELINE_GAP_YEARS = 2


def _fail(message: str) -> None:
    raise ValueError(f"Invalid canonical publication: {message}")


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _pair(value: Any, label: str) -> tuple[float, float]:
    if not isinstance(value, list) or len(value) < 2 or not all(_number(item) for item in value[:2]):
        _fail(f"{label} must be a finite [longitude, latitude] coordinate")
    lng, lat = float(value[0]), float(value[1])
    if not (REGION_BOUNDS["min_lng"] <= lng <= REGION_BOUNDS["max_lng"]):
        _fail(f"{label} longitude is outside the SC/GA planning region")
    if not (REGION_BOUNDS["min_lat"] <= lat <= REGION_BOUNDS["max_lat"]):
        _fail(f"{label} latitude is outside the SC/GA planning region")
    return lng, lat


def geometry_points(geometry: Any, label: str) -> list[tuple[float, float]]:
    if not isinstance(geometry, dict):
        _fail(f"{label} geometry must be a GeoJSON object")
    kind, coordinates = geometry.get("type"), geometry.get("coordinates")
    if kind == "Point":
        return [_pair(coordinates, label)]
    if kind == "LineString":
        if not isinstance(coordinates, list) or not coordinates:
            _fail(f"{label} LineString must contain coordinates")
        return [_pair(point, label) for point in coordinates]
    if kind == "MultiLineString":
        if not isinstance(coordinates, list) or not coordinates:
            _fail(f"{label} MultiLineString must contain lines")
        points = [
            _pair(point, label)
            for line in coordinates
            if isinstance(line, list)
            for point in line
        ]
        if not points:
            _fail(f"{label} MultiLineString must contain coordinates")
        return points
    _fail(f"{label} has unsupported geometry type {kind!r}")


def _validate_years(project: dict[str, Any]) -> None:
    values = [
        project.get("planned_start_year"),
        project.get("planned_end_year"),
        project.get("in_service_year"),
    ]
    for value in values:
        if value is not None and (not isinstance(value, int) or isinstance(value, bool) or not 2000 <= value <= 2100):
            _fail(f"{project['project_id']} has an invalid project year")
    present = [value for value in values if value is not None]
    if not present:
        return
    start, end, in_service = values
    if start is not None and end is not None and start > end:
        _fail(f"{project['project_id']} starts after it ends")
    if start is not None and in_service is not None and in_service < start:
        _fail(f"{project['project_id']} enters service before it starts")
    if end is not None and in_service is not None and in_service < end:
        _fail(f"{project['project_id']} enters service before planned work ends")


def _validate_master_project(project: dict[str, Any]) -> None:
    _validate_years(project)
    verified = project.get("verified_geometry")
    estimated = project.get("estimated_geometry")
    analysis = project.get("analysis_geometry")
    expected = verified or estimated
    expected_status = "VERIFIED" if verified else "ESTIMATED" if estimated else "UNRESOLVED"
    if project.get("geometry_status") != expected_status or analysis != expected:
        _fail(f"{project['project_id']} violates verified-first geometry precedence")
    if analysis is not None:
        geometry_points(analysis, project["project_id"])


def _point_latlng(value: Any, label: str) -> None:
    if not isinstance(value, dict) or not _number(value.get("lat")) or not _number(value.get("lng")):
        _fail(f"{label} must contain finite lat/lng")
    _pair([value["lng"], value["lat"]], label)


def validate_publication(master: dict[str, Any], website: dict[str, Any]) -> None:
    """Validate identities, dates, places, geometry, pair distances, and timeline eligibility."""
    projects = master.get("projects")
    if not isinstance(projects, list) or master.get("total_projects") != len(projects):
        _fail("master project count is inconsistent")
    ids = [project.get("project_id") for project in projects]
    if any(not isinstance(project_id, str) or not project_id for project_id in ids):
        _fail("every project needs a stable ID")
    if len(ids) != len(set(ids)):
        _fail("project IDs must be unique")
    for project in projects:
        if project.get("utility") not in {"DESC", "GPC"}:
            _fail(f"{project['project_id']} has an unsupported utility")
        _validate_master_project(project)

    if any(website.get(key) != master.get(key) for key in ("dataset_version", "pipeline_commit", "generated_at")):
        _fail("website and master metadata do not identify the same publication")
    policy = website.get("opportunity_policy")
    if policy != {
        "distance_km_lt": 40,
        "timeline_gap_years_lte": MAX_TIMELINE_GAP_YEARS,
        "unknown_timing_eligible": False,
    }:
        _fail("website opportunity policy is missing or unsupported")

    canonical = {project["project_id"]: to_scoring_project(project) for project in projects}
    web_projects = website.get("projects")
    if not isinstance(web_projects, list) or {project.get("id") for project in web_projects} != set(canonical):
        _fail("website catalog IDs differ from the master catalog")
    for project in web_projects:
        source = canonical[project["id"]]
        for key in (
            "name",
            "utility",
            "planned_start_year",
            "planned_end_year",
            "in_service_year",
            "geometry_status",
            "geometry",
        ):
            if project.get(key) != source.get(key):
                _fail(f"website project {project['id']} has mismatched {key}")

    full = website.get("modes", {}).get("full", {})
    matches = full.get("matches")
    if not isinstance(matches, list):
        _fail("full mode matches must be an array")
    seen_pairs: set[tuple[str, str]] = set()
    seen_match_ids: set[str] = set()
    for match in matches:
        match_id = match.get("match_id")
        if not isinstance(match_id, str) or not match_id or match_id in seen_match_ids:
            _fail("opportunity IDs must be present and unique")
        seen_match_ids.add(match_id)
        a_id, b_id = match.get("project_a_id"), match.get("project_b_id")
        if a_id not in canonical or b_id not in canonical or a_id == b_id:
            _fail(f"{match_id} references an unknown or identical project")
        pair = tuple(sorted((a_id, b_id)))
        if pair in seen_pairs:
            _fail(f"{match_id} duplicates a project pair")
        seen_pairs.add(pair)
        a, b = canonical[a_id], canonical[b_id]
        if {a.get("utility"), b.get("utility")} != {"DESC", "GPC"}:
            _fail(f"{match_id} is not a cross-utility pair")
        if not all(project.get("geometry_status") in {"VERIFIED", "ESTIMATED"} for project in (a, b)):
            _fail(f"{match_id} uses unresolved geometry")

        overlap, gap, overlap_years = scoring.timeline_relationship(a, b)
        if gap is None or gap > MAX_TIMELINE_GAP_YEARS:
            _fail(f"{match_id} is not schedule-aligned")
        if match.get("timeline_overlap") != overlap or match.get("timeline_gap_years") != gap:
            _fail(f"{match_id} has stale timeline analysis")
        if match.get("overlap_years") != overlap_years:
            _fail(f"{match_id} has stale overlap years")

        a_parts = coverage.parts_from_geometry(a.get("geometry"), a.get("geometry_type"))
        b_parts = coverage.parts_from_geometry(b.get("geometry"), b.get("geometry_type"))
        distance, intersects, closest_a, closest_b = coverage.closest_distance_km(a_parts, b_parts)
        if distance >= 40 or abs(match.get("distance_km", math.inf) - round(distance, 2)) > 0.001:
            _fail(f"{match_id} has stale or out-of-policy distance")
        tier, label, blocked = coverage.eligible_tier(distance, intersects, a, b)
        if (
            match.get("distance_tier") != tier
            or match.get("distance_tier_label") != label
            or bool(match.get("close_tier_blocked")) != blocked
        ):
            _fail(f"{match_id} has stale distance-tier analysis")
        for key, expected in (("closest_point_a", closest_a), ("closest_point_b", closest_b)):
            actual = match.get(key) or match.get("closest_points", {}).get(key[-1])
            _point_latlng(actual, f"{match_id}.{key}")
            if abs(actual["lat"] - expected["lat"]) > 1e-8 or abs(actual["lng"] - expected["lng"]) > 1e-8:
                _fail(f"{match_id} has stale closest-point analysis")

    summary = full.get("summary", {})
    if summary.get("schedule_aligned_opportunities") != len(matches):
        _fail("schedule-aligned opportunity count is inconsistent")
