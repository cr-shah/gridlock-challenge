"""Bounded public-service transport and coalescing TTL cache. No caller-supplied URLs."""

from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import ssl
import sys
import threading
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, HTTPRedirectHandler, HTTPSHandler, build_opener

HOSTS = frozenset(
    {"api.weather.gov", "sdmdataaccess.nrcs.usda.gov", "fwspublicservices.wim.usgs.gov"}
)


def utcnow():
    return datetime.now(timezone.utc).isoformat()


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch_json(url: str, body: dict | None = None) -> dict:
    p = urlsplit(url)
    if (
        p.scheme != "https"
        or p.hostname not in HOSTS
        or p.username
        or p.password
        or p.port
    ):
        raise ValueError("Unapproved provider URL.")
    headers = {
        "Accept": "application/geo+json, application/json",
        "User-Agent": os.getenv(
            "NWS_USER_AGENT", "GridlockResearch/1.0 (local planning explorer)"
        ),
    }
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    try:
        # Python.org macOS builds may lack a default CA bundle. Use the OS CA file;
        # verification and hostname checks remain enabled. Explicit deployment CA wins.
        cafile = os.getenv("SSL_CERT_FILE")
        if (
            not cafile
            and sys.platform == "darwin"
            and Path("/etc/ssl/cert.pem").is_file()
        ):
            cafile = "/etc/ssl/cert.pem"
        context = ssl.create_default_context(cafile=cafile)
        with build_opener(NoRedirect(), HTTPSHandler(context=context)).open(
            Request(url, data=data, headers=headers), timeout=8
        ) as response:
            raw = response.read(6_000_001)
            if len(raw) > 6_000_000:
                raise ValueError("Provider response exceeds byte budget.")
            result = json.loads(raw)
            if not isinstance(result, dict) or result.get("error"):
                raise ValueError("Provider returned an invalid response.")
            return result
    except HTTPError as exc:
        raise ValueError(
            "Provider rate limited."
            if exc.code == 429
            else f"Provider HTTP {exc.code}."
        ) from None


class Cache:
    """Per-key coalescing, bounded entries/concurrency, retry cooldown, stale-on-error."""

    def __init__(self, max_entries=96, clock=time.monotonic):
        self.entries = OrderedDict()
        self.pending = {}
        self.lock = threading.Lock()
        self.gate = threading.BoundedSemaphore(4)
        self.max_entries = max_entries
        self.clock = clock

    def get(self, key, loader, ttl=300, stale_ttl=3600):
        while True:
            with self.lock:
                entry = self.entries.get(key)
                now = self.clock()
                if entry and now < entry["retry_at"]:
                    self.entries.move_to_end(key)
                    return deepcopy(entry["value"])
                pending = self.pending.get(key)
                if pending is None:
                    pending = self.pending[key] = threading.Event()
                    break
            if not pending.wait(20):
                return {
                    "status": "unavailable",
                    "limitations": ["Provider request is still running."],
                    "records": [],
                }
        try:
            if not self.gate.acquire(timeout=1):
                raise ValueError("Provider concurrency limit reached; retry shortly.")
            try:
                value = loader()
            finally:
                self.gate.release()
            if value.get("status") == "unavailable":
                raise ValueError(
                    "; ".join(value.get("limitations", ["Provider unavailable."]))
                )
            item = {
                "value": value,
                "good_at": self.clock(),
                "retry_at": self.clock() + ttl,
            }
        except Exception:
            if (
                entry
                and entry.get("good_at") is not None
                and self.clock() - entry["good_at"] <= stale_ttl
            ):
                value = deepcopy(entry["value"])
                value["status"] = "stale"
                value["limitations"] = list(
                    dict.fromkeys(
                        value.get("limitations", [])
                        + [
                            "Refresh failed; showing a bounded stale response with its original timestamp."
                        ]
                    )
                )
                item = {**entry, "value": value, "retry_at": self.clock() + 60}
            else:
                value = {
                    "status": "unavailable",
                    "records": [],
                    "retrieved_at": None,
                    "limitations": [
                        "Public provider unavailable or rate limited. Retry after one minute."
                    ],
                }
                item = {"value": value, "good_at": None, "retry_at": self.clock() + 60}
        with self.lock:
            self.entries[key] = item
            self.entries.move_to_end(key)
            while len(self.entries) > self.max_entries:
                self.entries.popitem(last=False)
            self.pending.pop(key).set()
        return deepcopy(value)
