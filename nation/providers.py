"""Official live adapters. Missing data is never replaced with demo observations."""

from __future__ import annotations

from datetime import datetime, timezone
import os
from urllib.parse import urlencode, urlsplit

from shapely.geometry import shape

from nation.models import coordinate, ProviderResult, safe_url
from nation.transport import Cache, fetch_json, utcnow

CACHE = Cache()
REGISTRY = [
    {
        "id": "noaa-history",
        "name": "NOAA GHCN daily archive",
        "coverage": "nationwide_static",
        "mode": "on-demand",
        "scope": "Imported 2016–2025 station observations; distance and completeness eligibility, not continuous nationwide coverage",
    },
    {
        "id": "canonical",
        "name": "Gridlock canonical projects",
        "coverage": "regional",
        "scope": "DESC / Georgia Power, source-specific publication",
        "mode": "static",
    },
    {
        "id": "common-ground",
        "name": "National filing catalog",
        "coverage": "nationwide_static",
        "scope": "Imported public filings; incomplete coverage, mixed vintages",
        "mode": "static",
    },
    {
        "id": "nws-alerts",
        "name": "NWS active alerts",
        "coverage": "nationwide_live",
        "scope": "U.S. NWS service areas; some alerts have no polygon",
        "mode": "live",
    },
    {
        "id": "nws-forecast",
        "name": "NWS hourly forecast",
        "coverage": "nationwide_live",
        "scope": "Available land gridpoints; forecast, not observed conditions",
        "mode": "on-demand",
    },
    {
        "id": "ssurgo",
        "name": "USDA soil survey",
        "coverage": "nationwide_static",
        "scope": "Surveyed map units at the selected point; not a site test",
        "mode": "on-demand",
    },
    {
        "id": "wetlands",
        "name": "FWS wetland inventory",
        "coverage": "nationwide_static",
        "scope": "Mapped inventory; absence is not proof of no wetlands",
        "mode": "on-demand",
    },
]


def timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else None
    except ValueError:
        return None


def valid_geometry(g):
    if g is None:
        return None
    try:
        if g.get("type") not in {"Polygon", "MultiPolygon"}:
            return None
        geom = shape(g)
        if not geom.is_valid or geom.is_empty:
            return None
        coordinate(*geom.bounds[:2])
        coordinate(*geom.bounds[2:])
        return g
    except (TypeError, ValueError, KeyError):
        return None


def normalize_alerts(payload, now=None):
    now = now or datetime.now(timezone.utc)
    if payload.get("type") != "FeatureCollection" or not isinstance(
        payload.get("features"), list
    ):
        raise ValueError("Malformed alert collection.")
    records, malformed = [], 0
    seen = set()
    for f in payload["features"][:5000]:
        p = f.get("properties") or {}
        identifier = p.get("id") or f.get("id")
        expires = timestamp(p.get("expires"))
        sent = timestamp(p.get("sent"))
        if (
            not identifier
            or not expires
            or not sent
            or not p.get("event")
            or sent > now
        ):
            malformed += 1
            continue
        if expires <= now or p.get("status") != "Actual" or identifier in seen:
            continue
        seen.add(identifier)
        records.append(
            {
                "id": identifier,
                "kind": "hazard",
                "name": p["event"],
                "geometry": valid_geometry(f.get("geometry")),
                "confidence": "official",
                "severity": p.get("severity", "Unknown"),
                "certainty": p.get("certainty"),
                "onset": p.get("onset"),
                "expires": p["expires"],
                "area": p.get("areaDesc"),
                "headline": p.get("headline"),
                "description": p.get("description"),
                "instruction": p.get("instruction"),
                "zones": p.get("affectedZones", []),
                "provenance": {
                    "provider": "nws-alerts",
                    "source_url": safe_url(p.get("@id")) or safe_url(identifier),
                    "coverage": "nationwide_live",
                    "retrieved_at": now.isoformat(),
                    "source_updated_at": p["sent"],
                },
            }
        )
    records.sort(
        key=lambda r: (
            {"Extreme": 0, "Severe": 1, "Moderate": 2, "Minor": 3}.get(
                r["severity"], 4
            ),
            r["id"],
        )
    )
    truncated = (
        len(records) > 500
        or len(payload["features"]) > 5000
        or bool(payload.get("pagination", {}).get("next"))
    )
    partial = truncated or malformed > 0
    return ProviderResult(
        "nws-alerts",
        "partial" if partial else "available",
        "nationwide_live",
        records[:500],
        now.isoformat(),
        limitations=[
            "Some alerts lack polygons; unplotted alerts remain in the alert list.",
            "Alert intersection is possible exposure, not a predicted outage.",
        ]
        + ([f"{malformed} malformed alerts omitted."] if malformed else []),
        truncated=truncated,
    ).json()


def alerts():
    if os.getenv("GRIDLOCK_OFFLINE") == "1":
        return ProviderResult(
            "nws-alerts",
            "unavailable",
            "nationwide_live",
            limitations=["Live providers disabled by GRIDLOCK_OFFLINE."],
        ).json()
    result = CACHE.get(
        "nws-alerts",
        lambda: normalize_alerts(
            fetch_json("https://api.weather.gov/alerts/active?status=actual")
        ),
        ttl=180,
        stale_ttl=900,
    )
    now = datetime.now(timezone.utc)
    result["records"] = [
        r
        for r in result.get("records", [])
        if timestamp(r.get("expires")) and timestamp(r["expires"]) > now
    ]
    return {"provider": "nws-alerts", "coverage": "nationwide_live", **result}


