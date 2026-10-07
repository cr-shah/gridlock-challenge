"""Reproducible lexical research inventory; never reads env files or executes reference code."""

import json
from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
REFERENCES = ROOT.parent / "reference-repos"
URL = re.compile(r"https?://[^\s\"\'<>`]+")
ENV = re.compile(
    r"(?:process\.env\.|os\.environ\[?[\"\']?|(?:getenv|env|env_float)\([\"\'])([A-Z][A-Z0-9_]+)"
)
GEO = re.compile(
    r"\b(?:BBOX|BOUNDS|REGION_BOUNDS|UTM|EPSG|setView|fitBounds|flyTo|center|MAX_MAP_POINTS|MAX_EXPORT)\b"
)


def audit():
    result = {}
    for name in [
        "gridlock-atlas",
        "gridsight",
        "shellhacks26",
        "Shellhacks-2026-fradicus",
    ]:
        repo = REFERENCES / name
        paths = subprocess.check_output(
            ["git", "-C", str(repo), "ls-files"], text=True
        ).splitlines()
        entry = {
            "commit": subprocess.check_output(
                ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
            ).strip(),
            "root_licenses": [
                p
                for p in paths
                if "/" not in p and p.upper().startswith(("LICENSE", "COPYING"))
            ],
            "endpoints": [],
            "environment_names": [],
            "geographic_assumptions": [],
            "manifests": {},
        }
        for relative in paths:
            p = repo / relative
            if p.name in {"package.json", "pyproject.toml", "requirements.txt"}:
                entry["manifests"][relative] = (
                    p.read_text() if p.suffix != ".json" else json.loads(p.read_text())
                )
            if (
                p.suffix not in {".py", ".ts", ".tsx", ".js", ".mjs", ".cjs"}
                or any(part in {"plans", "node_modules", ".claude"} for part in p.parts)
                or p.stat().st_size > 600000
            ):
                continue
            for number, line in enumerate(
                p.read_text(errors="replace").splitlines(), 1
            ):
                for match in URL.findall(line):
                    try:
                        url = urlsplit(match.rstrip("),;"))
                        if url.username or url.password:
                            continue
                        # Query values and fragments can contain credentials; inventory only host and path.
                        public = f"{url.scheme}://{url.hostname}{url.path}"
                        entry["endpoints"].append(
                            {"file": relative, "line": number, "url_template": public}
                        )
                    except ValueError:
                        pass
                for variable in ENV.findall(line):
                    entry["environment_names"].append(
                        {"file": relative, "line": number, "name": variable}
                    )
                if GEO.search(line):
                    entry["geographic_assumptions"].append(
                        {"file": relative, "line": number}
                    )
        result[name] = entry
    return {
        "note": "Lexical source inventory, not a list of validated live services. Query values omitted. See INTEGRATION_PLAN.md for interpretation and selected integrations.",
        "repositories": result,
    }


if __name__ == "__main__":
    output = ROOT / "docs/REFERENCE_INVENTORY.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    data = audit()
    output.write_text(json.dumps(data, indent=2) + "\n")
    print(
        {
            k: {
                name: len(v[name])
                for name in ("endpoints", "environment_names", "geographic_assumptions")
            }
            for k, v in data["repositories"].items()
        }
    )
