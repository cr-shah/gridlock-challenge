"""Estimated Coverage eligibility. Verified distance math is not under test here."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import estimated_coverage as ec
import scoring_engine as se


def _facility(name, lat, lng):
    return {
        "name": name,
        "norm": ec.norm_name(name),
        "lat": lat,
        "lng": lng,
        "operator": "Georgia Power",
        "osm": "way/1",
    }


def _project(name, utility="GPC", **extra):
    record = {
        "id": extra.pop("id", name),
        "utility": utility,
        "name": name,
        "project_type": extra.pop("project_type", "line_rebuild"),
        "endpoint_candidates": extra.pop("endpoint_candidates", []),
        "county_region": extra.pop("county_region", None),
        "voltage_kv": extra.pop("voltage_kv", [115.0]),
        "in_service_year": extra.pop("in_service_year", 2028),
        "geometry_method": extra.pop("geometry_method", None),
        "geometry_confidence": extra.pop("geometry_confidence", None),
        "estimated_geometry": extra.pop("estimated_geometry", False),
    }
    record.update(extra)
    return record


class NameAndPlanTests(unittest.TestCase):
    def test_saint_abbreviation_does_not_eat_forest_or_west(self):
        self.assertEqual(ec.norm_name("Dean Forest Substation"), "DEAN FOREST")
        self.assertEqual(ec.norm_name("West McIntosh"), "WEST MCINTOSH")
        self.assertEqual(ec.norm_name("St. George"), "SAINT GEORGE")
        self.assertEqual(ec.norm_name("St George"), "SAINT GEORGE")

    def test_subject_facility_is_not_placed_on_a_different_candidate(self):
        rice = _project(
            "Rice Hope Autotransformer",
            project_type="substation_upgrade",
            endpoint_candidates=["Rice Hope", "Crossgate", "McIntosh"],
        )
        plan = ec.plan_estimate(rice, [("McIntosh", _facility("McIntosh Substation", 32.35, -81.17))])
        self.assertEqual(plan["action"], "regional")

        big = _project(
            "Big Ogeechee New Substation",
            project_type="area_project",
            endpoint_candidates=["Big Ogeechee", "Little Ogeechee"],
        )
        plan = ec.plan_estimate(big, [("Little Ogeechee", _facility("Little Ogeechee Substation", 32.01, -81.25))])
        self.assertEqual(plan["action"], "regional")

    def test_two_named_endpoints_become_a_line(self):
        project = _project(
            "Goshen (Savannah)–McIntosh Rebuild",
            endpoint_candidates=["Goshen (Savannah)", "Georgia Pacific (Rincon)"],
        )
        resolved = [
            ("Goshen (Savannah)", _facility("Goshen Substation", 32.25, -81.21)),
            ("McIntosh", _facility("McIntosh Substation", 32.35, -81.18)),
        ]
        plan = ec.plan_estimate(project, resolved)
        self.assertEqual(plan["action"], "lines")
        labels = [hit[0] for hit in plan["circuits"][0]]
        self.assertEqual(labels, ["Goshen (Savannah)", "McIntosh"])

    def test_ambiguous_title_endpoint_does_not_use_a_different_candidate_line(self):
        project = _project(
            "Coleman–Meldrim Rebuild",
            endpoint_candidates=["Four Lakes", "Structure 76A", "Quacco Road"],
        )
        resolved = [
            ("Meldrim", _facility("Meldrim Substation", 32.155, -81.368)),
            ("Four Lakes", _facility("Four Lakes Substation", 32.100, -81.373)),
            ("Quacco Road", _facility("Quacco Road Substation", 32.078, -81.271)),
        ]
        plan = ec.plan_estimate(project, resolved)
        self.assertEqual(plan["action"], "point")
        self.assertEqual(plan["hit"][0], "Meldrim")

    def test_far_same_name_facility_is_not_connected(self):
        project = _project("VCS1-Denny Terrace 230kV & VCS1-Pineland 230kV: Rebuild")
        resolved = [
            ("VCS1", _facility("VCS1", 34.30, -81.31)),
            ("Denny Terrace", _facility("Denny Terrace", 34.06, -81.06)),
            ("Pineland", _facility("Pineland", 32.61, -81.15)),
        ]
        plan = ec.plan_estimate(project, resolved)
        self.assertEqual(plan["action"], "lines")
        self.assertEqual(len(plan["circuits"]), 1)
        labels = [hit[0] for hit in plan["circuits"][0]]
        self.assertEqual(labels, ["VCS1", "Denny Terrace"])
        self.assertTrue(any("Pineland" in note for note in plan["notes"]))

    def test_rice_hope_segment_is_not_the_whole_parent_line(self):
        project = _project(
            "Goshen (Savannah)–Kraft Rebuild, Rice Hope Segment",
            endpoint_candidates=["Goshen (Savannah)", "Rice Hope"],
        )
        resolved = [
            ("Goshen (Savannah)", _facility("Goshen Substation", 32.25, -81.21)),
            ("Kraft", _facility("Kraft Substation", 32.15, -81.15)),
        ]
        plan = ec.plan_estimate(project, resolved)
        self.assertEqual(plan["action"], "point")
        self.assertEqual(plan["hit"][0], "Goshen (Savannah)")


class EligibilityTests(unittest.TestCase):
    def test_regional_anchor_cannot_create_a_close_tier(self):
        regional = _project("Effingham County 500 kV", geometry_method="regional_screening_anchor", geometry_confidence="LOW", estimated_geometry=True)
        official = _project("Jasper - Okatie", utility="DESC", geometry_method="official_georeferenced_route_map_trace", geometry_confidence="HIGH", estimated_geometry=False)
        for distance, intersects in ((0.0, True), (1.0, False), (4.0, False)):
            tier, _label, blocked = ec.eligible_tier(distance, intersects, regional, official)
            self.assertEqual(tier, se.TIER_CREWS)
            self.assertTrue(blocked)

    def test_estimated_facility_point_cannot_create_a_close_tier(self):
        point = _project("Goshen segment", geometry_method="estimated_facility_point", geometry_confidence="ESTIMATED", estimated_geometry=True)
        line = _project("Okatie - McIntosh", utility="DESC", geometry_method="approximate_verified_endpoints", geometry_confidence="ESTIMATED", estimated_geometry=True)
        tier, _label, blocked = ec.eligible_tier(0.0, True, point, line)
        self.assertEqual(tier, se.TIER_CREWS)
        self.assertTrue(blocked)

    def test_two_verified_endpoints_can_be_under_8_km(self):
        left = _project("Okatie - McIntosh", utility="DESC", geometry_method="approximate_verified_endpoints", geometry_confidence="ESTIMATED", estimated_geometry=True)
        right = _project("Goshen–McIntosh", geometry_method="approximate_verified_endpoints", geometry_confidence="ESTIMATED", estimated_geometry=True)
        tier, _label, blocked = ec.eligible_tier(0.0, True, left, right)
        self.assertEqual(tier, se.TIER_MUST)
        self.assertFalse(blocked)
        tier, _label, blocked = ec.eligible_tier(4.8, False, left, right)
        self.assertEqual(tier, se.TIER_LOGISTICS)
        self.assertFalse(blocked)

    def test_hifld_corridor_and_official_point_can_be_close(self):
        corridor = _project("VCS rebuild", utility="DESC", geometry_method="existing_corridor_hifld", geometry_confidence="MEDIUM", estimated_geometry=True)
        point = _project("Facility", geometry_method="official_project_map_facility_point", geometry_confidence="HIGH", estimated_geometry=False)
        tier, _label, blocked = ec.eligible_tier(1.2, False, corridor, point)
        self.assertEqual(tier, se.TIER_LAND)
        self.assertFalse(blocked)

    def test_low_confidence_cannot_be_reclassified_upward(self):
        low = _project("Anchor", geometry_method="approximate_verified_endpoints", geometry_confidence="LOW", estimated_geometry=True)
        other = _project("Line", utility="DESC", geometry_method="approximate_verified_endpoints", geometry_confidence="ESTIMATED", estimated_geometry=True)
        tier, _label, blocked = ec.eligible_tier(1.0, False, low, other)
        self.assertEqual(tier, se.TIER_CREWS)
        self.assertTrue(blocked)

    def test_coordination_score_does_not_change_the_distance_tier(self):
        close_desc = {
            "id": "d-close",
            "utility": "DESC",
            "name": "Close desc line",
            "geometry": [[-81.20, 32.30], [-81.10, 32.30]],
            "geometry_type": "LineString",
            "geometry_method": "approximate_verified_endpoints",
            "geometry_confidence": "ESTIMATED",
            "estimated_geometry": True,
            "in_service_year": 2020,
        }
        close_gpc = {
            "id": "g-close",
            "utility": "GPC",
            "name": "Close gpc line",
            "geometry": [[-81.20, 32.33], [-81.10, 32.33]],
            "geometry_type": "LineString",
            "geometry_method": "approximate_verified_endpoints",
            "geometry_confidence": "ESTIMATED",
            "estimated_geometry": True,
            "in_service_year": 2030,
        }
        far_desc = {
            "id": "d-far",
            "utility": "DESC",
            "name": "Far desc line",
            "geometry": [[-83.20, 34.20], [-83.10, 34.20]],
            "geometry_type": "LineString",
            "geometry_method": "approximate_verified_endpoints",
            "geometry_confidence": "ESTIMATED",
            "estimated_geometry": True,
            "in_service_year": 2028,
        }
        far_gpc = {
            "id": "g-far",
            "utility": "GPC",
            "name": "Far gpc line",
            "geometry": [[-83.20, 34.335], [-83.10, 34.335]],
            "geometry_type": "LineString",
            "geometry_method": "approximate_verified_endpoints",
            "geometry_confidence": "ESTIMATED",
            "estimated_geometry": True,
            "in_service_year": 2028,
        }
        matches = ec.score_estimated([close_desc, close_gpc, far_desc, far_gpc])
        self.assertGreaterEqual(len(matches), 2)
        self.assertEqual(matches[0]["project_a_id"], "d-close")
        self.assertEqual(matches[0]["distance_tier"], se.TIER_LOGISTICS)
        self.assertLess(matches[0]["coordination_score"], matches[1]["coordination_score"])
        self.assertEqual(matches[1]["distance_tier"], se.TIER_CREWS)
        self.assertGreater(matches[1]["distance_km"], 8)
        self.assertTrue(matches[0]["distance_km"] < matches[1]["distance_km"])

    def test_same_year_and_penalty_are_within_tier_only(self):
        same = _project("Okatie line", utility="DESC", geometry_confidence="ESTIMATED", in_service_year=2028, county_region="Savannah")
        other = _project("McIntosh line", geometry_confidence="ESTIMATED", in_service_year=2028, county_region="Savannah")
        score, explanation = ec.coordination_score(same, other)
        self.assertIn("+20 shared construction year", explanation)
        self.assertIn("+5 Savannah River planning-area context", explanation)
        self.assertIn("-10 weaker geometry confidence", explanation)
        self.assertGreaterEqual(score, 15)
        gap = _project("Later", utility="DESC", geometry_confidence="HIGH", in_service_year=2029)
        earlier = _project("Earlier", geometry_confidence="HIGH", in_service_year=2028)
        score, explanation = ec.coordination_score(gap, earlier)
        self.assertIn("+10 one-year timing gap", explanation)
        self.assertNotIn("shared construction year", explanation)


class OfficialGeometryTests(unittest.TestCase):
    def test_apply_estimates_never_replaces_official_geometry(self):
        official = _project(
            "Official route",
            utility="DESC",
            id="official-1",
            geometry=[[-81.1, 32.3], [-81.0, 32.4]],
            geometry_type="LineString",
            geometry_method="official_georeferenced_route_map_trace",
            geometry_confidence="HIGH",
        )
        estimate = {
            "project_id": "official-1",
            "geometry": [-81.2, 32.2],
            "geometry_type": "Point",
            "geometry_method": "estimated_facility_point",
            "geometry_confidence": "ESTIMATED",
            "geometry_source": "https://www.openstreetmap.org",
            "geometry_notes": "should not apply",
            "endpoint_names": ["Somewhere"],
        }
        prepared = ec.apply_estimates([official], [estimate])
        self.assertEqual(prepared[0]["geometry"], official["geometry"])
        self.assertFalse(prepared[0]["estimated_geometry"])
        self.assertEqual(prepared[0]["geometry_method"], "official_georeferenced_route_map_trace")

    def test_empty_estimate_is_not_applied(self):
        bare = _project("Unmapped", utility="DESC", id="bare-1", geometry=None, geometry_type=None)
        estimate = {
            "project_id": "bare-1",
            "geometry": [],
            "geometry_type": "LineString",
            "geometry_method": "existing_corridor_hifld",
            "geometry_confidence": "MEDIUM",
            "geometry_source": "hifld",
            "geometry_notes": "empty",
            "endpoint_names": [],
        }
        prepared = ec.apply_estimates([bare], [estimate])
        self.assertIsNone(prepared[0]["geometry"])
        self.assertFalse(prepared[0]["estimated_geometry"])

    def test_repo_estimates_do_not_overwrite_verified_records(self):
        projects = ec.load_projects(ec.VERIFIED_PATH)
        payload = json.loads(ec.ESTIMATE_PATH.read_text())
        official_ids = {project["id"] for project in projects if se.extract_latlng_points(project)}
        self.assertEqual(len(official_ids), 15)
        estimate_ids = {item["project_id"] for item in payload["estimates"]}
        self.assertFalse(official_ids & estimate_ids)
        prepared = ec.apply_estimates(projects, payload["estimates"])
        by_id = {project["id"]: project for project in projects}
        for project in prepared:
            if project["id"] in official_ids:
                self.assertEqual(project["geometry"], by_id[project["id"]]["geometry"])
                self.assertFalse(project["estimated_geometry"])
        rice = next(item for item in payload["estimates"] if item["project_id"] == "gpc-sertp-2025-rice-hope-autotransformer")
        self.assertEqual(rice["geometry_method"], "regional_screening_anchor")
        self.assertEqual(rice["geometry_confidence"], "LOW")
        big = next(item for item in payload["estimates"] if item["project_id"] == "gpc-sertp-2025-big-ogeechee-new-substation")
        self.assertEqual(big["geometry_method"], "regional_screening_anchor")
        for item in payload["estimates"]:
            self.assertTrue(ec.parts_from_geometry(item["geometry"], item["geometry_type"]))

    def test_saved_estimated_screen_keeps_close_tiers_eligible(self):
        payload = json.loads((ROOT / "data" / "estimated_analysis.json").read_text())
        summary = payload["summary"]
        self.assertEqual(summary["projects_with_geometry"], 59)
        self.assertEqual(summary["unresolved_count"], 19)
        self.assertEqual(summary["pairs_under_8km"], 2)
        self.assertEqual(summary["pairs_under_1_6km"], 1)
        self.assertEqual(summary["pairs_touching"], 1)
        self.assertTrue(payload["data_disclaimer"].startswith("Estimated geometry — planning-screening use only"))
        close = [match for match in payload["matches"] if match["distance_tier"] in (se.TIER_MUST, se.TIER_LAND, se.TIER_LOGISTICS)]
        self.assertEqual(len(close), 2)
        for match in close:
            self.assertFalse(match["close_tier_blocked"])
            for side in (match["project_a"], match["project_b"]):
                self.assertNotEqual(side["geometry_method"], "regional_screening_anchor")
                self.assertNotEqual(side["geometry_method"], "estimated_facility_point")
                self.assertNotEqual(side["geometry_confidence"], "LOW")


if __name__ == "__main__":
    unittest.main()
