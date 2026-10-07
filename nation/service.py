"""Indexed national catalog with provenance, bounded responses and saved analyses."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict
import gzip
import hashlib
import json
import math
from pathlib import Path
import threading

from shapely.geometry import box, shape
from shapely.strtree import STRtree

from canonical_repository import load_publication
from nation.models import GeoQuery, milestone
from nation import providers

ROOT = Path(__file__).resolve().parents[1]


def boxes(bounds):
    w, s, e, n = bounds
    return [box(w, s, e, n)] if w <= e else [box(w, s, 180, n), box(-180, s, e, n)]


def brief(record):
    return {k: v for k, v in record.items() if k != "detail"}


class Catalog:
    def __init__(self, root=ROOT):
        raw = (root / "data/nation/catalog.json.gz").read_bytes()
        receipt = json.loads((root / "data/nation/receipt.json").read_text())
        if hashlib.sha256(raw).hexdigest() != receipt["sha256"]:
            raise ValueError("National catalog integrity mismatch.")
        data = json.loads(gzip.decompress(raw))
        if data.get("schema_version") != 1:
            raise ValueError("Unsupported national catalog.")
        master, modes = load_publication(root)
        self.dataset = hashlib.sha256(
            json.dumps(
                [receipt["sha256"], master, modes],
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        self.records = list(data["records"])
        for p in master["projects"]:
            source = p["source_metadata"]
            self.records.append(
                {
                    "id": "canonical:" + p["project_id"],
                    "native_id": p["project_id"],
                    "kind": "project",
                    "name": p["project_name"],
                    "owner": p["utility"],
                    "states": ["45" if p["utility"] == "DESC" else "13"],
                    "counties": [],
                    "planning_region": "Southeast",
                    "status": "unknown",
                    "geometry": p.get("analysis_geometry"),
                    "confidence": {
                        "VERIFIED": "verified",
                        "ESTIMATED": "tentative",
                        "UNRESOLVED": "unresolved",
                    }[p["geometry_status"]],
                    "milestone": milestone(p.get("in_service_year"), "year"),
                    "source_id": "canonical",
                    "provenance": {
                        "provider": "canonical",
                        "coverage": "regional",
                        "source_url": source.get("source_url"),
                        "publisher": p["utility"],
                        "retrieved_at": master["generated_at"],
                        "source_updated_at": str(source.get("plan_year") or "") or None,
                    },
                    "detail": {
                        **p,
                        "geography_basis": "State filter follows source service region, not full route extent.",
                        "limitation": "Filed year and location evidence; construction status may be unknown.",
                    },
                }
            )
        self.by_id = {p["id"]: p for p in self.records}
        if len(self.by_id) != len(self.records):
            raise ValueError("Duplicate normalized project IDs.")
        self.states = {s["state_fips"]: s for s in data["geography"]["states"]}
        self.counties = data["geography"]["counties"]
        self.sources = data["sources"]
        self.receipt = receipt
        self.mapped = [p for p in self.records if p["geometry"]]
        self.shapes = [shape(p["geometry"]) for p in self.mapped]
        self.index = STRtree(self.shapes)
        self.pairs = data["pairs"]
        self.opportunities = []
        for p in modes["estimated"]["matches"]:
            self.opportunities.append(
                {
                    "id": p["match_id"],
                    "a": "canonical:" + p["project_a_id"],
                    "b": "canonical:" + p["project_b_id"],
                    "distance_km": p["distance_km"],
                    "time_gap_days": None,
                    "timeline_gap_years": p["timeline_gap_years"],
                    "classification": "regional_opportunity",
                    "method": "closest_geometry",
                    "rule": "canonical-under-40km-known-gap-lte-2years",
                    "confidence": "mixed",
                }
            )

    def select(self, q: GeoQuery):
        if q.state and q.state not in self.states:
            raise ValueError("Unknown state FIPS code.")
        records = self.records
        if q.bbox:
            indices = set()
            for bounds in boxes(q.bbox):
                indices.update(
                    int(i) for i in self.index.query(bounds, predicate="intersects")
                )
            records = [self.mapped[i] for i in sorted(indices)]
        needle = q.text.casefold()
        return [
            p
            for p in records
            if (not q.state or q.state in p["states"])
            and (
                not needle
                or needle
                in " ".join(
                    [
                        p["name"],
                        p.get("owner") or "",
                        p.get("planning_region") or "",
                        p["native_id"],
                    ]
                ).casefold()
            )
            and (not q.confidence or p["confidence"] == q.confidence)
            and (
                q.status == "all"
                or (
                    q.status == "active"
                    and p["status"] not in {"in_service", "cancelled"}
                )
                or p["status"] == q.status
            )
            and (not q.year or (p["milestone"]["value"] or "").startswith(q.year))
        ]

    def geography(self):
        counts = Counter(s for p in self.records for s in p["states"])
        return {
            "states": [
                {**s, "record_count": counts[s["state_fips"]]}
                for s in self.states.values()
            ],
            "providers": providers.REGISTRY,
            "receipt": self.receipt,
            "counts": {
                "records": len(self.records),
                "mapped": len(self.mapped),
                "sources": len({p["source_id"] for p in self.records}),
                "candidates": len(self.pairs),
                "opportunities": len(self.opportunities),
            },
            "limitations": [
                "Counts are filing records, not a complete or deduplicated census of physical projects.",
                "National geometry review is inherited from the source release. Most active locations are tentative.",
                "Active includes unknown status. A passed in-service date alone does not prove completion.",
            ],
        }

    def query(self, q):
        records = self.select(q)
        states = Counter(s for p in records for s in p["states"])
        confidence = Counter(p["confidence"] for p in records)
        years = Counter(
            p["milestone"]["value"][:4] if p["milestone"]["value"] else "Unknown"
            for p in records
        )
        features, truncated = self.features(records, q.zoom)
        return {
            "query": asdict(q),
            "total": len(records),
            "mapped": sum(bool(p["geometry"]) for p in records),
            "records": [
                brief(p)
                for p in sorted(records, key=lambda p: (p["name"], p["id"]))[
                    q.offset : q.offset + q.limit
                ]
            ],
            "next_offset": q.offset + q.limit
            if q.offset + q.limit < len(records)
            else None,
            "summary": {
                "states": dict(states),
                "confidence": dict(confidence),
                "years": dict(sorted(years.items())),
            },
            "map": {"type": "FeatureCollection", "features": features},
            "map_truncated": truncated,
            "scope_note": "Viewport excludes unlocated records."
            if q.bbox
            else "Unlocated records remain in totals and list.",
            "dataset": self.dataset,
        }

    def features(self, records, zoom):
        located = [p for p in records if p["geometry"]]
        if zoom < 7:
            step = 12 / (2 ** max(0, zoom - 2))
            groups = defaultdict(list)
            for p in located:
                c = shape(p["geometry"]).representative_point()
                groups[(math.floor(c.x / step), math.floor(c.y / step))].append((p, c))
            features = []
            for (x, y), group in sorted(groups.items()):
                features.append(
                    {
                        "type": "Feature",
                        "geometry": {
                            "type": "Point",
                            "coordinates": [
                                sum(c.x for _, c in group) / len(group),
                                sum(c.y for _, c in group) / len(group),
                            ],
                        },
                        "properties": {
                            "cluster": True,
                            "count": len(group),
                            "id": f"cell:{x}:{y}",
                            "verified": sum(
                                p["confidence"] == "verified" for p, _ in group
                            ),
                        },
                    }
                )
        else:
            features = [
                {
                    "type": "Feature",
                    "geometry": p["geometry"],
                    "properties": {
                        "id": p["id"],
                        "name": p["name"],
                        "confidence": p["confidence"],
                        "provider": p["provenance"]["provider"],
                        "date": p["milestone"]["value"],
                        "precision": p["milestone"]["precision"],
                    },
                }
                for p in located
            ]
        return features[:800], len(features) > 800

    def detail(self, identifier):
        if identifier not in self.by_id:
            raise KeyError(identifier)
        p = self.by_id[identifier]
        pairs = [
            r for r in self.pairs + self.opportunities if identifier in {r["a"], r["b"]}
        ]
        return {
            "record": p,
            "pairs": [
                {
                    **r,
                    "a_name": self.by_id[r["a"]]["name"],
                    "b_name": self.by_id[r["b"]]["name"],
                }
                for r in pairs[:50]
            ],
            "pairs_truncated": len(pairs) > 50,
            "source": next(
                (s for s in self.sources if s["_id"] == p["source_id"]), None
            ),
        }

    def candidates(self, q):
        ids = {p["id"] for p in self.select(q)}
        pairs = [
            p
            for p in self.opportunities + self.pairs
            if p["a"] in ids and p["b"] in ids
        ]
        return {
            "total": len(pairs),
            "records": [
                {
                    **p,
                    "a_name": self.by_id[p["a"]]["name"],
                    "b_name": self.by_id[p["b"]]["name"],
                }
                for p in pairs[q.offset : q.offset + q.limit]
            ],
            "next_offset": q.offset + q.limit
            if q.offset + q.limit < len(pairs)
            else None,
            "limitations": [
                "National pairs use centers under 25 straight-line miles with resolved distinct owners.",
                "National pairs are provisional, not routed coordination opportunities or confirmed shared work windows.",
                "Day gaps exist only for two exact filed dates. Regional opportunities keep their separate saved policy.",
            ],
        }

    def exposure(self, identifier):
        if identifier not in self.by_id:
            raise KeyError(identifier)
        record = self.by_id[identifier]
        result = providers.alerts()
        if not record["geometry"]:
            return {
                "status": "unavailable",
                "records": [],
                "limitations": ["Project has no eligible geometry."],
            }
        geometry = shape(record["geometry"])
        hits = []
        for alert in result.get("records", []):
            if alert["geometry"] and geometry.intersects(shape(alert["geometry"])):
                hits.append(alert)
        return {
            **result,
            "records": hits,
            "unlocated_alerts": sum(
                not a["geometry"] for a in result.get("records", [])
            ),
            "geometry_confidence": record["confidence"],
            "limitations": result.get("limitations", [])
            + [
                "No polygon intersection does not establish an all-clear; county/zone-only alerts are not spatially resolved."
            ],
        }


_catalog = None
_identity = None
_lock = threading.Lock()


def catalog():
    global _catalog, _identity
    paths = [ROOT / "data/nation/catalog.json.gz", ROOT / "data/nation/receipt.json"]
    paths += sorted((ROOT / "data/published").glob("*.json"))
    identity = tuple((str(p), p.stat().st_mtime_ns, p.stat().st_size) for p in paths)
    with _lock:
        if _catalog is None or identity != _identity:
            _catalog = Catalog()
            _identity = identity
        return _catalog