def forecast(lon, lat):
    info = fetch_json(f"https://api.weather.gov/points/{lat:.4f},{lon:.4f}")[
        "properties"
    ]
    target = info["forecastHourly"]
    p = urlsplit(target)
    if (
        p.scheme != "https"
        or p.netloc != "api.weather.gov"
        or not p.path.startswith("/gridpoints/")
        or not p.path.endswith("/forecast/hourly")
        or p.query
    ):
        raise ValueError("Unexpected forecast resource.")
    raw = fetch_json(target)["properties"]
    now = datetime.now(timezone.utc)
    updated = timestamp(raw.get("updateTime"))
    if updated is None or updated > now:
        raise ValueError("Forecast has no valid update timestamp.")
    periods = []
    for p in raw.get("periods", [])[:160]:
        start, end = timestamp(p.get("startTime")), timestamp(p.get("endTime"))
        if start is None or end is None or start >= end:
            raise ValueError("Malformed forecast interval.")
        if end <= now:
            continue
        periods.append(
            {
                "start": p["startTime"],
                "end": p["endTime"],
                "temperature": p.get("temperature"),
                "unit": p.get("temperatureUnit"),
                "wind": p.get("windSpeed"),
                "description": p.get("shortForecast"),
                "precipitation_probability": (
                    p.get("probabilityOfPrecipitation") or {}
                ).get("value"),
            }
        )
    return {
        "status": "available"
        if periods and (now - updated).total_seconds() < 21600
        else "stale",
        "provider": "nws-forecast",
        "coverage": "nationwide_live",
        "periods": periods[:48],
        "source_url": target,
        "source_updated_at": raw["updateTime"],
        "retrieved_at": utcnow(),
        "limitations": [
            "Point forecast; no construction safety clearance or damage prediction."
        ],
    }


def soil(lon, lat):
    # Fixed query with validated numeric coordinates, no client-provided SQL.
    query = (
        "SELECT TOP 20 m.mukey,m.muname,c.compname,c.comppct_r,c.drainagecl,c.hydgrp "
        f"FROM SDA_Get_Mukey_from_intersection_with_WktWgs84('POINT({lon} {lat})') p "
        "JOIN mapunit m ON m.mukey=p.mukey LEFT JOIN component c ON c.mukey=m.mukey "
        "ORDER BY m.mukey,c.comppct_r DESC"
    )
    source = "https://sdmdataaccess.nrcs.usda.gov/Tabular/post.rest"
    raw = fetch_json(source, {"query": query, "format": "JSON+COLUMNNAME"})
    rows = raw.get("Table", [])
    expected = ["mukey", "muname", "compname", "comppct_r", "drainagecl", "hydgrp"]
    if rows and rows[0] != expected:
        raise ValueError("Unexpected soil table.")
    records = [dict(zip(expected, r)) for r in rows[1:] if len(r) == 6]
    return {
        "provider": "ssurgo",
        "status": "partial" if len(records) == 20 else "available",
        "coverage": "nationwide_static",
        "records": records,
        "source_url": source,
        "retrieved_at": utcnow(),
        "limitations": [
            "Mapped soil survey; no result means no returned survey data, not safe ground."
        ],
    }


def wetlands(lon, lat):
    source = "https://fwspublicservices.wim.usgs.gov/wetlandsmapservice/rest/services/Wetlands/MapServer/0/query"
    params = {
        "f": "json",
        "geometry": f"{lon},{lat}",
        "geometryType": "esriGeometryPoint",
        "inSR": 4326,
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "ATTRIBUTE,WETLAND_TYPE",
        "returnGeometry": "false",
        "resultRecordCount": 20,
    }
    data = fetch_json(source + "?" + urlencode(params))
    if not isinstance(data.get("features"), list):
        raise ValueError("Malformed wetland response.")
    return {
        "provider": "wetlands",
        "status": "partial" if data.get("exceededTransferLimit") else "available",
        "coverage": "nationwide_static",
        "records": [f["attributes"] for f in data["features"][:20]],
        "source_url": source,
        "retrieved_at": utcnow(),
        "limitations": [
            "Inventory intersection only; absence is not proof of no wetlands or permit requirements."
        ],
    }


def site_provider(provider, lon, lat):
    coordinate(lon, lat)
    functions = {"nws-forecast": forecast, "ssurgo": soil, "wetlands": wetlands}
    if provider not in functions:
        raise ValueError("Unknown site provider.")
    if os.getenv("GRIDLOCK_OFFLINE") == "1":
        return {
            "provider": provider,
            "status": "unavailable",
            "limitations": ["Live providers disabled by GRIDLOCK_OFFLINE."],
        }
    # Exactly the rounded location is used both in the key and upstream request.
    lon, lat = round(lon, 4), round(lat, 4)
    return {
        "provider": provider,
        **CACHE.get(
            (provider, lon, lat), lambda: functions[provider](lon, lat), ttl=900
        ),
    }
