from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from analyst.server import allowed_asset
from nation.api import dispatch
from nation.models import GeoQuery, coordinate, milestone, safe_url
from nation.providers import normalize_alerts, site_provider, valid_geometry
from nation.service import Catalog, catalog
from nation.transport import Cache, fetch_json

NOW = datetime(2026, 10, 7, tzinfo=timezone.utc)
POLYGON = {
    "type": "Polygon",
    "coordinates": [[[-90, 25], [-70, 25], [-70, 40], [-90, 40], [-90, 25]]],
}


def alert(identifier="one", geometry=POLYGON):
    return {
        "id": identifier,
        "geometry": geometry,
        "properties": {
            "id": identifier,
            "event": "Wind advisory",
            "status": "Actual",
            "severity": "Moderate",
            "sent": "2026-10-06T00:00:00Z",
            "expires": "2026-10-08T00:00:00Z",
        },
    }


class ContractsTests(unittest.TestCase):
    def test_coordinates_reject_bool_nan_and_out_of_range(self):
        for lon, lat in [
            (True, 20),
            (float("nan"), 20),
            (181, 20),
            (-80, 91),
            ("20", 30),
        ]:
            with self.subTest(lon=lon, lat=lat), self.assertRaises(ValueError):
                coordinate(lon, lat)

    def test_date_precision_is_not_invented(self):
        self.assertEqual(
            milestone("2028", "year"), {"value": "2028", "precision": "year"}
        )
        self.assertEqual(milestone(None, "day")["precision"], "unknown")
        for value, precision in [
            ("2026-02-30", "day"),
            ("2026-14", "month"),
            ("2026", "day"),
            ("3033", "year"),
        ]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                milestone(value, precision)

    def test_query_validation_and_antimeridian(self):
        self.assertEqual(
            GeoQuery.parse("bbox=170,50,-130,72&state=02").bbox, (170, 50, -130, 72)
        )
        for query in [
            "bbox=nan,0,1,2",
            "bbox=0,5,2,1",
            "limit=50000",
            "zoom=-1",
            "state=GA",
            "text=" + ("a" * 121),
            "state=13&state=45",
            "status=fiction",
            "secret=x",
        ]:
            with self.subTest(query=query), self.assertRaises(ValueError):
                GeoQuery.parse(query)

    def test_url_validation(self):
        for url in [
            "javascript:alert(1)",
            "https://user:secret@example.com",
            None,
            "//example.com",
        ]:
            self.assertIsNone(safe_url(url))
        self.assertEqual(safe_url("https://weather.gov"), "https://weather.gov")

    def test_transport_rejects_ssrf_before_network(self):
        for url in [
            "http://api.weather.gov",
            "https://localhost",
            "https://api.weather.gov.evil.com",
            "https://api.weather.gov:444",
            "https://key@api.weather.gov",
        ]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                fetch_json(url)


class AlertTests(unittest.TestCase):
    def test_missing_polygon_is_retained_not_fabricated(self):
        data = normalize_alerts(
            {"type": "FeatureCollection", "features": [alert(geometry=None)]}, NOW
        )
        self.assertIsNone(data["records"][0]["geometry"])
        self.assertEqual(data["status"], "available")

    def test_expired_test_alerts_and_duplicates_excluded(self):
        expired = alert("expired")
        expired["properties"]["expires"] = "2026-10-05T00:00:00Z"
        test = alert("test")
        test["properties"]["status"] = "Test"
        data = normalize_alerts(
            {
                "type": "FeatureCollection",
                "features": [alert(), alert(), expired, test],
            },
            NOW,
        )
        self.assertEqual(len(data["records"]), 1)

    def test_partial_and_invalid_geometry(self):
        invalid = alert("bad")
        invalid["properties"]["sent"] = "tomorrow"
        data = normalize_alerts(
            {
                "type": "FeatureCollection",
                "features": [alert(), invalid],
                "pagination": {"next": "more"},
            },
            NOW,
        )
        self.assertEqual(data["status"], "partial")
        self.assertTrue(data["truncated"])
        self.assertIsNone(valid_geometry({"type": "Point", "coordinates": [0, 0]}))

    def test_cap_and_offline_are_explicit(self):
        data = normalize_alerts(
            {
                "type": "FeatureCollection",
                "features": [alert(str(i)) for i in range(501)],
            },
            NOW,
        )
        self.assertEqual(len(data["records"]), 500)
        self.assertEqual(data["status"], "partial")
        with (
            patch.dict("os.environ", {"GRIDLOCK_OFFLINE": "1"}),
            patch("nation.providers.fetch_json") as fetch,
        ):
            self.assertEqual(
                site_provider("nws-forecast", -82, 34)["status"], "unavailable"
            )
            fetch.assert_not_called()


