"""Normalized public API contracts. Coordinates always use longitude, latitude."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
import math
from typing import Any
from urllib.parse import parse_qs, urlsplit


def coordinate(lon: Any, lat: Any) -> tuple[float, float]:
    if (
        any(
            isinstance(v, bool)
            or not isinstance(v, (float, int))
            or not math.isfinite(v)
            for v in (lon, lat)
        )
        or not -180 <= lon <= 180
        or not -90 <= lat <= 90
    ):
        raise ValueError("Coordinates must be finite WGS84 longitude/latitude.")
    return float(lon), float(lat)


def safe_url(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    p = urlsplit(value)
    return (
        value
        if p.scheme in {"http", "https"}
        and p.hostname
        and not p.username
        and not p.password
        else None
    )


def milestone(value: Any, precision: str) -> dict:
    if not value or precision == "unknown":
        return {"value": None, "precision": "unknown"}
    value = str(value)
    formats = {"year": 4, "month": 7, "day": 10}
    if precision not in formats or len(value) != formats[precision]:
        raise ValueError("Milestone does not match its precision.")
    date.fromisoformat(value + {"year": "-01-01", "month": "-01", "day": ""}[precision])
    if not 1900 <= int(value[:4]) <= 2200:
        raise ValueError("Milestone year is outside the supported research range.")
    return {"value": value, "precision": precision}


@dataclass(frozen=True)
class GeoQuery:
    bbox: tuple[float, float, float, float] | None = None
    state: str = ""
    text: str = ""
    status: str = "active"
    confidence: str = ""
    zoom: int = 3
    limit: int = 60
    offset: int = 0
    year: str = ""

    @classmethod
    def parse(cls, query: str) -> "GeoQuery":
        raw = parse_qs(query, keep_blank_values=True)
        if any(len(v) != 1 for v in raw.values()):
            raise ValueError("Repeated query parameters are not supported.")
        q = {k: v[0] for k, v in raw.items()}
        if set(q) - {
            "bbox",
            "state",
            "text",
            "status",
            "confidence",
            "zoom",
            "limit",
            "offset",
            "year",
        }:
            raise ValueError("Unknown query parameter.")
        bbox = None
        if q.get("bbox"):
            bbox = tuple(float(v) for v in q["bbox"].split(","))
            if len(bbox) != 4:
                raise ValueError("bbox must be west,south,east,north.")
            coordinate(bbox[0], bbox[1])
            coordinate(bbox[2], bbox[3])
            if bbox[1] >= bbox[3] or bbox[0] == bbox[2]:
                raise ValueError("bbox must have a nonzero width and positive height.")
        state = q.get("state", "")
        if state and (len(state) != 2 or not state.isdigit()):
            raise ValueError("state must be a two-digit FIPS code.")
        zoom, limit, offset = (
            int(q.get(k, d)) for k, d in [("zoom", 3), ("limit", 60), ("offset", 0)]
        )
        if not 1 <= zoom <= 18 or not 1 <= limit <= 200 or not 0 <= offset <= 100000:
            raise ValueError("Invalid zoom, page size or offset.")
        status = q.get("status", "active")
        if status not in {
            "active",
            "all",
            "planned",
            "proposed",
            "under_construction",
            "in_service",
            "cancelled",
            "unknown",
        }:
            raise ValueError("Invalid status.")
        confidence = q.get("confidence", "")
        if confidence not in {"", "verified", "official", "tentative", "unresolved"}:
            raise ValueError("Invalid confidence.")
        year = q.get("year", "")
        if year and (not year.isdigit() or not 1900 <= int(year) <= 2200):
            raise ValueError("Invalid year.")
        text = q.get("text", "").strip()
        if len(text) > 120:
            raise ValueError("Search is limited to 120 characters.")
        return cls(bbox, state, text, status, confidence, zoom, limit, offset, year)


@dataclass
class ProviderResult:
    provider: str
    status: str
    coverage: str
    records: list[dict] = field(default_factory=list)
    retrieved_at: str | None = None
    source_updated_at: str | None = None
    limitations: list[str] = field(default_factory=list)
    truncated: bool = False

    def json(self) -> dict:
        return asdict(self)
