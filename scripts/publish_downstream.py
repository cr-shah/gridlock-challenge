#!/usr/bin/env python3
"""Publish website artifacts from the pipeline-owned canonical project snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import estimated_coverage as coverage  # noqa: E402
import scoring_engine as scoring  # noqa: E402
from master_dataset import load_master, scoring_projects  # noqa: E402
from publication_validation import validate_publication  # noqa: E402

PUBLISHED_DIR = ROOT / "data" / "published"
MAX_TIMELINE_GAP_YEARS = 2


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _without_embedded_projects(match: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in match.items() if key not in {"project_a", "project_b"}}


def _schedule_aligned(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return the same <=2-year subset published as Best Matches in the analyst workbook."""
    return [
        match
        for match in matches
        if match.get("timeline_gap_years") is not None
        and match["timeline_gap_years"] <= MAX_TIMELINE_GAP_YEARS
    ]


def _policy_summary(
    summary: dict[str, Any],
    candidates: list[dict[str, Any]],
    opportunities: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        **summary,
        "candidate_pairs_within_40km": len(candidates),
        "schedule_aligned_opportunities": len(opportunities),
        "max_timeline_gap_years": MAX_TIMELINE_GAP_YEARS,
    }


def build_website_data(master: dict[str, Any]) -> dict[str, Any]:
    verified = scoring_projects(master, "verified")
    full = scoring_projects(master, "full")

    _normalized, verified_candidates, verified_summary = scoring.analyze_projects(
        verified, dataset="verified"
    )
    full_candidates = coverage.score_estimated(full)
    full_summary = coverage.summarize(full, full_candidates)
    full_summary["pairs_checked"] = coverage.evaluable_pair_count(full)

    verified_matches = _schedule_aligned(verified_candidates)
    full_matches = _schedule_aligned(full_candidates)

    return {
        "dataset_version": master["dataset_version"],
        "generated_at": master["generated_at"],
        "pipeline_commit": master["pipeline_commit"],
        "opportunity_policy": {
            "distance_km_lt": 40,
            "timeline_gap_years_lte": MAX_TIMELINE_GAP_YEARS,
            "unknown_timing_eligible": False,
        },
        "projects": full
        + [
            scoring_projects({"projects": [project], "total_projects": 1}, "all")[0]
            for project in master["projects"]
            if project["geometry_status"] == "UNRESOLVED"
        ],
        "modes": {
            "verified": {
                "summary": _policy_summary(
                    verified_summary, verified_candidates, verified_matches
                ),
                "matches": [_without_embedded_projects(match) for match in verified_matches],
            },
            "full": {
                "summary": _policy_summary(full_summary, full_candidates, full_matches),
                "matches": [_without_embedded_projects(match) for match in full_matches],
            },
        },
    }


def build_project_explorer(master: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "project_id",
        "utility",
        "project_name",
        "project_type",
        "voltage",
        "planned_start_year",
        "planned_end_year",
        "in_service_year",
        "status",
        "geometry_status",
        "geometry_method",
        "geometry_confidence",
    )
    return {
        "dataset_version": master["dataset_version"],
        "generated_at": master["generated_at"],
        "pipeline_commit": master["pipeline_commit"],
        "total_projects": master["total_projects"],
        "projects": [{key: project[key] for key in keys} for project in master["projects"]],
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_head() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _master_manifest_verified(local_master: Path) -> bool:
    manifest_path = ROOT.parent / "gridlock-data-pipeline/data/published/publication_manifest.json"
    if not manifest_path.exists():
        return False
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifact = manifest.get("artifacts", {}).get("gridlock_master_projects.json", {})
    return artifact.get("sha256") == _sha256(local_master)


def publish(master_path: Path) -> dict[str, Any]:
    master = load_master(master_path)
    PUBLISHED_DIR.mkdir(parents=True, exist_ok=True)
    local_master = PUBLISHED_DIR / "gridlock_master_projects.json"
    if master_path.resolve() != local_master.resolve():
        shutil.copyfile(master_path, local_master)

    website = build_website_data(master)
    validate_publication(master, website)
    explorer = build_project_explorer(master)
    full_summary = website["modes"]["full"]["summary"]
    verified_summary = website["modes"]["verified"]["summary"]
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
    summary.update(
        {
            "candidate_pairs_within_40km": full_summary["candidate_pairs_within_40km"],
            "schedule_aligned_opportunities": full_summary["schedule_aligned_opportunities"],
            "verified_schedule_aligned_opportunities": verified_summary[
                "schedule_aligned_opportunities"
            ],
            "max_timeline_gap_years": MAX_TIMELINE_GAP_YEARS,
        }
    )

    artifacts = {
        "gridlock_master_projects.json": local_master,
        "website_data.json": PUBLISHED_DIR / "website_data.json",
        "project_explorer.json": PUBLISHED_DIR / "project_explorer.json",
        "summary_statistics.json": PUBLISHED_DIR / "summary_statistics.json",
    }
    _write_json(artifacts["website_data.json"], website)
    _write_json(artifacts["project_explorer.json"], explorer)
    _write_json(artifacts["summary_statistics.json"], summary)
    from scripts.export_all_pairs_excel import export_workbook

    workbook_summary = export_workbook(
        PUBLISHED_DIR / "gridlock_all_project_pairs.xlsx", master_path=local_master
    )
    receipt = {
        "dataset_version": master["dataset_version"],
        "generated_at": master["generated_at"],
        "pipeline_commit": master["pipeline_commit"],
        "source_product_commit": _git_head(),
        "imported_at": datetime.now(timezone.utc).isoformat(),
        "upstream_manifest_verified": _master_manifest_verified(local_master),
        "opportunity_policy": website["opportunity_policy"],
        "artifacts": {name: _sha256(path) for name, path in artifacts.items()},
    }
    _write_json(PUBLISHED_DIR / "import_receipt.json", receipt)
    return {"master": master, "summary": summary, "workbook": workbook_summary}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--master", type=Path, required=True)
    args = parser.parse_args()
    result = publish(args.master.resolve())
    print(json.dumps(result["summary"], indent=2))


if __name__ == "__main__":
    main()
