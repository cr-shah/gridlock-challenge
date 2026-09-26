# Gridlock — work so far

This note is for teammates. It covers the product repo (`cr-shah/gridlock-challenge`) through 26 September 2026. It does not replace the pipeline repo.

## What this product is

Gridlock is a static DESC × Georgia Power coordination dashboard. It compares planned transmission projects by closest-point distance, then uses timing only as a secondary rank. The site is one HTML file plus Leaflet. Scoring is `scoring_engine.py`. Nothing is scraped in this repo.

The current product branch is `feat/real-data-integration`. It is not merged into `main`. Draft pull request: https://github.com/cr-shah/gridlock-challenge/pull/2

The site opens in **Verified** mode. **Estimated Coverage** is a separate toggle. Demo data stays on the Demo toggle.

## Repos

| Repo | Role | Status on GitHub |
|---|---|---|
| `cr-shah/gridlock-challenge` | Product: scoring, map, verified records, estimated screening | `feat/real-data-integration` is pushed at `6ed3af7` |
| `cr-shah/gridlock-data-pipeline` | PDF discovery, parsing, validation, provenance | Not visible from this environment. `git ls-remote` returns "Repository not found" for that URL. There is no local clone here, so this note cannot confirm that pipeline `main` is up to date. |

Other product branches already on GitHub, left unmerged: `main`, `feat/product-polish`, `feat/real-data-mvp`.

## Verified mode

Verified mode scores only `data/verified_projects.json`. It does not score `data/projects.json` or `data/demo_analysis.json`.

```bash
python scoring_engine.py
# writes data/analysis.json
```

Rules that stayed in place:

- DESC × GPC only. Same-utility pairs are never compared.
- Distance is closest point to closest point, in kilometers, on the local equirectangular projection in `scoring_engine.py`. GeoJSON order is longitude, latitude.
- Tiers, unchanged: touching/crossing, under 1.6 km, under 8 km, under 40 km. Pairs at 40 km or more are excluded.
- A project with null geometry is counted and not compared.
- Missing years are not treated as overlap.
- Official geometry is never overwritten by an estimate.

### Verified result

78 projects: 54 DESC, 24 GPC. 15 have usable geometry (4 DESC, 11 GPC). 63 have no usable geometry.

1,296 possible DESC × GPC pairs. 44 pairs have geometry on both sides. **6 pairs are inside 40 km.** All six are shared-crews. None are under 8 km, under 1.6 km, or touching. None have overlapping schedules.

| km | DESC | GPC |
|---|---|---|
| 31.18 | Jasper–Okatie 230 kV #2 | Dean Forest–Little Ogeechee Rebuild |
| 31.49 | Okatie 230–115 kV substation | Dean Forest–Little Ogeechee Rebuild |
| 32.22 | Jasper–Okatie 230 kV #2 | Meldrim Bank D Replacement |
| 33.55 | Jasper–Okatie 230 kV #2 | Boulevard–Magnolia–Truman Parkway Rebuilds |
| 33.62 | Okatie 230–115 kV substation | Boulevard–Magnolia–Truman Parkway Rebuilds |
| 37.30 | Okatie 230–115 kV substation | Meldrim Bank D Replacement |

The nearest excluded pair after the Savannah geometry was added is Jasper–Okatie vs Little Ogeechee, at 41.00 km.

### How the verified set got here

1. The first real file had 64 projects (54 DESC, 10 GPC) and 5 usable geometries. Scoring produced 4 evaluable pairs and 0 pairs under 40 km. The closest evaluable pair was Urquhart–Aiken vs Callaway–Thomson at 42.82 km.
2. The file grew to 78 projects (54 DESC, 24 GPC) with 11 usable geometries. Still 0 pairs under 40 km.
3. Four Savannah GPC geometries were added (Dean Forest–Little Ogeechee, Boulevard–Magnolia–Truman Parkway, Little Ogeechee autotransformer, Meldrim Bank D). That produced the 6 pairs above.
4. Geometry provenance (`geometry_source`, `geometry_method`, `geometry_confidence`, `geometry_notes`) is kept on the scored records and shown in the UI.
5. Thin route lines were hard to click. The map binds the popup to the route and draws an invisible wider hit line.

### Spatial check, before the six pairs

A separate check confirmed the early zero was real, not a unit or axis bug:

- Vertices are longitude, latitude inside a South Carolina / Georgia box.
- The engine distance for Urquhart–Callaway was 42.82 km. An independent geodesic check was about 42.92 km. Treating the raw degree gap as kilometers would have been a false under-1.6 km result.
- That 42.82 km is the distance from the Urquhart plant endpoint, not a traced Aiken route.
- Crossing test lines score 0 km. A one-degree latitude step is about 111 km.

The 40 km threshold was not changed.

A later request to paste invented Okatie, McIntosh, and Goshen coordinates into `verified_projects.json` and label them HIGH was not done. That would have fabricated verified geometry and collided with the official Okatie point. The demo file already has a labeled 0 km placeholder. It is not part of the verified result.

## Estimated Coverage

Estimated Coverage fills missing geometry for screening. It is stored in `data/estimated_geometry.json` and scored to `data/estimated_analysis.json`. Official rows in `verified_projects.json` are copied through and not replaced.

