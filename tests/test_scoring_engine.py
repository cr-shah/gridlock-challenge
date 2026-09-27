"""Focused tests for the DESC × GPC coordination engine."""

from __future__ import annotations

import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scoring_engine as se


REF_LAT = 32.15
REF_LNG = -81.24


def offset_point(north_km=0.0, east_km=0.0, lat=REF_LAT, lng=REF_LNG):
    dlat = north_km / (se.EARTH_RADIUS_KM * math.pi / 180)
    dlng = east_km / (se.EARTH_RADIUS_KM * math.pi / 180 * math.cos(math.radians(lat)))
    return lat + dlat, lng + dlng


def point_project(pid, utility, north_km=0.0, east_km=0.0, **extra):
    lat, lng = offset_point(north_km, east_km)
    record = {
        "id": pid,
        "utility": utility,
        "name": extra.pop("name", pid),
        "geometry": [lng, lat],
        "geometry_type": "Point",
        "planned_start_year": extra.pop("planned_start_year", 2027),
        "planned_end_year": extra.pop("planned_end_year", 2028),
        "data_confidence": extra.pop("data_confidence", "HIGH"),
    }
    record.update(extra)
    return record


def line_project(pid, utility, start_offset, end_offset, **extra):
    lat1, lng1 = offset_point(*start_offset)
    lat2, lng2 = offset_point(*end_offset)
    record = {
        "id": pid,
        "utility": utility,
        "name": extra.pop("name", pid),
        "geometry": [[lng1, lat1], [lng2, lat2]],
        "geometry_type": "LineString",
        "planned_start_year": extra.pop("planned_start_year", 2027),
        "planned_end_year": extra.pop("planned_end_year", 2028),
    }
    record.update(extra)
    return record


class CrossUtilityTests(unittest.TestCase):
    def test_same_utility_pairs_are_never_compared(self):
        desc_a = point_project("d1", "DESC")
        desc_b = point_project("d2", "DESC", east_km=0.1)
        self.assertIsNone(se.compare_pair(desc_a, desc_b))
        self.assertFalse(se.is_desc_gpc_pair(desc_a, desc_b))

    def test_only_desc_times_gpc_pairs_are_emitted(self):
        projects = [
            point_project("d1", "DESC"),
            point_project("g1", "GPC", east_km=1.0),
            point_project("d2", "DESC", north_km=0.2),
            {
                "id": "duke-1",
                "utility": "DUKE",
                "name": "Should be ignored",
                "geometry": [REF_LNG, REF_LAT],
                "geometry_type": "Point",
                "planned_start_year": 2027,
                "planned_end_year": 2028,
            },
        ]
        normalized, matches, summary = se.analyze_projects(projects)
        self.assertEqual(summary["total_projects"], 3)
        self.assertEqual(summary["pairs_checked"], 2)
        self.assertTrue(all(m["project_a"]["utility"] == "DESC" for m in matches))
        self.assertTrue(all(m["project_b"]["utility"] == "GPC" for m in matches))
        self.assertTrue(all(m["project_a_id"].startswith("d") for m in matches))
        self.assertNotIn("duke-1", {p["id"] for p in normalized})


