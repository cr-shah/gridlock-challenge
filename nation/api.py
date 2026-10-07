"""Read-only HTTP dispatch, shared by the local server and integration tests."""

from urllib.parse import parse_qs, urlsplit
from nation.models import GeoQuery
from nation.service import catalog
from nation import providers


def single(query, allowed):
    parsed = parse_qs(query, keep_blank_values=True)
    if set(parsed) - set(allowed) or any(len(v) != 1 for v in parsed.values()):
        raise ValueError("Invalid query parameters.")
    return {k: v[0] for k, v in parsed.items()}


def dispatch(url):
    route = urlsplit(url)
    path, query = route.path, route.query
    if path == "/api/nation/geography":
        single(query, [])
        return catalog().geography()
    if path == "/api/nation/projects":
        return catalog().query(GeoQuery.parse(query))
    if path == "/api/nation/areas":
        q = single(query, ["state"])
        c = catalog()
        if q.get("state") not in c.states:
            raise ValueError("Select a known state for local areas.")
        return {
            "areas": [v for v in c.counties if v["state_fips"] == q["state"]],
            "limitation": "County bounds frame a local viewport; they are not exact boundary membership.",
        }
    if path == "/api/nation/pairs":
        return catalog().candidates(GeoQuery.parse(query))
    if path in {"/api/nation/project", "/api/nation/exposure"}:
        args = single(query, ["id"])
        identifier = args.get("id", "")
        return (
            catalog().detail(identifier)
            if path.endswith("/project")
            else catalog().exposure(identifier)
        )
    if path == "/api/nation/alerts":
        single(query, [])
        result = providers.alerts()
        # At most 500 official alerts, bounded server-side; never all national raw projects.
        return result
    if path == "/api/nation/site":
        q = single(query, ["provider", "lon", "lat"])
        if not all(k in q for k in ("provider", "lon", "lat")):
            raise ValueError("provider, lon and lat required.")
        return providers.site_provider(q["provider"], float(q["lon"]), float(q["lat"]))
    if path == "/api/nation/history":
        from nation.history import at

        q = single(query, ["lon", "lat"])
        if not all(k in q for k in ("lon", "lat")):
            raise ValueError("lon and lat required.")
        return at(float(q["lon"]), float(q["lat"]))
    raise KeyError(path)
