#!/usr/bin/env python3
"""Export every geometrically resolvable DESC x GPC pair to Excel.

This is a reporting-only path. Verified geometry is preferred and missing
geometry is filled from data/estimated_geometry.json. For this export, both
sources use the same closest-point distance calculation and tier thresholds.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import estimated_coverage as coverage  # noqa: E402
import scoring_engine as scoring  # noqa: E402
from master_dataset import load_master, scoring_projects  # noqa: E402


MASTER_PATH = ROOT / "data" / "published" / "gridlock_master_projects.json"
OUTPUT_PATH = ROOT / "data" / "published" / "gridlock_all_project_pairs.xlsx"

PAIR_COLUMNS = [
    "DESC Project Name",
    "DESC Year",
    "GPC Project Name",
    "GPC Year",
    "Year Gap",
    "Distance (km)",
    "Distance Tier",
    "DESC Geometry Type",
    "GPC Geometry Type",
    "DESC Geometry Method",
    "GPC Geometry Method",
    "DESC Geometry Confidence",
    "GPC Geometry Confidence",
]

UNRESOLVED_COLUMNS = [
    "Utility",
    "Project Name",
    "Project Year",
    "Project ID",
    "Reason",
]

PROJECT_COLUMNS = [
    "Project ID",
    "Utility",
    "Project Name",
    "Planned Start Year",
    "Planned End Year",
    "In-Service Year",
    "Geometry Status",
    "Geometry Type",
    "Geometry Method",
    "Geometry Confidence",
]

HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
HEADER_FONT = Font(color="FFFFFF", bold=True)
ALT_FILL = PatternFill("solid", fgColor="D9EAF7")


def project_year(project: dict[str, Any]) -> int | str | None:
    """Return the same comparison window used by the existing engine."""
    start, end = scoring.project_year_window(project)
    if start is None:
        return None
    if start == end:
        return int(start)
    return f"{int(start)}–{int(end)}"


def distance_tier(distance_km: float, intersects: bool) -> str:
    if intersects or distance_km <= scoring.TOUCHING_EPS_KM:
        return "Touching / Crossing"
    if distance_km < 1.6:
        return "<1.6 km"
    if distance_km < 8.0:
        return "<8 km"
    if distance_km < 40.0:
        return "<40 km"
    return ">40 km"


def sort_key(row: dict[str, Any]) -> tuple[float, float, str, str]:
    gap = row["Year Gap"]
    return (
        float("inf") if gap is None else gap,
        row["_distance_raw"],
        row["DESC Project Name"],
        row["GPC Project Name"],
    )


def build_rows(projects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    desc = [
        project
        for project in projects
        if project.get("utility") == "DESC"
        and coverage.parts_from_geometry(project.get("geometry"), project.get("geometry_type"))
    ]
    gpc = [
        project
        for project in projects
        if project.get("utility") == "GPC"
        and coverage.parts_from_geometry(project.get("geometry"), project.get("geometry_type"))
    ]

    rows: list[dict[str, Any]] = []
    for desc_project in desc:
        desc_parts = coverage.parts_from_geometry(
            desc_project.get("geometry"), desc_project.get("geometry_type")
        )
        for gpc_project in gpc:
            gpc_parts = coverage.parts_from_geometry(
                gpc_project.get("geometry"), gpc_project.get("geometry_type")
            )
            distance_km, intersects, _closest_desc, _closest_gpc = coverage.closest_distance_km(
                desc_parts, gpc_parts
            )
            _overlap, year_gap, _overlap_years = scoring.timeline_relationship(
                desc_project, gpc_project
            )
            rows.append(
                {
                    "DESC Project Name": desc_project.get("name"),
                    "DESC Year": project_year(desc_project),
                    "GPC Project Name": gpc_project.get("name"),
                    "GPC Year": project_year(gpc_project),
                    "Year Gap": year_gap,
                    "Distance (km)": round(distance_km, 2),
                    "Distance Tier": distance_tier(distance_km, intersects),
                    "DESC Geometry Type": desc_project.get("geometry_type"),
                    "GPC Geometry Type": gpc_project.get("geometry_type"),
                    "DESC Geometry Method": desc_project.get("geometry_method"),
                    "GPC Geometry Method": gpc_project.get("geometry_method"),
                    "DESC Geometry Confidence": desc_project.get("geometry_confidence"),
                    "GPC Geometry Confidence": gpc_project.get("geometry_confidence"),
                    "_distance_raw": distance_km,
                }
            )
    return sorted(rows, key=sort_key)


def unresolved_rows(
    projects: list[dict[str, Any]], unresolved_payload: list[dict[str, Any]] | None = None
) -> list[dict[str, Any]]:
    reasons = {
        item.get("project_id"): item.get("reason")
        for item in (unresolved_payload or [])
    }
    rows = []
    for project in projects:
        if coverage.parts_from_geometry(project.get("geometry"), project.get("geometry_type")):
            continue
        rows.append(
            {
                "Utility": project.get("utility"),
                "Project Name": project.get("name"),
                "Project Year": project_year(project),
                "Project ID": project.get("id"),
                "Reason": project.get("unresolved_reason")
                or reasons.get(project.get("id"))
                or "No verified or estimated geometry available",
            }
        )
    return sorted(rows, key=lambda row: (row["Utility"] or "", row["Project Name"] or ""))


def style_sheet(sheet, columns: list[str], row_count: int) -> None:
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = f"A1:{get_column_letter(len(columns))}{max(row_count + 1, 1)}"
    sheet.sheet_view.showGridLines = False
    sheet.row_dimensions[1].height = 30

    for cell in sheet[1]:
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for row_number in range(2, row_count + 2):
        if row_number % 2 == 0:
            for cell in sheet[row_number]:
                cell.fill = ALT_FILL
        for cell in sheet[row_number]:
            cell.alignment = Alignment(vertical="top", wrap_text=False)

    preferred_widths = {
        "DESC Project Name": 50,
        "GPC Project Name": 50,
        "DESC Year": 14,
        "GPC Year": 14,
        "Year Gap": 11,
        "Distance (km)": 14,
        "Distance Tier": 20,
        "DESC Geometry Type": 22,
        "GPC Geometry Type": 22,
        "DESC Geometry Method": 36,
        "GPC Geometry Method": 36,
        "DESC Geometry Confidence": 25,
        "GPC Geometry Confidence": 25,
        "Utility": 12,
        "Project Name": 58,
        "Project Year": 16,
        "Planned Start Year": 18,
        "Planned End Year": 18,
        "In-Service Year": 16,
        "Project ID": 42,
        "Reason": 58,
        "Project ID": 42,
        "Geometry Status": 20,
        "Geometry Type": 20,
        "Geometry Method": 36,
        "Geometry Confidence": 24,
    }
    for index, heading in enumerate(columns, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = preferred_widths.get(heading, 18)

    if "Distance (km)" in columns:
        distance_column = columns.index("Distance (km)") + 1
        for row_number in range(2, row_count + 2):
            sheet.cell(row=row_number, column=distance_column).number_format = "0.00"
    if "Year Gap" in columns:
        gap_column = columns.index("Year Gap") + 1
        for row_number in range(2, row_count + 2):
            sheet.cell(row=row_number, column=gap_column).number_format = "0"


def add_sheet(workbook: Workbook, title: str, columns: list[str], rows: list[dict[str, Any]]):
    sheet = workbook.create_sheet(title)
    sheet.append(columns)
    for row in rows:
        sheet.append([row.get(column) for column in columns])
    style_sheet(sheet, columns, len(rows))
    return sheet


def export_workbook(output_path: Path, *, master_path: Path = MASTER_PATH) -> dict[str, Any]:
    master = load_master(master_path)
    all_projects = scoring_projects(master, "all")
    projects = scoring_projects(master, "full")

    rows = build_rows(projects)
    unresolved = unresolved_rows(all_projects)
    same_year = sorted(
        (row for row in rows if row["Year Gap"] == 0),
        key=lambda row: (row["_distance_raw"], row["DESC Project Name"], row["GPC Project Name"]),
    )
    within_40 = sorted(
        (row for row in rows if row["_distance_raw"] < 40.0),
        key=sort_key,
    )
    best_matches = [
        row
        for row in within_40
        if row["Year Gap"] is not None and row["Year Gap"] <= 2
    ]

    workbook = Workbook()
    workbook.remove(workbook.active)
    project_rows = [
        {
            "Project ID": project.get("id"),
            "Utility": project.get("utility"),
            "Project Name": project.get("name"),
            "Planned Start Year": project.get("planned_start_year"),
            "Planned End Year": project.get("planned_end_year"),
            "In-Service Year": project.get("in_service_year"),
            "Geometry Status": project.get("geometry_status"),
            "Geometry Type": project.get("geometry_type"),
            "Geometry Method": project.get("geometry_method"),
            "Geometry Confidence": project.get("geometry_confidence"),
        }
        for project in all_projects
    ]
    add_sheet(workbook, "Projects", PROJECT_COLUMNS, project_rows)
    add_sheet(workbook, "All Evaluated Pairs", PAIR_COLUMNS, rows)
    add_sheet(workbook, "Same Year", PAIR_COLUMNS, same_year)
    add_sheet(workbook, "Within 40 km", PAIR_COLUMNS, within_40)
    add_sheet(workbook, "Best Matches", PAIR_COLUMNS, best_matches)
    add_sheet(workbook, "Unresolved Projects", UNRESOLVED_COLUMNS, unresolved)
    workbook.calculation.fullCalcOnLoad = True
    output_path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(output_path)

    return {
        "output_path": output_path,
        "total_projects": len(all_projects),
        "projects_with_geometry": len(projects),
        "evaluated_pairs": len(rows),
        "same_year_pairs": len(same_year),
        "same_year_under_40": sum(row["_distance_raw"] < 40.0 for row in same_year),
        "best_matches": len(best_matches),
        "closest_20": sorted(rows, key=lambda row: row["_distance_raw"])[:20],
    }


def print_summary(summary: dict[str, Any]) -> None:
    print(f"Excel file: {summary['output_path']}")
    print()
    print(f"TOTAL PROJECTS: {summary['total_projects']}")
    print(f"PROJECTS WITH GEOMETRY: {summary['projects_with_geometry']}")
    print(f"EVALUATED DESC × GPC PAIRS: {summary['evaluated_pairs']}")
    print(f"SAME-YEAR PAIRS: {summary['same_year_pairs']}")
    print(f"SAME-YEAR PAIRS UNDER 40 KM: {summary['same_year_under_40']}")
    print(
        "PAIRS WITH YEAR GAP <= 2 AND UNDER 40 KM: "
        f"{summary['best_matches']}"
    )
    print()
    print("CLOSEST 20 PAIRS:")
    for row in summary["closest_20"]:
        print(
            f"{row['DESC Project Name']} | {row['DESC Year']} | "
            f"{row['GPC Project Name']} | {row['GPC Year']} | "
            f"{row['Year Gap'] if row['Year Gap'] is not None else 'unknown'} | "
            f"{row['Distance (km)']:.2f} km"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    parser.add_argument("--master", type=Path, default=MASTER_PATH)
    args = parser.parse_args()
    summary = export_workbook(args.output.resolve(), master_path=args.master.resolve())
    print_summary(summary)


if __name__ == "__main__":
    main()