class DistanceTierTests(unittest.TestCase):
    def _tier_for(self, km):
        desc = point_project("d1", "DESC")
        gpc = point_project("g1", "GPC", east_km=km)
        return se.compare_pair(desc, gpc)

    def test_crossing_is_must_coordinate(self):
        desc = line_project("d1", "DESC", (0, -2), (0, 2))
        gpc = line_project("g1", "GPC", (-2, 0), (2, 0))
        match = se.compare_pair(desc, gpc)
        self.assertIsNotNone(match)
        self.assertEqual(match["distance_tier"], se.TIER_MUST)
        self.assertEqual(match["distance_tier_label"], "Must coordinate")
        self.assertLessEqual(match["distance_km"], 0.01)

    def test_zero_distance_is_must_coordinate(self):
        match = self._tier_for(0.0)
        self.assertEqual(match["distance_tier"], se.TIER_MUST)

    def test_under_1_6_km_is_shared_land(self):
        match = self._tier_for(1.0)
        self.assertEqual(match["distance_tier"], se.TIER_LAND)
        self.assertEqual(match["distance_tier_label"], "Shared land / ROW potential")

    def test_exactly_1_6_km_falls_into_logistics_tier(self):
        match = self._tier_for(1.6)
        self.assertEqual(match["distance_tier"], se.TIER_LOGISTICS)

    def test_under_8_km_is_shared_logistics(self):
        match = self._tier_for(5.0)
        self.assertEqual(match["distance_tier"], se.TIER_LOGISTICS)
        self.assertEqual(match["distance_tier_label"], "Shared site logistics potential")

    def test_exactly_8_km_falls_into_crews_tier(self):
        match = self._tier_for(8.0)
        self.assertEqual(match["distance_tier"], se.TIER_CREWS)

    def test_under_40_km_is_shared_crews(self):
        match = self._tier_for(20.0)
        self.assertEqual(match["distance_tier"], se.TIER_CREWS)
        self.assertEqual(match["distance_tier_label"], "Shared crews / equipment potential")

    def test_exactly_40_km_is_excluded(self):
        self.assertIsNone(self._tier_for(40.0))

    def test_over_40_km_is_excluded(self):
        self.assertIsNone(self._tier_for(50.0))
        _normalized, matches, summary = se.analyze_projects([
            point_project("d1", "DESC"),
            point_project("g1", "GPC", east_km=50.0),
        ])
        self.assertEqual(summary["pairs_checked"], 1)
        self.assertEqual(summary["pairs_within_40km"], 0)
        self.assertEqual(matches, [])


class TimelineTests(unittest.TestCase):
    def test_overlapping_windows(self):
        overlap, gap, years = se.timeline_relationship(
            {"planned_start_year": 2027, "planned_end_year": 2029},
            {"planned_start_year": 2028, "planned_end_year": 2030},
        )
        self.assertTrue(overlap)
        self.assertEqual(gap, 0)
        self.assertEqual(years, [2028, 2029])

    def test_non_overlapping_windows_report_gap(self):
        overlap, gap, years = se.timeline_relationship(
            {"planned_start_year": 2026, "planned_end_year": 2027},
            {"planned_start_year": 2029, "planned_end_year": 2030},
        )
        self.assertFalse(overlap)
        self.assertEqual(gap, 2)
        self.assertIsNone(years)

    def test_in_service_year_used_when_planned_years_missing(self):
        overlap, gap, years = se.timeline_relationship(
            {"in_service_year": 2028},
            {"planned_start_year": 2028, "planned_end_year": 2029},
        )
        self.assertTrue(overlap)
        self.assertEqual(gap, 0)
        self.assertEqual(years, [2028, 2028])

    def test_missing_years_are_not_treated_as_overlap(self):
        desc = point_project("d1", "DESC")
        desc.pop("planned_start_year")
        desc.pop("planned_end_year")
        gpc = point_project("g1", "GPC", east_km=1.0)
        match = se.compare_pair(desc, gpc)
        self.assertIsNotNone(match)
        self.assertFalse(match["timeline_overlap"])
        self.assertIsNone(match["timeline_gap_years"])
        self.assertIn("unknown", match["priority_explanation"])

    def test_overlap_adds_secondary_bonus_only(self):
        with_overlap = se.score_match(se.TIER_CREWS, True)
        without = se.score_match(se.TIER_CREWS, False)
        self.assertEqual(with_overlap - without, se.TIMELINE_OVERLAP_BONUS)
        self.assertLess(with_overlap, se.TIER_GEO_SCORE[se.TIER_LOGISTICS])


