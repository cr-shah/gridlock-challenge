"""
Estimated Coverage mode.

Does not modify verified geometry or the verified distance calculation.
Official coordinates in data/verified_projects.json are copied through unchanged.
Missing geometry may be filled from data/estimated_geometry.json, which is built
only from unique public OSM substations, HIFLD transmission corridors, official
points already in the verified file, or Census county internal points.

Estimated geometry is planning-screening only. It is never written back onto
the verified records.

Run:
    python estimated_coverage.py
    python estimated_coverage.py --rebuild-geometry
"""

from __future__ import annotations

import argparse
import json
import math
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from shapely.geometry import LineString, MultiLineString
from shapely.ops import nearest_points

import scoring_engine as se

ROOT = Path(__file__).resolve().parent
VERIFIED_PATH = ROOT / "data" / "verified_projects.json"
ESTIMATE_PATH = ROOT / "data" / "estimated_geometry.json"
OUTPUT_PATH = ROOT / "data" / "estimated_analysis.json"

DISCLAIMER = (
    "Estimated geometry — planning-screening use only. "
    "Official verified geometry is unchanged. Straight lines connect uniquely "
    "matched public substations. HIFLD corridors are used only for rebuilds "
    "with a unique owner and voltage match. County anchors are low-confidence "
    "screening points and cannot create a close tier."
)

# US Census TIGERweb county layer. Internal points are the published county centroids.
TIGER_COUNTY = (
    "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/"
    "State_County/MapServer/1/query"
)
HIFLD_LINES = (
    "https://services1.arcgis.com/Hp6G80Pky0om7QvQ/arcgis/rest/services/"
    "Electric_Power_Transmission_Lines/FeatureServer/0/query"
)
OVERPASS = "https://overpass-api.de/api/interpreter"

# Savannah city, used only to disambiguate duplicate facility names when the
# project text itself says Savannah. GNIS populated place Savannah, GA.
SAVANNAH_LAT = 32.0809
SAVANNAH_LNG = -81.0912
SAVANNAH_DISAMBIGUATION_KM = 50.0

SC_BOX = (32.00, 35.22, -83.40, -78.50)  # lat min, lat max, lng min, lng max
GA_BOX = (30.35, 35.05, -85.65, -80.75)

CLOSE_METHODS = {
    "approximate_verified_endpoints",
    "existing_corridor_hifld",
    "official_georeferenced_route_map_trace",
    "official_project_route_coordinates",
    "official_project_map_facility_point",
    "public_facility_endpoint_point",
}

CONFIDENCE_PENALTY = {
    "HIGH": 0,
    "MEDIUM": -5,
    "ESTIMATED": -10,
    "LOW": 0,
}

SAVANNAH_PHRASES = (
    "savannah", "chatham", "effingham", "bryan county", "okatie", "jasper",
    "goshen", "mcintosh", "meldrim", "boulevard", "deptford", "coleman",
    "rice hope", "kraft", "rincon", "bluffton", "hardeeville", "yemassee",
    "dean forest",
)

NAME_STOP = {
    "rebuild", "construct", "line", "lines", "kv", "kvs", "the", "and", "for",
    "with", "from", "tie", "tap", "new", "upgrade", "replace", "replacement",
    "section", "sections", "structures", "structure", "add", "sub", "substation",
    "project", "primary", "road", "county", "circuit", "single", "double",
    "spd", "spdc", "acsr", "approx", "miles", "mile",
}

# Documented name aliases. These do not move coordinates.
ALIASES = {
    "VCS1": ["VIRGIL C SUMMER NUCLEAR 1", "V C SUMMER"],
    "VCS2": ["VIRGIL C SUMMER NUCLEAR 2 3"],
    "VC SUMMER": ["V C SUMMER", "VIRGIL C SUMMER NUCLEAR 1"],
    "ST GEORGE": ["SAINT GEORGE"],
    "ST HELENA": ["SAINT HELENA"],
    "GOSHEN SAVANNAH": ["GOSHEN"],
    "WARRENTON PRIMARY": ["WARRENTON PRIMARY"],
    "ORANGEBURG 1": ["ORANGEBURG PRIMARY"],
}

HIFLD_OWNERS = {
    "DESC": ("SOUTH CAROLINA ELECTRIC&GAS COMPANY", "SOUTH CAROLINA ELECTRIC&GAS CO"),
    "GPC": ("GEORGIA POWER CO",),
}

COUNTY_FIPS = {
    ("SC", "Calhoun"): "45",
    ("GA", "Chatham"): "13",
    ("GA", "Bryan"): "13",
    ("GA", "Effingham"): "13",
    ("GA", "McDuffie"): "13",
    ("GA", "Warren"): "13",
    ("GA", "Richmond"): "13",
    ("GA", "Clayton"): "13",
    ("GA", "Henry"): "13",
    ("GA", "Butts"): "13",
    ("GA", "Spalding"): "13",
}


def norm_name(value):
    text = (value or "").upper().replace("&", " AND ")
    # "ST" is an abbreviation of Saint only as its own word. Replacing the
    # letters ST inside FOREST or WEST produced false names such as FORESAINT.
    text = re.sub(r"\bST\.", "SAINT", text)
    text = re.sub(r"\bST\b", "SAINT", text)
    text = re.sub(r"[#/]", " ", text)
    text = re.sub(r"[^A-Z0-9 ]", " ", text)
    text = re.sub(
        r"\b(SUBSTATION|SWITCHING STATION|SWITCHYARD|FACILITY|SUB|THE|PLANT)\b",
        " ",
        text,
    )
    text = re.sub(r"\s+", " ", text).strip()
    return text


def alias_labels(value):
    key = norm_name(value)
    labels = {key} if key else set()
    for alias_key, targets in ALIASES.items():
        if key == norm_name(alias_key):
            labels.update(targets)
    return {label for label in labels if label and not _reject_label(label)}


