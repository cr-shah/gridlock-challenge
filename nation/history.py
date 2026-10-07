"""Source-cited historical station selection. No extrapolation outside distance caps."""

from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import zipfile

from nation.models import coordinate

ROOT = Path(__file__).resolve().parents[1] / "data/nation"


def miles(lon, lat, other_lon, other_lat):
    a, b = math.radians(lat), math.radians(other_lat)
    h = (
        math.sin((b - a) / 2) ** 2
        + math.cos(a) * math.cos(b) * math.sin(math.radians(other_lon - lon) / 2) ** 2
    )
    return 3958.8 * 2 * math.asin(min(1, math.sqrt(h)))


@lru_cache(maxsize=1)
def index():
    return json.loads((ROOT / "weather-index.json").read_text())


@lru_cache(maxsize=64)
def series(identifier):
    # Identifier must come from the trusted imported index, never from a URL/file path.
    meta = index()["stations"][identifier]
    with zipfile.ZipFile(ROOT / "weather.zip") as archive:
        info = archive.getinfo(identifier + ".json")
        if info.file_size > 1_000_000:
            raise ValueError("Station exceeds observation budget")
        raw = archive.read(info)
    if hashlib.sha256(raw).hexdigest() != meta["sha256"]:
        raise ValueError("Station integrity check failed")
    return json.loads(raw)


def at(lon, lat):
    lon, lat = coordinate(lon, lat)
    idx = index()
    ranked = sorted(
        (miles(lon, lat, s["lon"], s["lat"]), k) for k, s in idx["stations"].items()
    )

    def nearest(fields, cap):
        return next(
            (
                (distance, key)
                for distance, key in ranked
                if distance <= cap
                and all(
                    idx["stations"][key]["completeness"].get(f, 0) >= 0.95
                    for f in fields
                )
            ),
            None,
        )

    rain = nearest(["prcp_in", "tmax_f"], 30)
    wind = nearest(["wsf2_mph"], 60)
    result = {
        "provider": "noaa-history",
        "coverage": "nationwide_static",
        "status": "available" if rain else "unavailable",
        "window": idx["window"],
        "source_url": idx["source"],
        "imported_at": idx["imported_at"],
        "limitations": [
            "Historical station observations, not a forecast or site measurement. Archive coverage is incomplete.",
            "Rain/temperature station within 30 miles; optional wind station within 60 miles; ≥95% variable completeness over the archive.",
            "Station values may differ from worksite conditions. Historical replay does not model future climate, ground drying, holidays or crew availability.",
        ],
    }
    if not rain:
        result["limitations"].append(
            "No eligible rain/temperature station in the imported archive within 30 miles."
        )
        return result

    def station_ref(pair):
        distance, key = pair
        s = series(key)
        return {
            **s["station"],
            "distance_mi": round(distance, 2),
            "source_url": s["source"]["url"],
            "retrieved_at": s["source"]["retrieved_at"],
            "completeness": idx["stations"][key]["completeness"],
        }

    data = series(rain[1])
    return {
        **result,
        "rain": station_ref(rain),
        "wind": station_ref(wind) if wind else None,
        "observations": {
            **{
                key: data.get(key) for key in ("prcp_in", "tmax_f", "tmin_f", "snow_in")
            },
            "wsf2_mph": series(wind[1])["wsf2_mph"] if wind else None,
        },
    }