class EmptyAndMissingFieldTests(unittest.TestCase):
    def test_empty_verified_dataset(self):
        normalized, matches, summary = se.analyze_projects([])
        self.assertEqual(normalized, [])
        self.assertEqual(matches, [])
        self.assertEqual(summary, se.empty_summary())

        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "verified_projects.json"
            dst = Path(tmp) / "analysis.json"
            src.write_text(json.dumps({"dataset": "verified", "projects": []}))
            output = se.run(str(src), str(dst), dataset="verified")
            self.assertEqual(output["dataset"], "verified")
            self.assertEqual(output["summary"]["total_projects"], 0)
            self.assertEqual(output["matches"], [])
            written = json.loads(dst.read_text())
            self.assertEqual(written["match_count"], 0)

    def test_missing_optional_fields_are_left_blank(self):
        raw = {
            "id": "desc-min",
            "utility": "DESC",
            "name": "Minimal DESC project",
            "geometry": [REF_LNG, REF_LAT],
            "geometry_type": "Point",
        }
        project = se.normalize_project(raw, dataset="verified")
        self.assertIsNone(project["project_type"])
        self.assertIsNone(project["planned_start_year"])
        self.assertIsNone(project["planned_end_year"])
        self.assertIsNone(project["in_service_year"])
        self.assertEqual(project["voltage_kv"], [])
        self.assertIsNone(project["source_url"])
        self.assertIsNone(project["source_page"])
        self.assertIsNone(project["data_confidence"])
        self.assertIsNone(project["geometry_source"])
        self.assertIsNone(project["geometry_method"])
        self.assertIsNone(project["geometry_confidence"])
        self.assertIsNone(project["geometry_notes"])

    def test_missing_geometry_is_counted_but_not_paired(self):
        projects = [
            {
                "id": "d1",
                "utility": "DESC",
                "name": "No geometry yet",
                "planned_start_year": 2027,
                "planned_end_year": 2028,
            },
            point_project("g1", "GPC"),
        ]
        _normalized, matches, summary = se.analyze_projects(projects)
        self.assertEqual(summary["total_projects"], 2)
        self.assertEqual(summary["projects_without_geometry"], 1)
        self.assertEqual(summary["pairs_checked"], 0)
        self.assertEqual(matches, [])

    def test_legacy_latlng_and_year_fields_still_work(self):
        raw = {
            "id": "desc-legacy",
            "utility": "DESC",
            "name": "Legacy shape",
            "lat1": REF_LAT,
            "lng1": REF_LNG,
            "lat2": REF_LAT,
            "lng2": REF_LNG + 0.01,
            "start_year": 2027,
            "end_year": 2028,
            "source_url": "https://example.com",
        }
        project = se.normalize_project(raw, dataset="demo")
        self.assertEqual(project["geometry_type"], "LineString")
        self.assertEqual(project["planned_start_year"], 2027)
        self.assertEqual(project["data_confidence"], "LOW")
        match = se.compare_pair(raw, point_project("g1", "GPC", east_km=1.0))
        self.assertIsNotNone(match)


class RankingTests(unittest.TestCase):
    def test_geography_outranks_timeline(self):
        projects = [
            point_project("d-far-overlap", "DESC", east_km=0.0, planned_start_year=2027, planned_end_year=2028),
            point_project(
                "g-far-overlap",
                "GPC",
                east_km=20.0,
                planned_start_year=2027,
                planned_end_year=2028,
            ),
            point_project("d-near-gap", "DESC", north_km=30.0, planned_start_year=2026, planned_end_year=2026),
            point_project(
                "g-near-gap",
                "GPC",
                north_km=30.0,
                east_km=1.0,
                planned_start_year=2029,
                planned_end_year=2030,
            ),
        ]
        _normalized, matches, _summary = se.analyze_projects(projects)
        self.assertGreaterEqual(len(matches), 2)
        # 1 km land-tier pair without overlap must beat a 20 km crews pair with overlap
        land = next(m for m in matches if m["distance_tier"] == se.TIER_LAND)
        crews = next(m for m in matches if m["distance_tier"] == se.TIER_CREWS)
        self.assertGreater(land["priority_score"], crews["priority_score"])
        self.assertEqual(matches[0]["distance_tier"], se.TIER_LAND)

    def test_ranking_is_deterministic(self):
        projects = [
            point_project("d1", "DESC"),
            point_project("d2", "DESC", north_km=3.0),
            point_project("g1", "GPC", east_km=2.0),
            point_project("g2", "GPC", north_km=3.0, east_km=12.0),
        ]
        first = se.analyze_projects(projects)[1]
        second = se.analyze_projects(list(reversed(projects)))[1]
        self.assertEqual(
            [(m["project_a_id"], m["project_b_id"], m["priority_score"], m["distance_km"]) for m in first],
            [(m["project_a_id"], m["project_b_id"], m["priority_score"], m["distance_km"]) for m in second],
        )
        self.assertEqual([m["match_id"] for m in first], [m["match_id"] for m in second])


