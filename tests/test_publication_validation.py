import copy
import json
import unittest
from pathlib import Path

from publication_validation import validate_publication

ROOT = Path(__file__).resolve().parents[1]


class PublicationValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.master = json.loads(
            (ROOT / "data/published/gridlock_master_projects.json").read_text()
        )
        cls.website = json.loads((ROOT / "data/published/website_data.json").read_text())

    def test_current_publication_is_logically_consistent(self):
        validate_publication(self.master, self.website)

    def test_rejects_stale_or_misaligned_dates(self):
        website = copy.deepcopy(self.website)
        website["modes"]["full"]["matches"][0]["timeline_gap_years"] = 7
        with self.assertRaisesRegex(ValueError, "stale timeline"):
            validate_publication(self.master, website)

    def test_rejects_stale_or_misaligned_places(self):
        master = copy.deepcopy(self.master)
        project = next(item for item in master["projects"] if item["analysis_geometry"])
        project["analysis_geometry"]["coordinates"] = [-20, 55]
        if project["verified_geometry"]:
            project["verified_geometry"] = project["analysis_geometry"]
        else:
            project["estimated_geometry"] = project["analysis_geometry"]
        with self.assertRaisesRegex(ValueError, "outside the SC/GA planning region"):
            validate_publication(master, self.website)

    def test_rejects_stale_distance(self):
        website = copy.deepcopy(self.website)
        website["modes"]["full"]["matches"][0]["distance_km"] = 39.99
        with self.assertRaisesRegex(ValueError, "stale or out-of-policy distance"):
            validate_publication(self.master, website)


if __name__ == "__main__":
    unittest.main()