def _reject_label(label):
    if label in {"NORTH", "SOUTH", "EAST", "WEST", "COUNTY", "UNKNOWN", "NOT AVAILABLE"}:
        return True
    if label.endswith(" COUNTY"):
        return True
    if label.startswith("TAP") or label.startswith("UNKNOWN"):
        return True
    return len(label) < 4


def haversine_km(lat1, lng1, lat2, lng2):
    r = se.EARTH_RADIUS_KM
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlng / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def in_box(lat, lng, box):
    lat0, lat1, lng0, lng1 = box
    return lat0 <= lat <= lat1 and lng0 <= lng <= lng1


def state_boxes(utility):
    if utility == "DESC":
        return SC_BOX, GA_BOX
    return GA_BOX, SC_BOX


# A straight line between two public name matches is not used when the only
# hits sit this far apart, unless a HIFLD corridor confirms the pair. This
# drops a different facility that happens to share a name (Pineland near
# Savannah is not the VCS Pineland). It is not a tier target.
MAX_UNCONFIRMED_ENDPOINT_KM = 150.0

_VOLTAGE_TAIL = re.compile(
    r"\s+\d+(?:\.\d+)?(?:\s*/\s*\d+(?:\.\d+)?)?\s*kV.*$",
    flags=re.I,
)


def _clean_place(value):
    item = _VOLTAGE_TAIL.sub("", value or "").strip(" -–—")
    item = re.sub(
        r"\s+(Rebuild|Reconductor|Construct|Upgrade|Replacement|Section|Tie Lines?)\b.*$",
        "",
        item,
        flags=re.I,
    ).strip()
    if not item or _reject_label(norm_name(item)):
        return None
    # Long planning phrases are not facility names ("Goshen Area Strategic Solution").
    if len(item.split()) > 3:
        return None
    return item


def segment_endpoint(project):
    """
    A named section of a longer rebuild, such as the Rice Hope segment of
    Goshen–Kraft. 'First Segment' is not a facility name.
    """
    head = project["name"].split(":")[0]
    match = re.search(r",\s+(.+?)\s+Segment\s*$", head, flags=re.I)
    if not match:
        return None
    label = match.group(1).strip()
    if norm_name(label) in {"FIRST", "SECOND", "THIRD", "LAST", "NORTH", "SOUTH"}:
        return None
    return _clean_place(label)


def title_groups(project):
    """
    Place-name groups taken from the project title.

    An ampersand separates circuits (VCS1–Denny Terrace & VCS1–Pineland).
    Dashes inside one circuit are that circuit's named points, in order.
    """
    head = project["name"].split(":")[0]
    groups = []
    for segment in re.split(r"\s+&\s+", head):
        segment = _VOLTAGE_TAIL.sub("", segment).strip()
        segment = re.sub(r"Switching-Station", "Switching Station", segment, flags=re.I)
        places = []
        for part in re.split(r"\s*[-–—]\s*", segment):
            place = _clean_place(part)
            if place:
                places.append(place)
        if places:
            groups.append(places)
    segment = segment_endpoint(project)
    if segment and groups and groups[0]:
        # The parent line's far end is not this segment's endpoint.
        groups[0] = [groups[0][0], segment]
    return groups


def subject_facility(project):
    """
    The facility a substation/autotransformer project is about.

    'Rice Hope Autotransformer' is Rice Hope. A different named candidate
    such as McIntosh is not a substitute location for that facility.
    """
    head = project["name"].split(":")[0].strip()
    match = re.match(
        r"(.+?)\s+(New Substation|Autotransformer)$",
        head,
        flags=re.I,
    )
    if not match:
        return None
    place = _clean_place(match.group(1))
    if not place or re.search(r"[-–—]", place):
        return None
    return place


def label_named_in_project(project, label):
    name_tokens = set(norm_name(project.get("name")).split())
    label_tokens = [token for token in norm_name(label).split() if len(token) >= 4]
    return bool(label_tokens) and all(token in name_tokens for token in label_tokens)


def endpoint_labels(project):
    """Title places first, then explicit candidates. Order preserved."""
    raw = []
    for group in title_groups(project):
        raw.extend(group)
    subject = subject_facility(project)
    if subject:
        raw.append(subject)
    raw.extend(project.get("endpoint_candidates") or [])
    ordered = []
    seen = set()
    for item in raw:
        place = _clean_place(str(item))
        if not place:
            continue
        key = norm_name(place)
        if key in seen:
            continue
        seen.add(key)
        ordered.append(place)
    return ordered


def is_rebuild(project):
    kind = (project.get("project_type") or "").lower()
    name = project["name"].lower()
    return (
        "rebuild" in kind
        or "reconductor" in kind
        or "upgrade" in kind
        or "rebuild" in name
        or "reconductor" in name
    )


def parts_from_geometry(geometry, geometry_type):
    """Return lists of (lat, lng) parts. Does not invent vertices."""
    if geometry is None:
        return []
    if isinstance(geometry, dict) and geometry.get("coordinates") is not None:
        geometry_type = geometry.get("type") or geometry_type
        geometry = geometry.get("coordinates")
    if geometry_type == "MultiLineString" or (
        isinstance(geometry, list)
        and geometry
        and isinstance(geometry[0], list)
        and geometry[0]
        and isinstance(geometry[0][0], list)
    ):
        parts = []
        for line in geometry:
            part = []
            for lng, lat in line:
                part.append((float(lat), float(lng)))
            if part:
                parts.append(part)
        return parts
    points = se.extract_latlng_points({"geometry": geometry, "geometry_type": geometry_type})
    if not points:
        return []
    return [points]


