"""
Gridlock Challenge — coordination engine (product layer).

Reads trusted (or explicitly labeled demo) project records, compares every
DESC × GPC pair using closest-point distance, applies the challenge distance
tiers, then ranks remaining pairs with geography first and timeline second.

Does not scrape documents, invent coordinates, or label placeholder data as
verified. Real records belong in data/verified_projects.json.

Requires: shapely
    pip install shapely

Run:
    python scoring_engine.py
    python scoring_engine.py --demo
    python scoring_engine.py --input data/verified_projects.json --output data/analysis.json
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path

from shapely.geometry import LineString
from shapely.ops import nearest_points

from master_dataset import scoring_projects

EARTH_RADIUS_KM = 6371.0088
TOUCHING_EPS_KM = 1e-6
COMPARE_UTILITIES = ("DESC", "GPC")

# Challenge tiers. Boundaries are exclusive on the right except touching:
#   0 / crossing → Must coordinate
#   < 1.6 km     → Shared land / ROW potential
#   < 8 km       → Shared site logistics potential
#   < 40 km      → Shared crews / equipment potential
#   >= 40 km     → excluded
TIER_MUST = "must_coordinate"
TIER_LAND = "shared_land_row"
TIER_LOGISTICS = "shared_site_logistics"
TIER_CREWS = "shared_crews_equipment"

TIER_LABELS = {
    TIER_MUST: "Must coordinate",
    TIER_LAND: "Shared land / ROW potential",
    TIER_LOGISTICS: "Shared site logistics potential",
    TIER_CREWS: "Shared crews / equipment potential",
}

# Geography is the primary rank. Timeline can never outrank a closer tier.
TIER_GEO_SCORE = {
    TIER_MUST: 400,
    TIER_LAND: 300,
    TIER_LOGISTICS: 200,
    TIER_CREWS: 100,
}
TIMELINE_OVERLAP_BONUS = 10

# Legacy aliases so the existing frontend and demo JSON stay readable.
TIER_LEGACY_KEY = {
    TIER_MUST: "touching_crossing",
    TIER_LAND: "shared_land",
    TIER_LOGISTICS: "shared_logistics",
    TIER_CREWS: "shared_crews",
}

# Illustrative only, and only attached in demo mode. Not verified utility costs.
SAVINGS_RANGE_USD = {
    TIER_MUST: (250_000, 600_000),
    TIER_LAND: (150_000, 400_000),
    TIER_LOGISTICS: (75_000, 200_000),
    TIER_CREWS: (25_000, 90_000),
}

CONFIDENCE_VALUES = {"HIGH", "MEDIUM", "LOW"}


# ---------------------------------------------------------------------------
# Geometry: project lat/lng into a local flat (km, km) plane, then let
# shapely measure true closest-point distance. Same method as the original
# prototype (equirectangular, pair-centered).
# ---------------------------------------------------------------------------

def latlng_to_km(lat, lng, ref_lat):
    x = lng * EARTH_RADIUS_KM * math.pi / 180 * math.cos(math.radians(ref_lat))
    y = lat * EARTH_RADIUS_KM * math.pi / 180
    return x, y


def km_to_latlng(x, y, ref_lat):
    lat = y / (EARTH_RADIUS_KM * math.pi / 180)
    lng = x / (EARTH_RADIUS_KM * math.pi / 180 * math.cos(math.radians(ref_lat)))
    return lat, lng


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _as_lnglat_pair(value):
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return None
    lng, lat = value[0], value[1]
    if not (_is_number(lng) and _is_number(lat)):
        return None
    return float(lng), float(lat)


def extract_latlng_points(project):
    """
    Return a list of (lat, lng) vertices, or None if geometry is missing.

    Accepts product-schema geometry (GeoJSON order: lng, lat), a GeoJSON
    object, or legacy lat1/lng1/lat2/lng2 fields. Does not invent points.
    """
    geom = project.get("geometry")
    geom_type = project.get("geometry_type")

    if isinstance(geom, dict) and geom.get("coordinates") is not None:
        geom_type = geom.get("type") or geom_type
        geom = geom.get("coordinates")

    points = None

    if geom is not None:
        pair = _as_lnglat_pair(geom)
        if pair is not None and geom_type in (None, "Point"):
            lng, lat = pair
            points = [(lat, lng)]
        elif isinstance(geom, list) and geom:
            parsed = []
            for vertex in geom:
                pair = _as_lnglat_pair(vertex)
                if pair is None:
                    parsed = []
                    break
                lng, lat = pair
                parsed.append((lat, lng))
            if parsed:
                points = parsed

    if points is None and _is_number(project.get("lat1")) and _is_number(project.get("lng1")):
        points = [(float(project["lat1"]), float(project["lng1"]))]
        if _is_number(project.get("lat2")) and _is_number(project.get("lng2")):
            lat2, lng2 = float(project["lat2"]), float(project["lng2"])
            if (lat2, lng2) != points[0]:
                points.append((lat2, lng2))

    return points or None


def project_line_km(points_latlng, ref_lat):
    coords = [latlng_to_km(lat, lng, ref_lat) for lat, lng in points_latlng]
    if len(coords) == 1:
        return LineString([coords[0], coords[0]])
    return LineString(coords)


def classify_tier(distance_km, intersects=False):
    """Return (tier_key, label) or (None, None) when the pair is out of scope."""
    if intersects or distance_km <= TOUCHING_EPS_KM:
        return TIER_MUST, TIER_LABELS[TIER_MUST]
    if distance_km < 1.6:
        return TIER_LAND, TIER_LABELS[TIER_LAND]
    if distance_km < 8.0:
        return TIER_LOGISTICS, TIER_LABELS[TIER_LOGISTICS]
    if distance_km < 40.0:
        return TIER_CREWS, TIER_LABELS[TIER_CREWS]
    return None, None


def years_overlap(a_start, a_end, b_start, b_end):
    lo, hi = max(a_start, b_start), min(a_end, b_end)
    if lo <= hi:
        return True, [int(lo), int(hi)]
    return False, None


def _optional_year(*values):
    for value in values:
        if _is_number(value):
            return int(value)
    return None


def project_year_window(project):
    """
    Comparison window only. Missing years stay missing — we do not invent them.

    Uses planned_start_year / planned_end_year when present, then legacy
    start_year / end_year, then in_service_year as a one-year window.
    """
    start = _optional_year(project.get("planned_start_year"), project.get("start_year"))
    end = _optional_year(project.get("planned_end_year"), project.get("end_year"))
    in_service = _optional_year(project.get("in_service_year"))

    if start is None and end is None:
        if in_service is None:
            return None, None
        return in_service, in_service
    if start is None:
        start = end
    if end is None:
        end = start
    if start > end:
        start, end = end, start
    return start, end


def timeline_relationship(project_a, project_b):
    a_start, a_end = project_year_window(project_a)
    b_start, b_end = project_year_window(project_b)
    if a_start is None or b_start is None:
        return False, None, None
    overlap, overlap_years = years_overlap(a_start, a_end, b_start, b_end)
    if overlap:
        return True, 0, overlap_years
    gap = max(a_start, b_start) - min(a_end, b_end)
    return False, int(gap), None


def score_match(tier_key, timeline_overlap):
    geo = TIER_GEO_SCORE.get(tier_key, 0)
    bonus = TIMELINE_OVERLAP_BONUS if timeline_overlap else 0
    return geo + bonus


def priority_explanation(tier_label, distance_km, timeline_overlap, timeline_gap_years, score):
    geo = score - (TIMELINE_OVERLAP_BONUS if timeline_overlap else 0)
    parts = [
        f"Geography first: {tier_label} at {distance_km:.2f} km ({geo} pts)."
    ]
    if timeline_overlap:
        parts.append(f"Timeline overlaps (+{TIMELINE_OVERLAP_BONUS} pts).")
    elif timeline_gap_years is None:
        parts.append("Timeline unknown (0 pts; years were not provided).")
    else:
        parts.append(f"Timeline gap of {timeline_gap_years} year(s) (0 pts).")
    parts.append(f"Priority score {score} = geography + timeline.")
    return " ".join(parts)


def estimate_savings(tier_key):
    lo, hi = SAVINGS_RANGE_USD.get(tier_key, (0, 0))
    return {
        "low_usd": lo,
        "high_usd": hi,
        "assumption": (
            "Illustrative estimate of avoided duplicate mobilization/staging "
            "cost — not a verified utility cost figure."
        ),
    }


def coordination_brief(a, b, distance_km, tier_label, timeline_overlap, overlap_years, timeline_gap_years):
    lines = [
        f"{a['utility']} – {a['name']}  <->  {b['utility']} – {b['name']}",
        f"Why coordinate: {tier_label} ({distance_km:.2f} km apart, closest point to closest point).",
    ]
    if timeline_overlap and overlap_years:
        lines.append(f"Build windows overlap in {overlap_years[0]}-{overlap_years[1]}.")
    elif timeline_gap_years is None:
        lines.append("Timing is unknown for at least one project — not treated as overlap.")
    else:
        lines.append(
            "Same area, different timing — build windows don't overlap "
            f"(gap of {timeline_gap_years} year(s)). "
            "Worth asking whether either utility's schedule could be adjusted."
        )
    lines.append("Next action: share this brief with both utilities' regional planning contacts.")
    return "\n".join(lines)


def _voltage_list(value):
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [v for v in value if _is_number(v)]
    if _is_number(value):
        return [value]
    return []


def normalize_project(raw, dataset="verified"):
    """Project-facing record. Optional fields stay null when absent."""
    points = extract_latlng_points(raw)
    geom_type = raw.get("geometry_type")
    geometry = raw.get("geometry")

    if isinstance(geometry, dict) and geometry.get("coordinates") is not None:
        geom_type = geometry.get("type") or geom_type
        geometry = geometry.get("coordinates")

    if points is not None:
        lnglat = [[lng, lat] for lat, lng in points]
        if geom_type not in ("Point", "LineString"):
            geom_type = "Point" if len(points) == 1 else "LineString"
        if geometry is None:
            geometry = lnglat[0] if geom_type == "Point" else lnglat
        lat1, lng1 = points[0]
        lat2, lng2 = points[-1]
    else:
        geom_type = geom_type if geom_type in ("Point", "LineString") else None
        geometry = None
        lat1 = lng1 = lat2 = lng2 = None

    planned_start = _optional_year(raw.get("planned_start_year"), raw.get("start_year"))
    planned_end = _optional_year(raw.get("planned_end_year"), raw.get("end_year"))
    in_service = _optional_year(raw.get("in_service_year"))
    window_start, window_end = project_year_window(raw)

    confidence = raw.get("data_confidence")
    if confidence not in CONFIDENCE_VALUES:
        confidence = "LOW" if dataset == "demo" else None

    geometry_confidence = raw.get("geometry_confidence")
    if geometry_confidence not in CONFIDENCE_VALUES:
        geometry_confidence = None

    return {
        "id": raw.get("id"),
        "utility": raw.get("utility"),
        "name": raw.get("name"),
        "project_type": raw.get("project_type") if raw.get("project_type") not in ("", None) else None,
        "planned_start_year": planned_start,
        "planned_end_year": planned_end,
        "in_service_year": in_service,
        "voltage_kv": _voltage_list(raw.get("voltage_kv")),
        "geometry": geometry,
        "geometry_type": geom_type,
        "source_url": raw.get("source_url") or None,
        "source_page": raw.get("source_page") if raw.get("source_page") not in ("", None) else None,
        "data_confidence": confidence,
        "geometry_source": raw.get("geometry_source") or None,
        "geometry_method": raw.get("geometry_method") or None,
        "geometry_confidence": geometry_confidence,
        "geometry_notes": raw.get("geometry_notes") or None,
        "geometry_status": raw.get("geometry_status") or None,
        "estimated_geometry": bool(raw.get("estimated_geometry")),
        "lat1": lat1,
        "lng1": lng1,
        "lat2": lat2,
        "lng2": lng2,
        "start_year": window_start,
        "end_year": window_end,
        "has_geometry": points is not None,
    }


def is_desc_gpc_pair(project_a, project_b):
    return {project_a.get("utility"), project_b.get("utility")} == set(COMPARE_UTILITIES)


def pair_projects(desc_project, gpc_project):
    """DESC is always project_a; GPC is always project_b."""
    if desc_project.get("utility") == "DESC" and gpc_project.get("utility") == "GPC":
        return desc_project, gpc_project
    if desc_project.get("utility") == "GPC" and gpc_project.get("utility") == "DESC":
        return gpc_project, desc_project
    raise ValueError("pair_projects expects one DESC and one GPC project")


def compare_pair(project_a, project_b):
    """
    Closest-point comparison for one DESC × GPC pair.

    Returns a match dict, or None when the pair is out of scope (>= 40 km
    or missing geometry).
    """
    if not is_desc_gpc_pair(project_a, project_b):
        return None

    a, b = pair_projects(project_a, project_b)
    points_a = extract_latlng_points(a)
    points_b = extract_latlng_points(b)
    if not points_a or not points_b:
        return None

    ref_lat = sum(lat for lat, _lng in points_a + points_b) / float(len(points_a) + len(points_b))
    line_a = project_line_km(points_a, ref_lat)
    line_b = project_line_km(points_b, ref_lat)
    distance_km = float(line_a.distance(line_b))
    intersects = bool(line_a.intersects(line_b))
    tier_key, tier_label = classify_tier(distance_km, intersects=intersects)
    if tier_key is None:
        return None

    overlap, gap, overlap_years = timeline_relationship(a, b)
    score = score_match(tier_key, overlap)
    pt_a, pt_b = nearest_points(line_a, line_b)
    closest_a = dict(zip(("lat", "lng"), km_to_latlng(pt_a.x, pt_a.y, ref_lat)))
    closest_b = dict(zip(("lat", "lng"), km_to_latlng(pt_b.x, pt_b.y, ref_lat)))
    years_a = list(project_year_window(a))
    years_b = list(project_year_window(b))
    if years_a[0] is None:
        years_a = None
    if years_b[0] is None:
        years_b = None

    return {
        "project_a_id": a.get("id"),
        "project_b_id": b.get("id"),
        "project_a": a,
        "project_b": b,
        "distance_km": round(distance_km, 2),
        "distance_tier": tier_key,
        "distance_tier_label": tier_label,
        "timeline_overlap": overlap,
        "timeline_gap_years": gap,
        "priority_score": score,
        "priority_explanation": priority_explanation(tier_label, distance_km, overlap, gap, score),
        "closest_points": {
            "a": closest_a,
            "b": closest_b,
        },
        "tier": TIER_LEGACY_KEY[tier_key],
        "tier_label": tier_label,
        "years_a": years_a,
        "years_b": years_b,
        "overlap_years": overlap_years,
        "closest_point_a": closest_a,
        "closest_point_b": closest_b,
        "score": score,
        "coordination_brief": coordination_brief(
            a, b, distance_km, tier_label, overlap, overlap_years, gap
        ),
    }


def rank_matches(matches):
    """Deterministic: higher score, then closer, then stable ids."""
    return sorted(
        matches,
        key=lambda m: (
            -m["priority_score"],
            m["distance_km"],
            str(m.get("project_a_id") or ""),
            str(m.get("project_b_id") or ""),
        ),
    )


def detect_dataset(payload, input_path, explicit=None):
    if explicit:
        return explicit
    if isinstance(payload, dict) and payload.get("dataset") in ("demo", "verified"):
        return payload["dataset"]
    name = Path(input_path).name
    if name in {"projects.json", "demo_projects.json"}:
        return "demo"
    return "verified"


def load_projects(path, mode="verified"):
    with open(path) as handle:
        data = json.load(handle)
    if isinstance(data, list):
        return {"dataset": "verified", "projects": data}
    if data.get("projects") and data.get("dataset_version") and data.get("total_projects") is not None:
        return {
            "dataset": "verified" if mode == "verified" else "estimated",
            "projects": scoring_projects(data, mode),
        }
    projects = data.get("projects")
    if projects is None:
        raise ValueError(f"{path} must contain a 'projects' array")
    return data


def empty_summary():
    return {
        "total_projects": 0,
        "desc_projects": 0,
        "gpc_projects": 0,
        "pairs_checked": 0,
        "pairs_within_40km": 0,
        "pairs_with_timeline_overlap": 0,
        "projects_without_geometry": 0,
        "projects_without_timing": 0,
    }


def analyze_projects(raw_projects, dataset="verified"):
    normalized = []
    for raw in raw_projects:
        utility = raw.get("utility")
        if utility not in COMPARE_UTILITIES:
            continue
        if not raw.get("id") or not raw.get("name"):
            continue
        normalized.append(normalize_project(raw, dataset=dataset))

    desc = [p for p in normalized if p["utility"] == "DESC"]
    gpc = [p for p in normalized if p["utility"] == "GPC"]

    matches = []
    pairs_checked = 0
    for a in desc:
        for b in gpc:
            if not a["has_geometry"] or not b["has_geometry"]:
                continue
            pairs_checked += 1
            match = compare_pair(a, b)
            if match is None:
                continue
            matches.append(match)

    matches = rank_matches(matches)
    for index, match in enumerate(matches, start=1):
        match["match_id"] = f"m{index:03d}"
        if dataset == "demo":
            match["est_savings_usd"] = estimate_savings(match["distance_tier"])

    summary = {
        "total_projects": len(normalized),
        "desc_projects": len(desc),
        "gpc_projects": len(gpc),
        "pairs_checked": pairs_checked,
        "pairs_within_40km": len(matches),
        "pairs_with_timeline_overlap": sum(1 for m in matches if m["timeline_overlap"]),
        "projects_without_geometry": sum(1 for p in normalized if not p["has_geometry"]),
        "projects_without_timing": sum(
            1 for p in normalized if project_year_window(p)[0] is None
        ),
    }
    return normalized, matches, summary


def build_output(normalized, matches, summary, dataset):
    disclaimer = (
        "Verified product dataset. Records should come from gridlock-data-pipeline. "
        "Missing geometry or years are left blank and are not invented."
        if dataset == "verified"
        else (
            "DEMO / LEGACY dataset. Coordinates are approximate placeholders. "
            "Do not present these results as verified DESC or Georgia Power data."
        )
    )
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": dataset,
        "data_source": dataset,
        "data_disclaimer": disclaimer,
        "utilities": list(COMPARE_UTILITIES),
        "input_project_count": summary["total_projects"],
        "match_count": summary["pairs_within_40km"],
        "summary": summary,
        "projects": normalized,
        "matches": matches,
    }


def run(input_path, output_path, dataset=None, mode="verified"):
    payload = load_projects(input_path, mode=mode)
    dataset = detect_dataset(payload, input_path, explicit=dataset)
    raw_projects = payload.get("projects") or []
    normalized, matches, summary = analyze_projects(raw_projects, dataset=dataset)
    output = build_output(normalized, matches, summary, dataset)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as handle:
        json.dump(output, handle, indent=2, default=str)
        handle.write("\n")

    print(
        f"{summary['total_projects']} projects in -> "
        f"{summary['pairs_checked']} DESC×GPC pairs checked -> "
        f"{summary['pairs_within_40km']} within 40 km -> {output_path}"
    )
    if matches:
        top = matches[0]
        print(
            f"Top match: {top['project_a']['name']} <-> {top['project_b']['name']} "
            f"({top['distance_tier']}, {top['distance_km']} km, score {top['priority_score']})"
        )
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/published/gridlock_master_projects.json")
    parser.add_argument("--output", default="data/published/scoring_verified.json")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Score labeled demo/legacy data (data/projects.json → data/demo_analysis.json)",
    )
    parser.add_argument("--dataset", choices=("verified", "demo"), default=None)
    parser.add_argument("--mode", choices=("verified", "full"), default="verified")
    args = parser.parse_args()
    input_path = args.input
    output_path = args.output
    dataset = args.dataset
    if args.demo:
        if args.input == "data/published/gridlock_master_projects.json":
            input_path = "data/projects.json"
        if args.output == "data/published/scoring_verified.json":
            output_path = "data/demo_analysis.json"
        dataset = dataset or "demo"
    run(input_path, output_path, dataset=dataset, mode=args.mode)
