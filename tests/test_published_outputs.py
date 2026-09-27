import unittest
from pathlib import Path

from master_dataset import load_master
from scripts.publish_downstream import MAX_TIMELINE_GAP_YEARS, build_website_data
import scoring_engine as scoring

ROOT = Path(__file__).resolve().parents[1]


class PublishedOutputsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        master = load_master(ROOT / "data/published/gridlock_master_projects.json")
        cls.website = build_website_data(master)

    def test_full_coverage_uses_best_matches_schedule_policy(self):
        mode = self.website["modes"]["full"]
        self.assertEqual(mode["summary"]["candidate_pairs_within_40km"], 38)
        self.assertEqual(mode["summary"]["schedule_aligned_opportunities"], 24)
        self.assertEqual(len(mode["matches"]), 24)
        self.assertTrue(
            all(
                match["timeline_gap_years"] is not None
                and match["timeline_gap_years"] <= MAX_TIMELINE_GAP_YEARS
                for match in mode["matches"]
            )
        )

    def test_large_timeline_gaps_are_not_published_as_opportunities(self):
        names = {
            (match["project_a_id"], match["project_b_id"])
            for match in self.website["modes"]["full"]["matches"]
        }
        self.assertNotIn(
            (
                "scrtp-desc-2026-3fcc16fb58dedf958023",
                "gpc-sertp-2025-meldrim-bank-d-replacement",
            ),
            names,
        )

    def test_policy_is_machine_readable(self):
        self.assertEqual(
            self.website["opportunity_policy"],
            {
                "distance_km_lt": 40,
                "timeline_gap_years_lte": 2,
                "unknown_timing_eligible": False,
            },
        )

    def test_scoring_loader_uses_the_canonical_master(self):
        path = ROOT / "data/published/gridlock_master_projects.json"
        verified = scoring.load_projects(path, mode="verified")["projects"]
        full = scoring.load_projects(path, mode="full")["projects"]
        self.assertEqual(len(verified), 15)
        self.assertEqual(len(full), 59)
        self.assertTrue(all(project["geometry_status"] == "VERIFIED" for project in verified))
        self.assertTrue(
            all(project["geometry_status"] in {"VERIFIED", "ESTIMATED"} for project in full)
        )


if __name__ == "__main__":
    unittest.main()
