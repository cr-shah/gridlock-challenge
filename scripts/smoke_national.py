"""Exercise the running local server. Live checks are optional and never require keys."""

import argparse
import json
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen


def main(base, live=False):
    def read(path):
        with urlopen(base + path, timeout=25) as response:
            return json.loads(response.read())

    start = time.monotonic()
    g = read("/api/nation/geography")
    projects = read("/api/nation/projects?limit=5")
    assert len(projects["records"]) == 5 and projects["total"] > 7000
    assert len(projects["map"]["features"]) <= 800
    p = read("/api/nation/project?" + urlencode({"id": projects["records"][0]["id"]}))
    assert p["record"]["provenance"]["source_url"]
    assert read("/api/nation/pairs?limit=5")["total"] >= 1352
    assert read("/api/nation/areas?state=02")["areas"]
    history = read("/api/nation/history?lon=-82&lat=34")
    assert history["status"] == "available"
    assert len(history["observations"]["prcp_in"]) == 3653
    local = read("/api/nation/projects?state=45&zoom=8&limit=1")
    assert all("precision" in f["properties"] for f in local["map"]["features"])
    for path, code in [
        ("/api/nation/projects?limit=999999", 400),
        ("/api/nation/project?id=missing", 404),
        ("/.env", 404),
        ("/data/nation/catalog.json.gz", 404),
        ("/data/nation/weather.zip", 404),
        ("/api/nation/history?lon=nan&lat=34", 400),
        ("/nation/service.py", 404),
    ]:
        try:
            read(path)
        except HTTPError as exc:
            assert exc.code == code, (path, exc.code)
        else:
            raise AssertionError(path + " was not rejected")
    with urlopen(base + "/", timeout=5) as response:
        assert b"National intelligence" in response.read()
    print(
        json.dumps(
            {
                "http_checks": "passed",
                "counts": g["counts"],
                "seconds": round(time.monotonic() - start, 3),
            }
        )
    )
    if live:
        for path in [
            "alerts",
            "site?provider=nws-forecast&lon=-82&lat=34",
            "site?provider=ssurgo&lon=-82&lat=34",
            "site?provider=wetlands&lon=-82&lat=34",
        ]:
            data = read("/api/nation/" + path)
            print(
                json.dumps(
                    {
                        "provider": data.get("provider"),
                        "status": data["status"],
                        "records": len(data.get("records", data.get("periods", []))),
                        "retrieved_at": data.get("retrieved_at"),
                    }
                )
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8002")
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    main(args.base, args.live)
