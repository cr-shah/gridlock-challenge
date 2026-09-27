"""Adapters for the pipeline-published canonical Gridlock dataset."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

GEOMETRY_STATUSES = frozenset({"VERIFIED", "ESTIMATED", "UNRESOLVED"})


def load_master(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    projects = payload.get("projects")
    if not isinstance(projects, list):
        raise ValueError(f"{path} must contain a projects array")
    ids = [project.get("project_id") for project in projects]
    if any(not isinstance(project_id, str) or not project_id for project_id in ids):
        raise ValueError("every canonical project needs a stable project_id")
    if len(ids) != len(set(ids)):
        raise ValueError("canonical project IDs must be unique")
    statuses = {project.get("geometry_status") for project in projects}
    if statuses - GEOMETRY_STATUSES:
        raise ValueError(f"unsupported geometry statuses: {sorted(statuses - GEOMETRY_STATUSES)}")
    if payload.get("total_projects") != len(projects):
        raise ValueError("canonical total_projects does not match projects array")
    return payload


def to_scoring_project(project: dict[str, Any]) -> dict[str, Any]:
    source = project.get("source_metadata") or {}
    geometry = project.get("analysis_geometry")
    geometry_type = geometry.get("type") if isinstance(geometry, dict) else None
    return {
        "id": project["project_id"],
        "utility": project.get("utility"),
        "name": project.get("project_name"),
        "project_type": project.get("project_type"),
        "planned_start_year": project.get("planned_start_year"),
        "planned_end_year": project.get("planned_end_year"),
        "in_service_year": project.get("in_service_year"),
        "voltage_kv": project.get("voltage") or [],
        "status": project.get("status"),
        "geometry": geometry,
        "geometry_type": geometry_type,
        "geometry_status": project.get("geometry_status"),
        "geometry_method": project.get("geometry_method"),
        "geometry_confidence": project.get("geometry_confidence"),
        "geometry_source": project.get("geometry_source"),
        "geometry_notes": project.get("geometry_notes"),
        "tier_eligibility": project.get("geometry_tier_eligibility"),
        "estimated_geometry": project.get("geometry_status") == "ESTIMATED",
        "unresolved_reason": project.get("unresolved_reason"),
        "source_url": source.get("source_url"),
        "source_page": source.get("source_page"),
        "data_confidence": source.get("data_confidence"),
        "county_region": project.get("county_region"),
        "endpoint_candidates": project.get("endpoint_candidates") or [],
    }


def scoring_projects(payload: dict[str, Any], mode: str) -> list[dict[str, Any]]:
    allowed = {
        "verified": {"VERIFIED"},
        "full": {"VERIFIED", "ESTIMATED"},
        "all": GEOMETRY_STATUSES,
    }
    if mode not in allowed:
        raise ValueError(f"unsupported master dataset mode: {mode}")
    return [
        to_scoring_project(project)
        for project in payload["projects"]
        if project.get("geometry_status") in allowed[mode]
    ]
