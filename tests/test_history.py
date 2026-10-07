import hashlib
import math
import unittest
from unittest.mock import patch

from nation import history
from nation.api import dispatch
from analyst.server import allowed_asset


class HistoryTests(unittest.TestCase):
    def test_archive_receipt(self):
        self.assertEqual(
            hashlib.sha256((history.ROOT / "weather.zip").read_bytes()).hexdigest(),
            history.index()["archive_sha256"],
        )
        self.assertEqual(len(history.index()["stations"]), 1979)

    def test_distance_dateline(self):
        self.assertLess(history.miles(179.9, 0, -179.9, 0), 14)
        self.assertEqual(history.miles(0, 0, 0, 0), 0)

    def test_selected_station_and_day_alignment(self):
        r = dispatch("/api/nation/history?lon=-82&lat=34")
        self.assertEqual(r["status"], "available")
        self.assertLessEqual(r["rain"]["distance_mi"], 30)
        self.assertLessEqual(r["wind"]["distance_mi"], 60)
        self.assertTrue(
            r["rain"]["source_url"].startswith("https://www.ncei.noaa.gov/")
        )
        for values in r["observations"].values():
            self.assertEqual(len(values), 3653)
            self.assertTrue(all(v is None or math.isfinite(v) for v in values))

    def test_no_far_station_fallback(self):
        r = history.at(0, 0)
        self.assertEqual(r["status"], "unavailable")
        self.assertNotIn("observations", r)

    def test_api_coordinates_and_private_archive(self):
        for query in [
            "lon=nan&lat=34",
            "lon=0&lat=91",
            "lat=34",
            "lon=0&lat=0&url=x",
            "lon=0&lon=1&lat=0",
        ]:
            with self.assertRaises(ValueError):
                dispatch("/api/nation/history?" + query)
        self.assertFalse(allowed_asset("data/nation/weather.zip"))
        self.assertFalse(allowed_asset("data/nation/weather-index.json"))

    def test_station_hash_corruption_fails_closed(self):
        history.series.cache_clear()
        with patch("nation.history.hashlib.sha256") as hash_mock:
            hash_mock.return_value.hexdigest.return_value = "corrupt"
            with self.assertRaises(ValueError):
                history.series(next(iter(history.index()["stations"])))
        history.series.cache_clear()


if __name__ == "__main__":
    unittest.main()