```bash
python estimated_coverage.py
python estimated_coverage.py --rebuild-geometry --osm-cache /tmp/osm_subs.json --hifld-cache /tmp/hifld_attrs.json
```

The on-screen flag is: **Estimated geometry — planning-screening use only.**

### How an estimate is chosen

In this order:

1. Two named endpoints that resolve to unique public facilities become a straight line. Method `approximate_verified_endpoints`, confidence `ESTIMATED`.
2. A rebuild, reconductor, or upgrade with a unique owner-and-voltage HIFLD corridor uses that corridor. Method `existing_corridor_hifld`, confidence `MEDIUM`.
3. One defensible named facility becomes a point. Method `estimated_facility_point`, confidence `ESTIMATED`.
4. Several confirmed pieces can be a MultiLineString.
5. County or region only becomes a Census internal-point anchor. Method `regional_screening_anchor`, confidence `LOW`. This can qualify only for the under-40 km screen.
6. Otherwise the project stays unresolved.

A new substation or autotransformer is not pinned to a different named facility. Rice Hope was not placed at McIntosh. Big Ogeechee was not placed at Little Ogeechee. Both are county anchors. Coleman is ambiguous in OpenStreetMap (two Georgia Power substations), so Coleman–Dean Forest is a Dean Forest point and Coleman–Meldrim is a Meldrim point. A Pineland name match about 188 km from V.C. Summer was not connected. The VCS1–Denny Terrace rebuild uses the HIFLD 230 kV corridor (one segment, 230 vertices).

### Who can enter a close tier

Under 8 km, under 1.6 km, and touching are allowed only when both sides are based on official or high-confidence geometry, two resolved endpoints, an existing HIFLD corridor, or an official facility point against a defensible line.

A single estimated facility point cannot create those tiers. A LOW county anchor cannot create those tiers. If the raw distance would have been closer, the pair stays in the under-40 km screen and is marked close-tier blocked. The coordination score never changes the distance tier.

Within a tier, the score is:

- +20 same construction year
- +10 one-year timing gap
- +10 shared named corridor, facility, or substation
- +5 Savannah River planning-area context when the project text supports it
- High confidence 0, medium −5, estimated −10
- Low confidence is kept out of the close tiers instead of given a numeric penalty

### Estimated result

Mapped projects went from 15 to 59. 44 estimates were added. 19 projects are still unresolved, all DESC. Every GPC project has either official geometry or an estimate.

| Method | Count | Confidence |
|---|---|---|
| `estimated_facility_point` | 27 | ESTIMATED |
| `approximate_verified_endpoints` | 10 | ESTIMATED |
| `regional_screening_anchor` | 6 | LOW |
| `existing_corridor_hifld` | 1 | MEDIUM |

840 evaluable pairs. 38 are under 40 km. 2 are under 8 km. 1 is under 1.6 km, and that pair is the touching pair. 6 pairs share a construction year. No close pair was blocked in the saved run, because the only under-8 km pairs use eligible geometry.

**0.00 km, touching.** Okatie–McIntosh 115 kV Tie and Goshen (Savannah)–McIntosh Rebuild. Both are straight lines to the same public McIntosh substation (`way/121624352`). Okatie uses the official substation point. Goshen uses the Savannah-area Georgia Power substation, not the Augusta one. Both are in service in 2028. This is a shared terminal on two screening lines, not a surveyed crossing. Score 25.

**4.83 km, under 8 km.** Official Jasper–Okatie route (HIGH) and the same Goshen–McIntosh straight line. The closest points are the west end of the official corridor and the McIntosh terminal. Jasper is 2026 and the rebuild is 2028. Score −5.

The original six verified pairs still appear inside this screen, at the same distances, because their official geometry is included unchanged.

## What was deliberately left alone

- `scoring_engine.py` distance math
- Official coordinates in `data/verified_projects.json`
- The 40 km threshold
- The pipeline repository
- Merging `feat/real-data-integration` into `main`

## Tests

```bash
python -m unittest tests.test_scoring_engine tests.test_estimated_coverage
```

41 tests passed after Estimated Coverage landed, including the check that the verified file still produces exactly 6 pairs under 40 km. Estimated-mode tests cover the close-tier bans, the two-endpoint and HIFLD allowances, the rule that score does not reorder tiers, and the guard that official geometry is not replaced.

## Run the site locally

```bash
pip install -r requirements.txt
python scoring_engine.py
python estimated_coverage.py
python -m http.server 8000
```

Open `http://localhost:8000`. `file://` cannot load the JSON.

## Public site

GitHub Pages is on and built, but it still publishes `main`:

https://cr-shah.github.io/gridlock-challenge/

That URL does not yet serve Estimated Coverage. `data/estimated_analysis.json` returns 404 there. Switching Pages to `feat/real-data-integration` needs a repo admin. This environment's token received HTTP 403 on the Pages API.

To publish the product branch without merging the pull request: open the repository Settings, then Pages. Under Build and deployment, leave the source as "Deploy from a branch". Set the branch to `feat/real-data-integration` and the folder to `/ (root)`. Click Save.

## Branch tip

`feat/real-data-integration` at `6ed3af7` — "Add Estimated Coverage screening without changing verified geometry."