def closest_distance_km(parts_a, parts_b):
    """Same local kilometer projection as the verified engine, for any parts."""
    flat = [point for part in parts_a + parts_b for point in part]
    ref_lat = sum(lat for lat, _lng in flat) / float(len(flat))

    def to_shape(parts):
        lines = []
        for part in parts:
            coords = [se.latlng_to_km(lat, lng, ref_lat) for lat, lng in part]
            if len(coords) == 1:
                coords = [coords[0], coords[0]]
            lines.append(LineString(coords))
        if len(lines) == 1:
            return lines[0]
        return MultiLineString(lines)

    shape_a = to_shape(parts_a)
    shape_b = to_shape(parts_b)
    distance_km = float(shape_a.distance(shape_b))
    intersects = bool(shape_a.intersects(shape_b))
    point_a, point_b = nearest_points(shape_a, shape_b)
    closest_a = dict(zip(("lat", "lng"), se.km_to_latlng(point_a.x, point_a.y, ref_lat)))
    closest_b = dict(zip(("lat", "lng"), se.km_to_latlng(point_b.x, point_b.y, ref_lat)))
    return distance_km, intersects, closest_a, closest_b


def close_eligible(project):
    """True when this geometry may support a <8 km, <1.6 km, or touching tier."""
    method = project.get("geometry_method")
    confidence = project.get("geometry_confidence")
    if method == "regional_screening_anchor" or confidence == "LOW":
        return False
    if method == "estimated_facility_point":
        return False
    if project.get("estimated_geometry"):
        return method in ("approximate_verified_endpoints", "existing_corridor_hifld")
    return method in CLOSE_METHODS or confidence in ("HIGH", "MEDIUM")


def eligible_tier(distance_km, intersects, project_a, project_b):
    """
    Geographic tier from the unchanged thresholds.
    LOW and single estimated points cannot be classified as touching, <1.6, or <8.
    A blocked close pair inside 40 km remains a <40 km screening pair.
    """
    tier, label = se.classify_tier(distance_km, intersects=intersects)
    if tier is None:
        return None, None, False
    blocked = (
        tier in (se.TIER_MUST, se.TIER_LAND, se.TIER_LOGISTICS)
        and not (close_eligible(project_a) and close_eligible(project_b))
    )
    if blocked:
        return se.TIER_CREWS, se.TIER_LABELS[se.TIER_CREWS], True
    return tier, label, False


def _penalty(project):
    return CONFIDENCE_PENALTY.get(project.get("geometry_confidence") or "LOW", 0)


def significant_tokens(project):
    blob = " ".join(
        [
            project.get("name") or "",
            " ".join(project.get("endpoint_names") or []),
        ]
    )
    tokens = set()
    for token in re.findall(r"[A-Za-z0-9]+", blob.lower()):
        if token in NAME_STOP or len(token) < 5 or token.isdigit():
            continue
        tokens.add(token)
    return tokens


def savannah_supported(project):
    blob = f"{project.get('name') or ''} {project.get('county_region') or ''}".lower()
    return any(phrase in blob for phrase in SAVANNAH_PHRASES)


def coordination_score(project_a, project_b):
    """Within-tier score. It does not select the distance tier."""
    overlap, gap, _years = se.timeline_relationship(project_a, project_b)
    parts = []
    score = 0
    if overlap:
        score += 20
        parts.append("+20 shared construction year")
    elif gap == 1:
        score += 10
        parts.append("+10 one-year timing gap")
    shared = significant_tokens(project_a) & significant_tokens(project_b)
    if shared:
        score += 10
        parts.append("+10 shared name context (" + ", ".join(sorted(shared)) + ")")
    if savannah_supported(project_a) and savannah_supported(project_b):
        score += 5
        parts.append("+5 Savannah River planning-area context")
    penalty = min(_penalty(project_a), _penalty(project_b))
    if penalty:
        score += penalty
        parts.append(f"{penalty} weaker geometry confidence")
    if not parts:
        parts.append("no timing, name, or area bonus")
    return score, "; ".join(parts)


def _json_get(url, params):
    request = urllib.request.Request(url + "?" + urllib.parse.urlencode(params))
    with urllib.request.urlopen(request, timeout=90) as response:
        return json.load(response)