class CacheTests(unittest.TestCase):
    def test_ttl_stale_original_timestamp_and_hard_expiry(self):
        now = [0]
        cache = Cache(clock=lambda: now[0])
        data = {"status": "available", "retrieved_at": "original", "records": [1]}
        self.assertEqual(cache.get("x", lambda: data, ttl=10), data)
        now[0] = 11

        def fail():
            raise OSError("secret upstream text")

        value = cache.get("x", fail, ttl=10, stale_ttl=100)
        self.assertEqual(value["status"], "stale")
        self.assertEqual(value["retrieved_at"], "original")
        now[0] = 150
        self.assertEqual(cache.get("x", fail, stale_ttl=100)["status"], "unavailable")

    def test_coalescing_and_copy_isolation(self):
        cache = Cache()
        calls = []
        started = threading.Event()
        release = threading.Event()

        def loader():
            calls.append(1)
            started.set()
            release.wait(2)
            return {"status": "available", "records": [1]}

        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(cache.get, "x", loader)
            started.wait(2)
            second = pool.submit(cache.get, "x", loader)
            release.set()
            a, b = first.result(), second.result()
        a["records"].append(2)
        self.assertEqual(b["records"], [1])
        self.assertEqual(len(calls), 1)

    def test_failure_cooldown_and_bounded_entries(self):
        cache = Cache(max_entries=2)
        calls = []

        def fail():
            calls.append(1)
            raise OSError()

        cache.get("x", fail)
        cache.get("x", fail)
        self.assertEqual(len(calls), 1)
        for key in ["a", "b", "c"]:
            cache.get(key, lambda: {"status": "available"})
        self.assertEqual(len(cache.entries), 2)


class CatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = catalog()

    def test_source_catalog_and_canonical_preservation(self):
        c = self.catalog
        self.assertEqual(
            sum(p["provenance"]["provider"] == "canonical" for p in c.records), 78
        )
        self.assertEqual(len(c.opportunities), 24)
        self.assertGreater(len(c.records), 12000)
        self.assertEqual(len(c.records), len(c.by_id))
        self.assertFalse(any(p["id"].startswith("national:legacy:") for p in c.records))

    def test_response_is_bounded_and_does_not_include_raw_evidence(self):
        data = self.catalog.query(GeoQuery())
        self.assertLessEqual(len(data["records"]), 60)
        self.assertLessEqual(len(data["map"]["features"]), 800)
        self.assertTrue(all("detail" not in p for p in data["records"]))
        self.assertLess(len(json.dumps(data)), 200000)
        self.assertEqual(
            sum(f["properties"]["count"] for f in data["map"]["features"]),
            data["mapped"],
        )

    def test_state_status_and_missing_geometry(self):
        q = GeoQuery(state="48", status="all", confidence="unresolved")
        records = self.catalog.select(q)
        self.assertTrue(records)
        self.assertTrue(
            all("48" in p["states"] and p["geometry"] is None for p in records)
        )
        data = self.catalog.query(q)
        self.assertEqual(data["mapped"], 0)
        self.assertEqual(data["map"]["features"], [])

    def test_spatial_index_matches_direct_geometry_including_antimeridian(self):
        from nation.service import boxes

        for bounds in [(-84, 30, -80, 35), (170, 50, -130, 73), (-161, 18, -154, 23)]:
            q = GeoQuery(bbox=bounds, status="all")
            actual = {p["id"] for p in self.catalog.select(q)}
            expected = {
                p["id"]
                for p, g in zip(self.catalog.mapped, self.catalog.shapes)
                if any(g.intersects(b) for b in boxes(bounds))
            }
            self.assertEqual(actual, expected)

    def test_saved_candidates_have_references_and_exact_day_gap_only(self):
        for pair in self.catalog.pairs:
            a, b = (self.catalog.by_id[pair[k]] for k in ("a", "b"))
            self.assertEqual(pair["classification"], "provisional")
            self.assertLess(pair["distance_km"], 40.235)
            if pair["time_gap_days"] is not None:
                self.assertEqual(a["milestone"]["precision"], "day")
                self.assertEqual(b["milestone"]["precision"], "day")

    def test_implausible_dates_keep_evidence_not_timeline(self):
        affected = [
            r for r in self.catalog.records if r.get("detail", {}).get("date_issue")
        ]
        self.assertTrue(affected)
        self.assertTrue(all(p["milestone"]["value"] is None for p in affected))
        self.assertTrue(all(p["detail"]["source_milestone"]["value"] for p in affected))

    def test_detail_and_pagination(self):
        a = self.catalog.query(GeoQuery(limit=10))
        b = self.catalog.query(GeoQuery(limit=10, offset=10))
        self.assertFalse(
            {r["id"] for r in a["records"]} & {r["id"] for r in b["records"]}
        )
        self.assertIn("detail", self.catalog.detail(a["records"][0]["id"])["record"])
        with self.assertRaises(ValueError):
            self.catalog.select(GeoQuery(state="00"))

    def test_dataset_identity_includes_canonical_content(self):
        from copy import deepcopy
        from nation.service import ROOT, load_publication

        master, modes = load_publication(ROOT)
        modified = deepcopy(master)
        modified["projects"][0]["project_name"] += " revised"
        with patch("nation.service.load_publication", return_value=(modified, modes)):
            changed = Catalog()
        self.assertNotEqual(
            self.catalog.query(GeoQuery())["dataset"],
            changed.query(GeoQuery())["dataset"],
        )

    def test_exposure_is_intersection_not_prediction(self):
        c = self.catalog
        identifier = next(
            p["id"]
            for p in c.records
            if p["provenance"]["provider"] == "canonical" and p["geometry"]
        )
        result = normalize_alerts(
            {"type": "FeatureCollection", "features": [alert(), alert("zone", None)]},
            NOW,
        )
        with patch("nation.providers.alerts", return_value=result):
            out = c.exposure(identifier)
        self.assertEqual(len(out["records"]), 1)
        self.assertEqual(out["unlocated_alerts"], 1)
        self.assertIn("not a predicted outage", " ".join(out["limitations"]))

    def test_hash_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data/nation").mkdir(parents=True)
            (root / "data/nation/catalog.json.gz").write_bytes(b"bad")
            (root / "data/nation/receipt.json").write_text('{"sha256":"wrong"}')
            with self.assertRaisesRegex(ValueError, "integrity"):
                Catalog(root)

    def test_dispatch_rejects_unknown_params_and_private_assets(self):
        with self.assertRaises(ValueError):
            dispatch("/api/nation/project?id=a&id=b")
        with self.assertRaises(KeyError):
            dispatch("/api/nation/nope")
        self.assertFalse(allowed_asset("data/nation/catalog.json.gz"))
        self.assertFalse(allowed_asset(".env"))
        self.assertTrue(allowed_asset("nationwide.html"))

    def test_county_navigation_is_geographic_reference_only(self):
        out = dispatch("/api/nation/areas?state=45")
        self.assertTrue(out["areas"])
        self.assertTrue(all(a["state_fips"] == "45" for a in out["areas"]))
        self.assertIn("not exact boundary", out["limitation"])
        with self.assertRaises(ValueError):
            dispatch("/api/nation/areas?state=00")


if __name__ == "__main__":
    unittest.main()
