"""Validate and package the authorized Common Ground NOAA archive; no network calls."""

from datetime import date, datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT.parent / "reference-repos/Shellhacks-2026-fradicus"


def build():
    source = REFERENCE / "data/weather_history"
    index = json.loads((source / "index.json").read_text())
    window = index["window"]
    count = (
        date.fromisoformat(window["end"]) - date.fromisoformat(window["start"])
    ).days + 1
    fields = ("prcp_in", "tmax_f", "tmin_f", "snow_in", "wsf2_mph")
    stations, entries = {}, []
    for identifier, meta in sorted(index["stations"].items()):
        if not re.fullmatch(r"[A-Z0-9]+", identifier):
            raise ValueError("Invalid station identifier")
        path = (source / meta["file"]).resolve()
        if not path.is_relative_to(source.resolve()):
            raise ValueError("Invalid station path")
        raw = path.read_bytes()
        data = json.loads(gzip.decompress(raw) if path.suffix == ".gz" else raw)
        if (
            data["station"]["id"] != identifier
            or data["start"] != window["start"]
            or data["end"] != window["end"]
        ):
            raise ValueError("Station identity/window mismatch")
        lat, lon = data["station"]["lat"], data["station"]["lon"]
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError("Invalid station coordinates")
        completeness = {}
        for key in fields:
            values = data.get(key, [None] * count)
            if len(values) != count or any(
                v is not None
                and (
                    isinstance(v, bool)
                    or not isinstance(v, (int, float))
                    or not math.isfinite(v)
                )
                for v in values
            ):
                raise ValueError("Invalid observations")
            data[key] = values
            completeness[key] = sum(v is not None for v in values) / count
        body = json.dumps(data, separators=(",", ":"), allow_nan=False).encode()
        stations[identifier] = {
            "name": meta["name"],
            "lat": lat,
            "lon": lon,
            "completeness": completeness,
            "sha256": hashlib.sha256(body).hexdigest(),
        }
        entries.append((identifier + ".json", body))
    output = ROOT / "data/nation/weather.zip"
    with zipfile.ZipFile(
        output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as archive:
        for name, body in entries:
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, body)
    receipt = {
        "window": window,
        "stations": stations,
        "source": index["source"]["citation"],
        "reference_commit": subprocess.check_output(
            ["git", "-C", str(REFERENCE), "rev-parse", "HEAD"], text=True
        ).strip(),
        "imported_at": datetime.now(timezone.utc).isoformat(),
        "archive_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "selection": {"rain_max_mi": 30, "wind_max_mi": 60, "min_complete": 0.95},
    }
    (output.parent / "weather-index.json").write_text(
        json.dumps(receipt, indent=2) + "\n"
    )
    print(
        json.dumps(
            {
                "stations": len(stations),
                "days_per_station": count,
                "archive_bytes": output.stat().st_size,
            }
        )
    )


if __name__ == "__main__":
    build()