def fetch_osm_substations(cache_path=None):
    if cache_path and Path(cache_path).exists():
        payload = json.loads(Path(cache_path).read_text())
        elements = payload.get("elements") or []
        facilities = []
        for element in elements:
            tags = element.get("tags") or {}
            name = tags.get("name")
            if not name:
                continue
            lat = element.get("lat") or (element.get("center") or {}).get("lat")
            lng = element.get("lon") or (element.get("center") or {}).get("lon")
            if lat is None or lng is None:
                continue
            facilities.append(
                {
                    "name": name,
                    "norm": norm_name(name),
                    "lat": float(lat),
                    "lng": float(lng),
                    "operator": tags.get("operator") or "",
                    "osm": f"{element['type']}/{element['id']}",
                }
            )
        return facilities
    query = """
    [out:json][timeout:90];
    area["ISO3166-2"="US-SC"]->.sc;
    area["ISO3166-2"="US-GA"]->.ga;
    (
      node["power"="substation"](area.sc);
      way["power"="substation"](area.sc);
      node["power"="substation"](area.ga);
      way["power"="substation"](area.ga);
    );
    out center tags;
    """
    data = urllib.parse.urlencode({"data": query}).encode()
    request = urllib.request.Request(
        OVERPASS,
        data=data,
        headers={"User-Agent": "gridlock-estimated-coverage/1.0"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        payload = json.load(response)
    facilities = []
    for element in payload.get("elements") or []:
        tags = element.get("tags") or {}
        name = tags.get("name")
        if not name:
            continue
        lat = element.get("lat") or (element.get("center") or {}).get("lat")
        lng = element.get("lon") or (element.get("center") or {}).get("lon")
        if lat is None or lng is None:
            continue
        facilities.append(
            {
                "name": name,
                "norm": norm_name(name),
                "lat": float(lat),
                "lng": float(lng),
                "operator": tags.get("operator") or "",
                "osm": f"{element['type']}/{element['id']}",
            }
        )
    return facilities


def fetch_hifld_attributes(cache_path=None):
    if cache_path and Path(cache_path).exists():
        rows = json.loads(Path(cache_path).read_text())
        prepared = []
        for row in rows:
            owner = row.get("OWNER") or ""
            if owner == "GEORGIA POWER CO":
                utility = "GPC"
            elif owner.startswith("SOUTH CAROLINA ELECTRIC"):
                utility = "DESC"
            else:
                continue
            row = dict(row)
            row["utility"] = utility
            row["sub1"] = norm_name(row.get("SUB_1"))
            row["sub2"] = norm_name(row.get("SUB_2"))
            prepared.append(row)
        return prepared
    rows = []
    for utility, owners in HIFLD_OWNERS.items():
        for owner in owners:
            offset = 0
            while True:
                payload = _json_get(
                    HIFLD_LINES,
                    {
                        "where": f"OWNER='{owner}'",
                        "outFields": "OBJECTID,OWNER,VOLTAGE,SUB_1,SUB_2",
                        "returnGeometry": "false",
                        "orderByFields": "OBJECTID",
                        "resultOffset": str(offset),
                        "resultRecordCount": "2000",
                        "f": "json",
                    },
                )
                batch = [feature["attributes"] for feature in payload.get("features") or []]
                for row in batch:
                    row["utility"] = utility
                    row["sub1"] = norm_name(row.get("SUB_1"))
                    row["sub2"] = norm_name(row.get("SUB_2"))
                rows.extend(batch)
                if not payload.get("exceededTransferLimit") and len(batch) < 2000:
                    break
                offset += len(batch)
                if not batch:
                    break
    return rows


def fetch_hifld_geometry(object_ids):
    """Fetch paths by the OBJECTID attribute. The objectIds query parameter
    does not address that field and returns a different feature."""
    geometries = {}
    ids = [int(item) for item in object_ids]
    for start in range(0, len(ids), 15):
        chunk = ids[start:start + 15]
        where = "OBJECTID IN ({})".format(",".join(str(item) for item in chunk))
        payload = _json_get(
            HIFLD_LINES,
            {
                "where": where,
                "outFields": "OBJECTID",
                "returnGeometry": "true",
                "outSR": "4326",
                "f": "json",
            },
        )
        for feature in payload.get("features") or []:
            paths = (feature.get("geometry") or {}).get("paths") or []
            coordinates = []
            for path in paths:
                coordinates.extend([[lng, lat] for lng, lat in path])
            if len(coordinates) >= 2:
                geometries[int(feature["attributes"]["OBJECTID"])] = coordinates
    return geometries


def fetch_county_point(state, name):
    fips = COUNTY_FIPS[(state, name)]
    payload = _json_get(
        TIGER_COUNTY,
        {
            "where": f"NAME='{name} County' AND STATE='{fips}'",
            "outFields": "NAME,STATE,INTPTLAT,INTPTLON",
            "returnGeometry": "false",
            "f": "json",
        },
    )
    attributes = payload["features"][0]["attributes"]
    return float(attributes["INTPTLAT"]), float(attributes["INTPTLON"])


def operator_ok(facility, utility):
    operator = facility["operator"].lower()
    if utility == "GPC":
        return "georgia power" in operator
    return any(token in operator for token in ("carolina", "dominion", "sceg", "sce&g"))


def resolve_facility(label, facilities, utility, savannah_only=False):
    wanted = alias_labels(label)
    matches = [item for item in facilities if item["norm"] in wanted or any(item["norm"] == alias for alias in wanted)]
    # Exact normalized name, plus aliases.
    exact = []
    for item in facilities:
        if item["norm"] in wanted:
            exact.append(item)
    if not exact:
        return None, "no unique public facility"
    preferred = [item for item in exact if operator_ok(item, utility)]
    pool = preferred or exact
    home, other = state_boxes(utility)
    in_home = [item for item in pool if in_box(item["lat"], item["lng"], home)]
    if in_home:
        pool = in_home
    else:
        # Keep operator-matched facilities just across the river (McIntosh is in Georgia).
        pool = [item for item in pool if in_box(item["lat"], item["lng"], home) or in_box(item["lat"], item["lng"], other)]
    if savannah_only:
        pool = [
            item for item in pool
            if haversine_km(item["lat"], item["lng"], SAVANNAH_LAT, SAVANNAH_LNG) <= SAVANNAH_DISAMBIGUATION_KM
        ]
    # If operator was missing, drop facilities that sit only in the other state.
    if not preferred:
        pool = [item for item in pool if in_box(item["lat"], item["lng"], home) or operator_ok(item, utility)]
    unique = {(round(item["lat"], 4), round(item["lng"], 4)) for item in pool}
    if len(unique) != 1:
        return None, f"ambiguous ({len(unique)} facilities)"
    return pool[0], "unique public substation"


def voltage_matches(line_kv, project_voltages):
    if not project_voltages or line_kv is None:
        return False
    for voltage in project_voltages:
        if abs(float(line_kv) - float(voltage)) <= max(5.0, 0.1 * float(voltage)):
            return True
    return False


def counties_from_project(project):
    blob = f"{project.get('county_region') or ''} {project.get('name') or ''}"
    found = []
    for (state, name) in COUNTY_FIPS:
        if re.search(rf"\b{name}\b", blob, flags=re.I):
            if state == "GA" and project.get("utility") == "DESC" and "Calhoun" not in name:
                continue
            if state == "SC" and project.get("utility") == "GPC":
                continue
            found.append((state, name))
    # DESC Calhoun County is South Carolina, not a Georgia name collision.
    if project.get("utility") == "DESC" and re.search(r"\bCalhoun\b", blob, flags=re.I):
        found.append(("SC", "Calhoun"))
    # De-duplicate
    ordered = []
    for item in found:
        if item not in ordered:
            ordered.append(item)
    return ordered


def _resolve_label(label, facilities, projects, utility):
    facility, reason = resolve_facility(
        label,
        facilities,
        utility,
        savannah_only=("savannah" in label.lower()),
    )
    if facility:
        return facility, reason
    official = _official_point_for_label(label, projects)
    if official:
        return official, "official verified facility point"
    return None, reason


def _resolved_places(labels, facilities, projects, utility):
    resolved = []
    notes = []
    seen = set()
    for label in labels:
        key = norm_name(label)
        if key in seen:
            continue
        seen.add(key)
        facility, reason = _resolve_label(label, facilities, projects, utility)
        if facility:
            resolved.append((label, facility))
        else:
            notes.append(f"{label}: {reason}")
    return resolved, notes


def plan_estimate(project, resolved):
    """
    Decide which resolved facilities may become geometry.

    resolved is a list of (label, facility) for title places and candidates.
    A failed subject facility is never replaced by a different candidate.
    Extra candidates are not substituted for a titled line's endpoints.
    """
    by_label = {}
    for label, facility in resolved:
        by_label.setdefault(norm_name(label), (label, facility))

    def lookup(label):
        return by_label.get(norm_name(label))

    def ignored_note(used_labels):
        used = {norm_name(label) for label in used_labels}
        ignored = [label for label, _facility in resolved if norm_name(label) not in used]
        if not ignored:
            return []
        return ["not used as a substitute location: " + ", ".join(ignored)]

    subject = subject_facility(project)
    if subject:
        hit = lookup(subject)
        if hit:
            return {"action": "point", "hit": hit, "notes": ignored_note([hit[0]])}
        return {
            "action": "regional",
            "notes": [f"{subject}: subject facility was not uniquely resolved"] + ignored_note([]),
        }

    groups = title_groups(project)
    titled = [place for group in groups for place in group]
    use_title = any(lookup(place) for place in titled)
    circuits = []
    notes = []
    if use_title:
        for group in groups:
            places = []
            for place in group:
                hit = lookup(place)
                if hit and hit not in places:
                    places.append(hit)
            kept = []
            for hit in places:
                if not kept:
                    kept.append(hit)
                    continue
                distance = haversine_km(
                    kept[-1][1]["lat"], kept[-1][1]["lng"], hit[1]["lat"], hit[1]["lng"]
                )
                if distance > MAX_UNCONFIRMED_ENDPOINT_KM:
                    notes.append(
                        f"{kept[-1][0]}–{hit[0]}: public name match is {distance:.0f} km apart "
                        "and was not used without a confirming corridor"
                    )
                    continue
                kept.append(hit)
            if len(kept) >= 2:
                circuits.append(kept)
            elif len(kept) == 1 and not circuits:
                circuits.append(kept)
        if any(len(circuit) >= 2 for circuit in circuits):
            used = [hit[0] for circuit in circuits if len(circuit) >= 2 for hit in circuit]
            return {
                "action": "lines",
                "circuits": [circuit for circuit in circuits if len(circuit) >= 2],
                "notes": notes + ignored_note(used),
            }
        singles = [circuit[0] for circuit in circuits if len(circuit) == 1]
        if singles:
            return {"action": "point", "hit": singles[0], "notes": notes + ignored_note([singles[0][0]])}
        return {"action": "regional", "notes": notes}

    candidate_hits = []
    for label in project.get("endpoint_candidates") or []:
        hit = lookup(label)
        if hit and hit not in candidate_hits:
            candidate_hits.append(hit)
    kept = []
    for hit in candidate_hits:
        if not kept:
            kept.append(hit)
            continue
        distance = haversine_km(kept[-1][1]["lat"], kept[-1][1]["lng"], hit[1]["lat"], hit[1]["lng"])
        if distance > MAX_UNCONFIRMED_ENDPOINT_KM:
            notes.append(
                f"{kept[-1][0]}–{hit[0]}: public name match is {distance:.0f} km apart "
                "and was not used without a confirming corridor"
            )
            continue
        kept.append(hit)
    if len(kept) >= 2:
        return {"action": "lines", "circuits": [kept], "notes": notes}
    if len(kept) == 1:
        return {"action": "point", "hit": kept[0], "notes": notes}
    return {"action": "regional", "notes": notes}


def build_estimates(projects, osm_cache=None, hifld_cache=None):
    facilities = fetch_osm_substations(osm_cache)
    hifld = fetch_hifld_attributes(hifld_cache)
    county_cache = {}
    estimates = []
    unresolved = []

    def county_point(state, name):
        if (state, name) not in county_cache:
            try:
                county_cache[(state, name)] = fetch_county_point(state, name)
            except (IndexError, KeyError, urllib.error.URLError):
                county_cache[(state, name)] = None
        return county_cache[(state, name)]

    for project in projects:
        if se.extract_latlng_points(project):
            continue
        labels = endpoint_labels(project)
        resolved, notes = _resolved_places(labels, facilities, projects, project["utility"])
        plan = plan_estimate(project, resolved)
        notes = list(dict.fromkeys(notes + plan.get("notes") or []))
        if plan["action"] == "lines":
            estimate = _lines_estimate(project, plan["circuits"], hifld, notes)
            if estimate and _geometry_nonempty(estimate):
                estimates.append(estimate)
                continue
            notes.append("corridor or endpoint line had no coordinates")
        elif plan["action"] == "point":
            estimates.append(facility_point_estimate(project, plan["hit"], notes))
            continue
        counties = counties_from_project(project)
        if counties:
            points = [point for point in (county_point(*item) for item in counties) if point]
            if points:
                lat = sum(point[0] for point in points) / len(points)
                lng = sum(point[1] for point in points) / len(points)
                kept = [item for item in counties if county_point(*item)]
                estimates.append(regional_estimate(project, kept, lat, lng, notes))
                continue
        unresolved.append({
            "project_id": project["id"],
            "name": project["name"],
            "reason": "; ".join(notes) or "no defensible public match",
        })
    return estimates, unresolved


def _geometry_nonempty(estimate):
    return bool(parts_from_geometry(estimate.get("geometry"), estimate.get("geometry_type")))


def _lines_estimate(project, circuits, hifld, notes):
    """Prefer a HIFLD corridor for a rebuild pair. Otherwise a straight line."""
    parts = []
    descriptions = []
    all_hifld = True
    names = []
    for circuit in circuits:
        pair_rows = None
        if is_rebuild(project) and len(circuit) >= 2:
            pair_rows = _matching_corridor(project, [circuit[0], circuit[-1]], hifld)
        if pair_rows:
            geometries = fetch_hifld_geometry([row["OBJECTID"] for row in pair_rows])
            lines = [geometries[int(row["OBJECTID"])] for row in pair_rows if int(row["OBJECTID"]) in geometries]
            if lines:
                parts.extend(lines)
                descriptions.append(
                    f"HIFLD corridor {circuit[0][0]}–{circuit[-1][0]} ({len(lines)} segment(s), owner and voltage matched)"
                )
                names.extend([circuit[0][0], circuit[-1][0]])
                continue
        all_hifld = False
        line = [
            [round(hit[1]["lng"], 6), round(hit[1]["lat"], 6)]
            for hit in circuit
        ]
        if len(line) >= 2:
            parts.append(line)
            described = " to ".join(
                f"{hit[1]['name']} ({hit[1]['osm']})" for hit in circuit
            )
            descriptions.append(f"straight line {described}")
            names.extend(hit[0] for hit in circuit)
    if not parts:
        return None
    if len(parts) == 1:
        geometry = parts[0]
        geometry_type = "LineString"
    else:
        geometry = parts
        geometry_type = "MultiLineString"
    if all_hifld:
        method = "existing_corridor_hifld"
        confidence = "MEDIUM"
        source = HIFLD_LINES.split("/query")[0]
        eligibility = "estimated_close"
    else:
        method = "approximate_verified_endpoints"
        confidence = "ESTIMATED"
        source = "https://www.openstreetmap.org"
        eligibility = "estimated_close"
    note = "; ".join(descriptions)
    if notes:
        note += ". Not used: " + "; ".join(notes)
    note += ". Not a surveyed route. Estimated geometry — planning-screening use only."
    ordered_names = []
    for name in names:
        if name not in ordered_names:
            ordered_names.append(name)
    return {
        "project_id": project["id"],
        "estimated_geometry": True,
        "geometry_type": geometry_type,
        "geometry": geometry,
        "geometry_method": method,
        "geometry_confidence": confidence,
        "geometry_source": source,
        "geometry_notes": note,
        "endpoint_names": ordered_names,
        "tier_eligibility": eligibility,
    }


def _official_point_for_label(label, projects):
    wanted = alias_labels(label)
    hits = []
    for project in projects:
        if project.get("geometry_type") != "Point":
            continue
        if not se.extract_latlng_points(project):
            continue
        if norm_name(project["name"]).split(" ")[0] in wanted or any(token in norm_name(project["name"]) for token in wanted if len(token) >= 5):
            # Require the facility word to be a whole token in the official name.
            official_tokens = set(norm_name(project["name"]).split())
            if any(token in official_tokens for token in wanted):
                lat, lng = se.extract_latlng_points(project)[0]
                hits.append(
                    {
                        "name": project["name"],
                        "norm": norm_name(label),
                        "lat": lat,
                        "lng": lng,
                        "operator": "verified official point",
                        "osm": project["id"],
                        "official": True,
                    }
                )
    unique = {(round(item["lat"], 4), round(item["lng"], 4)) for item in hits}
    if len(unique) != 1:
        return None
    return hits[0]


def _matching_corridor(project, resolved, hifld):
    labels = []
    for _name, facility in resolved[:2]:
        labels.append(alias_labels(facility["name"]) | alias_labels(_name))
    voltages = project.get("voltage_kv") or []
    hits = []
    for row in hifld:
        if row["utility"] != project["utility"]:
            continue
        ends = {row["sub1"], row["sub2"]}
        if not any(label in ends for label in labels[0]):
            continue
        if not any(label in ends for label in labels[1]):
            continue
        if not voltage_matches(row.get("VOLTAGE"), voltages):
            continue
        hits.append(row)
    if not hits or len(hits) > 4:
        return None
    return hits


def corridor_estimate(project, resolved, rows):
    geometries = fetch_hifld_geometry([row["OBJECTID"] for row in rows])
    lines = [geometries[row["OBJECTID"]] for row in rows if row["OBJECTID"] in geometries]
    if len(lines) == 1:
        geometry = lines[0]
        geometry_type = "LineString"
    else:
        geometry = lines
        geometry_type = "MultiLineString"
    names = [item[0] for item in resolved[:2]]
    return {
        "project_id": project["id"],
        "estimated_geometry": True,
        "geometry_type": geometry_type,
        "geometry": geometry,
        "geometry_method": "existing_corridor_hifld",
        "geometry_confidence": "MEDIUM",
        "geometry_source": HIFLD_LINES.split("/query")[0],
        "geometry_notes": (
            f"HIFLD corridor between {names[0]} and {names[1]} "
            f"({len(lines)} segment(s), owner/voltage matched). "
            "Estimated geometry — planning-screening use only."
        ),
        "endpoint_names": names,
        "tier_eligibility": "estimated_close",
    }


def endpoint_line_estimate(project, resolved):
    (name_a, facility_a), (name_b, facility_b) = resolved
    return {
        "project_id": project["id"],
        "estimated_geometry": True,
        "geometry_type": "LineString",
        "geometry": [
            [round(facility_a["lng"], 6), round(facility_a["lat"], 6)],
            [round(facility_b["lng"], 6), round(facility_b["lat"], 6)],
        ],
        "geometry_method": "approximate_verified_endpoints",
        "geometry_confidence": "ESTIMATED",
        "geometry_source": "https://www.openstreetmap.org",
        "geometry_notes": (
            f"Straight line between public facilities {facility_a['name']} "
            f"({facility_a['osm']}) and {facility_b['name']} ({facility_b['osm']}). "
            "Not a surveyed route. Estimated geometry — planning-screening use only."
        ),
        "endpoint_names": [name_a, name_b],
        "tier_eligibility": "estimated_close",
    }


def facility_point_estimate(project, resolved, extra_notes):
    name, facility = resolved
    note = (
        f"Only {facility['name']} ({facility['osm']}) resolved. "
        "The other endpoint was left unresolved"
    )
    if extra_notes:
        note += " (" + "; ".join(extra_notes) + ")"
    note += ". Estimated geometry — planning-screening use only."
    return {
        "project_id": project["id"],
        "estimated_geometry": True,
        "geometry_type": "Point",
        "geometry": [round(facility["lng"], 6), round(facility["lat"], 6)],
        "geometry_method": "estimated_facility_point",
        "geometry_confidence": "ESTIMATED",
        "geometry_source": "https://www.openstreetmap.org" if not facility.get("official") else facility["osm"],
        "geometry_notes": note,
        "endpoint_names": [name],
        "tier_eligibility": "broad_screen",
    }


def regional_estimate(project, counties, lat, lng, extra_notes):
    label = ", ".join(f"{name} County, {state}" for state, name in counties)
    note = (
        f"Census county internal point for {label}. "
        "No facility or corridor was uniquely resolved. "
        "Eligible only for under-40 km screening. "
        "Estimated geometry — planning-screening use only."
    )
    if extra_notes:
        note += " Unresolved names: " + "; ".join(extra_notes) + "."
    return {
        "project_id": project["id"],
        "estimated_geometry": True,
        "geometry_type": "Point",
        "geometry": [round(lng, 6), round(lat, 6)],
        "geometry_method": "regional_screening_anchor",
        "geometry_confidence": "LOW",
        "geometry_source": TIGER_COUNTY.split("/query")[0],
        "geometry_notes": note,
        "endpoint_names": [],
        "tier_eligibility": "regional_screen",
    }


def load_projects(path):
    payload = json.loads(Path(path).read_text())
    if isinstance(payload, list):
        return payload
    return payload.get("projects") or []


def apply_estimates(projects, estimates):
    """Return scoring records. Official geometry is never replaced."""
    by_id = {item["project_id"]: item for item in estimates}
    prepared = []
    for project in projects:
        record = dict(project)
        record["estimated_geometry"] = False
        if se.extract_latlng_points(project):
            prepared.append(record)
            continue
        estimate = by_id.get(project["id"])
        if not estimate or not _geometry_nonempty(estimate):
            prepared.append(record)
            continue
        record["geometry"] = estimate["geometry"]
        record["geometry_type"] = estimate["geometry_type"]
        record["geometry_method"] = estimate["geometry_method"]
        record["geometry_confidence"] = estimate["geometry_confidence"]
        record["geometry_source"] = estimate["geometry_source"]
        record["geometry_notes"] = estimate["geometry_notes"]
        record["endpoint_names"] = estimate.get("endpoint_names") or []
        record["estimated_geometry"] = True
        record["tier_eligibility"] = estimate.get("tier_eligibility")
        prepared.append(record)
    return prepared


def score_estimated(projects):
    desc = []
    gpc = []
    for project in projects:
        if project.get("utility") == "DESC" and parts_from_geometry(project.get("geometry"), project.get("geometry_type")):
            desc.append(project)
        elif project.get("utility") == "GPC" and parts_from_geometry(project.get("geometry"), project.get("geometry_type")):
            gpc.append(project)
    matches = []
    for project_a in desc:
        for project_b in gpc:
            parts_a = parts_from_geometry(project_a.get("geometry"), project_a.get("geometry_type"))
            parts_b = parts_from_geometry(project_b.get("geometry"), project_b.get("geometry_type"))
            distance_km, intersects, closest_a, closest_b = closest_distance_km(parts_a, parts_b)
            tier, label, blocked = eligible_tier(distance_km, intersects, project_a, project_b)
            if tier is None:
                continue
            geographic_tier, _geographic_label = se.classify_tier(distance_km, intersects=intersects)
            overlap, gap, overlap_years = se.timeline_relationship(project_a, project_b)
            score, explanation = coordination_score(project_a, project_b)
            window_a = list(se.project_year_window(project_a))
            window_b = list(se.project_year_window(project_b))
            if overlap:
                timing = f"Same construction year ({overlap_years[0]})."
            elif gap is None:
                timing = "Timing unknown for at least one project."
            elif gap == 1:
                timing = "One-year timing gap."
            else:
                timing = f"Timing gap of {gap} year(s)."
            blocked_note = ""
            if blocked:
                blocked_note = (
                    f" Geographic tier would be {geographic_tier}, but this pair stays in "
                    "the under-40 km screen because a low-confidence or single-point estimate "
                    "cannot create a touching, under-1.6 km, or under-8 km tier."
                )
            brief = "\n".join([
                f"{project_a['utility']} – {project_a['name']}  <->  {project_b['utility']} – {project_b['name']}",
                f"Distance: {distance_km:.2f} km (closest point to closest point). Tier: {label}.",
                timing + blocked_note,
                (
                    f"Geometry: {project_a.get('geometry_method')} ({project_a.get('geometry_confidence')}) "
                    f"and {project_b.get('geometry_method')} ({project_b.get('geometry_confidence')})."
                ),
                f"Coordination score {score}: {explanation}. The score does not change the distance tier.",
                "Estimated geometry — planning-screening use only.",
            ])
            matches.append(
                {
                    "project_a_id": project_a["id"],
                    "project_b_id": project_b["id"],
                    "project_a": _public_project(project_a),
                    "project_b": _public_project(project_b),
                    "distance_km": round(distance_km, 2),
                    "geographic_distance_km": round(distance_km, 2),
                    "geographic_tier": geographic_tier,
                    "distance_tier": tier,
                    "distance_tier_label": label,
                    "close_tier_blocked": blocked,
                    "timeline_overlap": overlap,
                    "timeline_gap_years": gap,
                    "overlap_years": overlap_years,
                    "coordination_score": score,
                    "coordination_explanation": explanation,
                    "coordination_brief": brief,
                    "closest_points": {"a": closest_a, "b": closest_b},
                    "closest_point_a": closest_a,
                    "closest_point_b": closest_b,
                    "years_a": window_a if window_a[0] is not None else None,
                    "years_b": window_b if window_b[0] is not None else None,
                    "screening_note": "Estimated geometry — planning-screening use only.",
                }
            )
    tier_order = {se.TIER_MUST: 0, se.TIER_LAND: 1, se.TIER_LOGISTICS: 2, se.TIER_CREWS: 3}
    matches.sort(
        key=lambda match: (
            tier_order.get(match["distance_tier"], 9),
            -match["coordination_score"],
            match["distance_km"],
            match["project_a_id"],
            match["project_b_id"],
        )
    )
    for index, match in enumerate(matches, start=1):
        match["match_id"] = f"e{index:03d}"
    return matches


def _public_project(project):
    return {
        "id": project.get("id"),
        "utility": project.get("utility"),
        "name": project.get("name"),
        "project_type": project.get("project_type"),
        "planned_start_year": project.get("planned_start_year"),
        "planned_end_year": project.get("planned_end_year"),
        "in_service_year": project.get("in_service_year"),
        "voltage_kv": project.get("voltage_kv") or [],
        "geometry": project.get("geometry"),
        "geometry_type": project.get("geometry_type"),
        "geometry_method": project.get("geometry_method"),
        "geometry_confidence": project.get("geometry_confidence"),
        "geometry_source": project.get("geometry_source"),
        "geometry_notes": project.get("geometry_notes"),
        "source_url": project.get("source_url"),
        "source_page": project.get("source_page"),
        "data_confidence": project.get("data_confidence"),
        "county_region": project.get("county_region"),
        "estimated_geometry": bool(project.get("estimated_geometry")),
        "endpoint_names": project.get("endpoint_names") or [],
        "start_year": se.project_year_window(project)[0],
        "end_year": se.project_year_window(project)[1],
    }


def summarize(projects, matches):
    def count(tier_set):
        return sum(1 for match in matches if match["distance_tier"] in tier_set)

    estimated = sum(1 for project in projects if project.get("estimated_geometry"))
    with_geometry = sum(
        1 for project in projects
        if parts_from_geometry(project.get("geometry"), project.get("geometry_type"))
    )
    return {
        "total_projects": len(projects),
        "desc_projects": sum(1 for project in projects if project.get("utility") == "DESC"),
        "gpc_projects": sum(1 for project in projects if project.get("utility") == "GPC"),
        "projects_with_geometry": with_geometry,
        "projects_without_geometry": len(projects) - with_geometry,
        "estimated_geometry_count": estimated,
        "unresolved_count": len(projects) - with_geometry,
        "pairs_checked": None,
        "pairs_within_40km": len(matches),
        "pairs_under_8km": count({se.TIER_MUST, se.TIER_LAND, se.TIER_LOGISTICS}),
        "pairs_under_1_6km": count({se.TIER_MUST, se.TIER_LAND}),
        "pairs_touching": count({se.TIER_MUST}),
        "pairs_with_timeline_overlap": sum(1 for match in matches if match["timeline_overlap"]),
        "same_year_opportunities": sum(1 for match in matches if match["timeline_overlap"]),
        "close_tier_blocked": sum(1 for match in matches if match["close_tier_blocked"]),
    }


def evaluable_pair_count(projects):
    desc = sum(1 for project in projects if project.get("utility") == "DESC" and parts_from_geometry(project.get("geometry"), project.get("geometry_type")))
    gpc = sum(1 for project in projects if project.get("utility") == "GPC" and parts_from_geometry(project.get("geometry"), project.get("geometry_type")))
    return desc * gpc


def write_analysis(projects, matches, summary):
    summary["pairs_checked"] = evaluable_pair_count(projects)
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": "estimated",
        "data_source": "estimated",
        "data_disclaimer": DISCLAIMER,
        "utilities": ["DESC", "GPC"],
        "input_project_count": summary["total_projects"],
        "match_count": len(matches),
        "summary": summary,
        "projects": [_public_project(project) for project in projects],
        "matches": matches,
    }
    OUTPUT_PATH.write_text(json.dumps(output, indent=2) + "\n")
    return output


def rebuild_geometry_file(osm_cache=None, hifld_cache=None):
    projects = load_projects(VERIFIED_PATH)
    estimates, unresolved = build_estimates(projects, osm_cache=osm_cache, hifld_cache=hifld_cache)
    payload = {
        "schema_version": "1.0",
        "dataset": "estimated_coverage",
        "disclaimer": DISCLAIMER,
        "estimates": estimates,
        "unresolved": unresolved,
    }
    ESTIMATE_PATH.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"estimates {len(estimates)} unresolved {len(unresolved)} -> {ESTIMATE_PATH}")
    return payload


