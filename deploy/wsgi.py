"""Same-origin public frontend/API. No dotenv loading or paid AI calls."""
from functools import lru_cache
import hashlib
from http import HTTPStatus
import json
import mimetypes
from pathlib import Path
from threading import BoundedSemaphore
from urllib.parse import parse_qs

from nation.api import dispatch
from nation.history import index as weather_index
from nation.service import catalog

ROOT = Path(__file__).resolve().parents[1]
# Reserve thread capacity for assets and health checks while providers are slow.
NATION_GATE = BoundedSemaphore(6)
AI_MESSAGE = "AI Analyst is disabled on the public demo to prevent unauthenticated paid API usage."


@lru_cache(maxsize=1)
def validate_weather():
    raw = (ROOT / "data/nation/weather.zip").read_bytes()
    if hashlib.sha256(raw).hexdigest() != weather_index()["archive_sha256"]:
        raise ValueError("Weather archive integrity mismatch.")
    return True


def asset(name):
    path = ROOT / name
    allowed = (
        path.parent == ROOT and path.suffix in {".html", ".css", ".js"}
    ) or (path.parent == ROOT / "data/published" and path.suffix == ".json")
    if allowed and path.is_file() and path.resolve().is_relative_to(ROOT.resolve()):
        return path
    return None


def route(env):
    method, path = env["REQUEST_METHOD"], env.get("PATH_INFO", "/")
    if method == "POST" and path == "/api/analyst":
        return 503, {"error": AI_MESSAGE}, None
    if method not in {"GET", "HEAD"}:
        return 405, {"error": "Method not allowed."}, None
    if path == "/api/analyst/status":
        return 200, {"ready": False, "missing": [], "reason": AI_MESSAGE}, None
    if path == "/healthz":
        try:
            c = catalog()
            validate_weather()
            return 200, {"status": "ok", "dataset": c.dataset}, None
        except Exception:
            return 503, {"status": "unavailable"}, None
    if path.startswith("/api/nation/"):
        if not NATION_GATE.acquire(blocking=False):
            return 429, {"error": "Explorer is busy. Retry shortly."}, None
        try:
            query = env.get("QUERY_STRING", "")
            return 200, dispatch(path + ("?" + query if query else "")), None
        except KeyError:
            return 404, {"error": "Record or endpoint not found."}, None
        except (ValueError, TypeError):
            return 400, {"error": "Invalid query or unavailable record data."}, None
        except Exception:
            return 503, {"error": "National data temporarily unavailable."}, None
        finally:
            NATION_GATE.release()
    name = path.lstrip("/") or (
        "index.html" if "radar" in parse_qs(env.get("QUERY_STRING", "")).get("view", [])
        else "nationwide.html"
    )
    file = asset(name)
    if not file:
        return 404, {"error": "Not found."}, None
    return 200, file.read_bytes(), mimetypes.guess_type(name)[0]


def application(environ, start_response):
    try:
        status, value, content_type = route(environ)
    except Exception:
        status, value, content_type = 503, {"error": "Service temporarily unavailable."}, None
    body = value if isinstance(value, bytes) else json.dumps(value).encode()
    headers = [
        ("Content-Type", content_type or "application/json"),
        ("Content-Length", str(len(body))),
        ("Cache-Control", "no-store"),
        ("X-Content-Type-Options", "nosniff"),
        ("X-Frame-Options", "SAMEORIGIN"),
        ("Referrer-Policy", "strict-origin-when-cross-origin"),
    ]
    if status == 429:
        headers.append(("Retry-After", "5"))
    if status == 405:
        headers.append(("Allow", "GET, HEAD"))
    start_response(f"{status} {HTTPStatus(status).phrase}", headers)
    return [b"" if environ["REQUEST_METHOD"] == "HEAD" else body]
