#!/usr/bin/env python3
"""Regenerate every product artifact from the pipeline master dataset."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import estimated_coverage as coverage  # noqa: E402
import scoring_engine as scoring  # noqa: E402
from master_dataset import load_master, scoring_projects  # noqa: E402
from scripts.export_all_pairs_excel import export_workbook  # noqa: E402


PUBLISHED_DIR = ROOT / "data" / "published"


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _without_embedded_projects(match: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in match.items() if key not in {"project_a", "project_b"}}


def build_website_data(master: dict[str, Any]) -> dict[str, Any]:
    verified = scoring_projects(master, "verified")
    full = scoring_projects(master, "full")

    _verified_normalized, verified_matches, verified_summary = scoring.analyze_projects(
        verified, dataset="verified"
    )
    full_matches = coverage.score_estimated(full)
    full_summary = coverage.summarize(full, full_matches)
    full_summary["pairs_checked"] = coverage.evaluable_pair_count(full)

    return {
        "dataset_version": master["dataset_version"],
        "generated_at": master["generated_at"],
        "pipeline_commit": master["pipeline_commit"],
        "projects": full + [
            scoring_projects({"projects": [project], "total_projects": 1}, "all")[0]
            for project in master["projects"]
            if project["geometry_status"] == "UNRESOLVED"
        ],
        "modes": {
            "verified": {
                "summary": verified_summary,
                "matches": [_without_embedded_projects(match) for match in verified_matches],
            },
            "full": {
                "summary": full_summary,
                "matches": [_without_embedded_projects(match) for match in full_matches],
            },
        },
    }


def build_project_explorer(master: dict[str, Any]) -> dict[str, Any]:
    return {
        "dataset_version": master["dataset_version"],
        "generated_at": master["generated_at"],
        "pipeline_commit": master["pipeline_commit"],
        "total_projects": master["total_projects"],
        "projects": [
            {
                "project_id": project["project_id"],
                "utility": project["utility"],
                "project_name": project["project_name"],
                "project_type": project["project_type"],
                "voltage": project["voltage"],
                "planned_start_year": project["planned_start_year"],
                "planned_end_year": project["planned_end_year"],
                "in_service_year": project["in_service_year"],
                "status": project["status"],
                "geometry_status": project["geometry_status"],
                "geometry_method": project["geometry_method"],
                "geometry_confidence": project["geometry_confidence"],
            }
            for project in master["projects"]
        ],
    }


def publish(master_path: Path) -> dict[str, Any]:
    master = load_master(master_path)
    PUBLISHED_DIR.mkdir(parents=True, exist_ok=True)
    local_master = PUBLISHED_DIR / "gridlock_master_projects.json"
    if master_path.resolve() != local_master.resolve():
        shutil.copyfile(master_path, local_master)

    website = build_website_data(master)
    explorer = build_project_explorer(master)
    summary = {
        key: master[key]
        for key in (
            "dataset_version",
            "generated_at",
            "pipeline_commit",
            "total_projects",
            "DESC_count",
            "GPC_count",
            "verified_geometry_count",
            "estimated_geometry_count",
            "unresolved_count",
        )
    }
    summary["verified_pairs_within_40km"] = website["modes"]["verified"]["summary"][
        "pairs_within_40km"
    ]
    summary["full_pairs_within_40km"] = website["modes"]["full"]["summary"][
        "pairs_within_40km"
    ]

    _write_json(PUBLISHED_DIR / "website_data.json", website)
    _write_json(PUBLISHED_DIR / "project_explorer.json", explorer)
    _write_json(PUBLISHED_DIR / "summary_statistics.json", summary)
    excel_summary = export_workbook(
        PUBLISHED_DIR / "gridlock_all_project_pairs.xlsx",
        master_path=local_master,
    )
    return {"master": master, "summary": summary, "excel": excel_summary}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--master", type=Path, required=True)
    args = parser.parse_args()
    result = publish(args.master.resolve())
    print(json.dumps(result["summary"], indent=2))


if __name__ == "__main__":
    main()