def run():
    projects = load_projects(VERIFIED_PATH)
    payload = json.loads(ESTIMATE_PATH.read_text())
    prepared = apply_estimates(projects, payload.get("estimates") or [])
    # Guard: official geometry unchanged.
    official = {project["id"]: project.get("geometry") for project in projects}
    for project in prepared:
        if official.get(project["id"]) is not None and project.get("geometry") != official[project["id"]]:
            raise RuntimeError(f"official geometry was overwritten for {project['id']}")
    matches = score_estimated(prepared)
    summary = summarize(prepared, matches)
    summary["pairs_checked"] = evaluable_pair_count(prepared)
    output = write_analysis(prepared, matches, summary)
    print(
        f"mapped {summary['projects_with_geometry']} "
        f"estimated {summary['estimated_geometry_count']} "
        f"unresolved {summary['unresolved_count']} "
        f"pairs {summary['pairs_checked']} "
        f"<40 {summary['pairs_within_40km']} "
        f"<8 {summary['pairs_under_8km']} "
        f"<1.6 {summary['pairs_under_1_6km']} "
        f"touching {summary['pairs_touching']}"
    )
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rebuild-geometry", action="store_true")
    parser.add_argument("--osm-cache", default=None)
    parser.add_argument("--hifld-cache", default=None)
    args = parser.parse_args()
    if args.rebuild_geometry:
        rebuild_geometry_file(osm_cache=args.osm_cache, hifld_cache=args.hifld_cache)
    run()


if __name__ == "__main__":
    main()
