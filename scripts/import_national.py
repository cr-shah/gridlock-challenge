"""Import Common Ground's validated release under the user's reuse permission.

Run with the sibling pipeline Python (jsonschema installed). No network/database writes.
Reference code runs only here; product runtime consumes a self-contained hashed artifact.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import gzip
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from nation.models import coordinate, milestone, safe_url


def build(reference: Path) -> dict:
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(reference / "pipeline"))
    from national.build import load_snapshot
    from national_pairs.build import generate

    snapshot = load_snapshot(reference)
    pairs = generate(snapshot, root=reference)
    sources = {s["_id"]: s for s in snapshot["sources"]}
    records = []
    for p in snapshot["projects"]:
        if p["_id"].startswith("legacy:"):
            continue
        source = sources[p["source_id"]]
        point = p.get("center")
        review = p.get("location_review")
        candidate = p.get("location_candidate") or {}
        geometry = None
        if point and review not in {"rejected", "needs_review", "unlocated"}:
            lon, lat = coordinate(point["lon"], point["lat"])
            geometry = {"type": "Point", "coordinates": [lon, lat]}
        confidence = (
            (
                "verified"
                if review == "confirmed"
                else "official"
                if candidate.get("tier") == "official"
                else "tentative"
            )
            if geometry
            else "unresolved"
        )
        raw_date = p.get("in_service") or {}
        value, precision = raw_date.get("value"), raw_date.get("precision", "unknown")
        # Some producers encode a year/month in an ISO-looking string. Preserve raw separately.
        if value and precision in {"year", "month"}:
            value = value[: 4 if precision == "year" else 7]
        date_issue = None
        try:
            normalized_date = milestone(value, precision)
        except ValueError:
            normalized_date = milestone(None, "unknown")
            date_issue = "Invalid or implausible source date excluded from normalized timeline; raw value retained."
        records.append(
            {
                "id": "national:" + p["_id"],
                "native_id": p["native_id"],
                "kind": "project",
                "name": p["name"],
                "owner": p.get("owner"),
                "other_owners": p.get("other_owners", []),
                "states": p.get("states", []),
                "counties": p.get("counties", []),
                "planning_region": p.get("planning_region"),
                "status": p.get("status_group", "unknown"),
                "geometry": geometry,
                "confidence": confidence,
                "milestone": normalized_date,
                "source_id": p["source_id"],
                "provenance": {
                    "provider": "common-ground",
                    "coverage": "nationwide_static",
                    "source_url": safe_url(source.get("download_url"))
                    or safe_url(source.get("landing_url")),
                    "publisher": source.get("publisher"),
                    "retrieved_at": source.get("retrieved_at"),
                    "source_updated_at": source.get("publication_date"),
                    "sha256": source.get("sha256"),
                },
                "detail": {
                    "description": p.get("description"),
                    "status_text": p.get("status"),
                    "date_raw": raw_date.get("raw"),
                    "source_milestone": raw_date,
                    "date_issue": date_issue,
                    "evidence": p.get("evidence"),
                    "location_candidate": candidate,
                    "location_verification": p.get("location_verification"),
                    "location_review": review,
                    "geography_basis": p.get("geography_basis"),
                    "events": p.get("project_events", []),
                    "limitation": "Imported filing record; current status and location have not been independently reverified by Gridlock.",
                },
            }
        )
    ids = {r["id"] for r in records}
    normalized_pairs = []
    dates = {r["id"]: r["milestone"] for r in records}
    for p in pairs["pairs"]:
        a, b = "national:" + p["a"], "national:" + p["b"]
        if a in ids and b in ids:
            normalized_pairs.append(
                {
                    "id": p["_id"],
                    "a": a,
                    "b": b,
                    "distance_km": round(p["distance_mi"] * 1.609344, 3),
                    "time_gap_days": p["time_gap_days"]
                    if dates[a]["precision"] == dates[b]["precision"] == "day"
                    else None,
                    "confidence": p["tier"],
                    "method": "center_haversine",
                    "classification": "provisional",
                    "rule": p["rule_version"],
                    "owner_identity_version": p["identity_version"],
                }
            )
    commit = subprocess.check_output(
        ["git", "-C", str(reference), "rev-parse", "HEAD"], text=True
    ).strip()
    return {
        "schema_version": 1,
        "imported_at": datetime.now(timezone.utc).isoformat(),
        "reference": {
            "repository": "https://github.com/fradicus/Shellhacks-2026",
            "commit": commit,
            "permission": "User-confirmed author agreement at ShellHacks, 2026-10-06",
        },
        "records": records,
        "sources": list(sources.values()),
        "geography": snapshot["geography"],
        "pairs": normalized_pairs,
        "pair_coverage": pairs["coverage"],
        "counts": {
            "records": len(records),
            "mapped": sum(bool(r["geometry"]) for r in records),
            "confidence": dict(Counter(r["confidence"] for r in records)),
            "pairs": len(normalized_pairs),
        },
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--reference",
        type=Path,
        default=ROOT.parent / "reference-repos/Shellhacks-2026-fradicus",
    )
    args = parser.parse_args()
    payload = build(args.reference.resolve())
    out = ROOT / "data/nation"
    out.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode()
    # One atomic artifact; a hash receipt pins the complete imported bundle.
    raw = gzip.compress(raw, mtime=0)
    temporary = out / "catalog.json.gz.tmp"
    temporary.write_bytes(raw)
    temporary.replace(out / "catalog.json.gz")
    receipt = {
        "sha256": hashlib.sha256(raw).hexdigest(),
        "reference": payload["reference"],
        "imported_at": payload["imported_at"],
        "counts": payload["counts"],
    }
    temporary = out / "receipt.json.tmp"
    temporary.write_text(json.dumps(receipt, indent=2) + "\n")
    temporary.replace(out / "receipt.json")
    print(json.dumps(receipt, indent=2))
