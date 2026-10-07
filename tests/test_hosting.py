"""Public hosting boundary: real catalog, private files, and safe failures."""
import importlib.util
import io
import json
import unittest
from unittest.mock import patch
from wsgiref.util import setup_testing_defaults


class HostingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from deploy.wsgi import application
        cls.app = staticmethod(application)

    def request(self, path, method="GET"):
        env = {}
        setup_testing_defaults(env)
        env.update(PATH_INFO=path.split("?", 1)[0],
                   QUERY_STRING=path.partition("?")[2],
                   REQUEST_METHOD=method, **{"wsgi.input": io.BytesIO()})
        result = {}

        def start(status, headers):
            result.update(status=int(status.split()[0]), headers=dict(headers))

        result["body"] = b"".join(self.app(env, start))
        return result

    def test_hosting_entrypoint_exists(self):
        self.assertIsNotNone(importlib.util.find_spec("deploy.wsgi"))

    def test_frontend_and_regional_tools_remain_available(self):
        for path in ("/", "/index.html?view=radar", "/project-explorer.html",
                     "/time-lens.js", "/planning-model.js",
                     "/data/published/website_data.json"):
            with self.subTest(path=path):
                r = self.request(path)
                self.assertEqual(r["status"], 200)
                self.assertTrue(r["body"])
                self.assertEqual(r["headers"]["X-Content-Type-Options"], "nosniff")
        self.assertIn(b"nationwide.js", self.request("/")["body"])
        self.assertIn(b"radar.js", self.request("/?view=radar")["body"])

    def test_private_files_and_traversal_are_not_published(self):
        for path in ("/.env", "/.git/config", "/analyst/core.py",
                     "/data/nation/weather.zip", "/data/nation/catalog.json.gz",
                     "/data/published/../../.env", "/../README.md"):
            with self.subTest(path=path):
                self.assertEqual(self.request(path)["status"], 404)

    def test_catalog_and_historical_weather_are_real(self):
        r = self.request("/api/nation/geography")
        self.assertEqual(r["status"], 200)
        self.assertGreater(len(json.loads(r["body"])["states"]), 40)
        r = self.request("/api/nation/history?lon=-82&lat=34")
        data = json.loads(r["body"])
        self.assertEqual(r["status"], 200)
        self.assertEqual(data["status"], "available")
        self.assertEqual(len(data["observations"]["prcp_in"]), 3653)

    def test_bad_queries_missing_records_and_methods(self):
        self.assertEqual(self.request("/api/nation/projects?limit=50000")["status"], 400)
        self.assertEqual(self.request("/api/nation/project?id=not-a-record")["status"], 404)
        self.assertEqual(self.request("/api/nation/missing")["status"], 404)
        self.assertEqual(self.request("/", "DELETE")["status"], 405)

    def test_head_has_headers_but_no_body(self):
        r = self.request("/", "HEAD")
        self.assertEqual(r["status"], 200)
        self.assertEqual(r["body"], b"")
        self.assertGreater(int(r["headers"]["Content-Length"]), 0)

    def test_public_ai_is_disabled_even_when_key_is_present(self):
        with patch.dict("os.environ", {"GEMINI_API_KEY": "do-not-publish-me"}):
            r = self.request("/api/analyst/status")
            self.assertFalse(json.loads(r["body"])["ready"])
            self.assertNotIn(b"do-not-publish-me", r["body"])
            self.assertEqual(self.request("/api/analyst", "POST")["status"], 503)

    def test_health_checks_data_and_hides_failures(self):
        r = self.request("/healthz")
        self.assertEqual(r["status"], 200)
        self.assertEqual(json.loads(r["body"])["status"], "ok")
        with patch("deploy.wsgi.catalog", side_effect=OSError("secret-path")):
            r = self.request("/healthz")
            self.assertEqual(r["status"], 503)
            self.assertNotIn(b"secret-path", r["body"])

    def test_provider_failures_do_not_leak_credentials(self):
        with patch("deploy.wsgi.dispatch", side_effect=OSError("secret-key")):
            r = self.request("/api/nation/alerts")
            self.assertEqual(r["status"], 503)
            self.assertNotIn(b"secret-key", r["body"])

    def test_overload_returns_retry_instead_of_extra_work(self):
        from deploy.wsgi import NATION_GATE
        held = 0
        try:
            while NATION_GATE.acquire(blocking=False):
                held += 1
            r = self.request("/api/nation/geography")
            self.assertEqual(r["status"], 429)
            self.assertIn("Retry-After", r["headers"])
        finally:
            for _ in range(held):
                NATION_GATE.release()


if __name__ == "__main__":
    unittest.main()