class DemoDatasetTests(unittest.TestCase):
    def test_repo_demo_data_still_produces_ranked_matches(self):
        payload = json.loads((ROOT / "data" / "projects.json").read_text())
        self.assertEqual(payload["dataset"], "demo")
        _normalized, matches, summary = se.analyze_projects(payload["projects"], dataset="demo")
        self.assertGreaterEqual(summary["total_projects"], 2)
        self.assertGreaterEqual(len(matches), 1)
        self.assertTrue(all(m["project_a"]["data_confidence"] == "LOW" for m in matches))
        self.assertIn("est_savings_usd", matches[0])

    def test_repo_verified_file_is_real_desc_gpc_data(self):
        payload = json.loads((ROOT / "data" / "verified_projects.json").read_text())
        projects = payload["projects"] if isinstance(payload, dict) else payload
        self.assertIsInstance(projects, list)
        self.assertEqual(len(projects), 78)
        self.assertEqual(sum(1 for p in projects if p.get("utility") == "DESC"), 54)
        self.assertEqual(sum(1 for p in projects if p.get("utility") == "GPC"), 24)
        self.assertTrue(all(p.get("utility") in ("DESC", "GPC") for p in projects))
        demo_ids = {p["id"] for p in json.loads((ROOT / "data" / "projects.json").read_text())["projects"]}
        self.assertFalse(any(p.get("id") in demo_ids for p in projects))
        sertp = [p for p in projects if str(p.get("id", "")).startswith("gpc-sertp-2025-")]
        self.assertEqual(len(sertp), 14)
        mapped_sertp = [p for p in sertp if se.extract_latlng_points(p)]
        self.assertEqual(len(mapped_sertp), 4)
        usable = [p for p in projects if se.extract_latlng_points(p)]
        self.assertEqual(len(usable), 15)
        self.assertEqual(sum(1 for p in usable if p["utility"] == "DESC"), 4)
        self.assertEqual(sum(1 for p in usable if p["utility"] == "GPC"), 11)
        normalized, matches, summary = se.analyze_projects(projects, dataset="verified")
        self.assertEqual(summary["total_projects"], 78)
        self.assertEqual(summary["pairs_checked"], 44)
        self.assertEqual(summary["pairs_within_40km"], 6)
        self.assertEqual(summary["pairs_with_timeline_overlap"], 0)
        self.assertEqual(len(matches), 6)
        self.assertTrue(all(m["distance_tier"] == se.TIER_CREWS for m in matches))
        self.assertTrue(all(8.0 <= m["distance_km"] < 40.0 for m in matches))
        self.assertFalse(any(m["timeline_overlap"] for m in matches))
        self.assertIn("Dean Forest", matches[0]["project_b"]["name"])
        self.assertIn("Jasper - Okatie", matches[0]["project_a"]["name"])
        traced = next(p for p in normalized if p["geometry_method"])
        self.assertIn(traced["geometry_confidence"], se.CONFIDENCE_VALUES)
        self.assertTrue(traced["geometry_source"])


if __name__ == "__main__":
    unittest.main()
