# Gridlock — coordination radar

Product layer for the ShellHacks 2026 Gridlock Challenge.

Trusted DESC and Georgia Power project records go in. Closest-point geography, challenge distance tiers, and timeline comparison come out on a static map.

This repository does **not** scrape planning PDFs. Document discovery, parsing, validation, and provenance live in the separate `gridlock-data-pipeline` repo.

```
data/verified_projects.json  →  scoring_engine.py  →  data/analysis.json  →  index.html
```

## Run it

```bash
pip install -r requirements.txt
python scoring_engine.py                 # verified records → data/analysis.json
python scoring_engine.py --demo          # labeled placeholder data → data/demo_analysis.json
python -m http.server 8000
```

Open `http://localhost:8000`. Opening the HTML file directly (`file://`) will fail on `fetch()`.

`python -m unittest tests/test_scoring_engine.py` runs the focused engine tests.

## Where to put real records

Paste or export the first trusted DESC and Georgia Power projects into:

**`data/verified_projects.json`**

Then rerun `python scoring_engine.py`. Do not invent coordinates, routes, years, or ownership. If a field is unknown, leave it `null`.

`data/projects.json` is demo/legacy only. The dashboard can load it through the **Demo** toggle; it is never labeled verified.

## Product data contract

Each project in `data/verified_projects.json` should look like:

```json
{
  "id": "desc-okatie-mcintosh-tie",
  "utility": "DESC",
  "name": "Okatie - McIntosh 115kV Tie Reactor",
  "project_type": null,
  "planned_start_year": 2027,
  "planned_end_year": 2027,
  "in_service_year": null,
  "voltage_kv": [115],
  "geometry": [[-80.87, 32.26], [-81.24, 32.15]],
  "geometry_type": "LineString",
  "source_url": "https://...",
  "source_page": 14,
  "data_confidence": "HIGH"
}
```

- `utility` is `DESC` or `GPC` only.
- `geometry` uses GeoJSON axis order: longitude, latitude.
- Point: `[lng, lat]` with `geometry_type: "Point"`.
- LineString: `[[lng, lat], ...]` with `geometry_type: "LineString"`.
- A GeoJSON geometry object is also accepted.
- Missing geometry: counted, not mapped, not compared.
- Missing years: not treated as timeline overlap.
- See `data/product_schema.json` for the field list.

Legacy demo fields (`lat1`/`lng1`/`lat2`/`lng2`, `start_year`/`end_year`) still load so the original prototype dataset keeps working.

## How ranking works

The engine compares **only** DESC × GPC pairs, using Shapely closest-point distance on a local kilometer plane (not centroids).

| Distance | Tier |
| --- | --- |
| 0 / crossing | Must coordinate |
| < 1.6 km | Shared land / ROW potential |
| < 8 km | Shared site logistics potential |
| < 40 km | Shared crews / equipment potential |
| >= 40 km | excluded |

Geography is the primary rank (`400 / 300 / 200 / 100`). Timeline overlap adds `+10` and can never outrank a closer geographic tier. Pairs with unknown years get no overlap bonus. Ranking is deterministic: score, then distance, then project ids.

Illustrative savings ranges are attached only in demo mode and are labeled as assumptions — not verified utility costs.

## What this repo is not

Do not add PDF scrapers, SERTP parsers, historical ML, storm/outage features, a backend, or a database here. Keep the static GitHub Pages architecture.
