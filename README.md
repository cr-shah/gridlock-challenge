# Gridlock — coordination radar

## Public hosting

The full app can run as one Free Python service using the included `render.yaml`
and production Gunicorn entrypoint. [Deploy on Render](https://render.com/deploy?repo=https://github.com/cr-shah/gridlock-challenge)
requires a signed-in hosting account. See [deployment instructions and checks](docs/DEPLOYMENT.md).
This is a deployment link, not an already-live app URL. No keys are needed for the
national tools; the public paid AI analyst is disabled. Local AI setup is unchanged.

## Nationwide intelligence

The local landing page now opens the national explorer: 12,334 filing records, 5,399
located records, 1,352 national provisional candidates, plus the original 24 regional
coordination opportunities. These are records from mixed-vintage public filings, not
a complete or deduplicated inventory of active physical projects. Most active mapped
locations are tentative; source review and date precision remain visible.

Run `.venv/bin/python -m analyst.server` and open <http://127.0.0.1:8002/>.
The original overview remains at `/index.html`, and Radar at `/index.html?view=radar`.
Static-only hosting can still serve the regional pages; national exploration requires
the Python API server. No API keys are required for national exploration or public
NWS/USDA/FWS context. Existing AI configuration remains unchanged.

Use **3D time lens** above the map to explore filed dates vertically and play through
years. Select a project or click a map point, then open **Historical work-window lab**
to replay 2016–2025 NOAA observations against editable workday/weather assumptions.
Both retain unknowns and source confidence; replay is a scenario, not a forecast.

See [the integration plan](INTEGRATION_PLAN.md), [delivery and API documentation](docs/NATIONWIDE.md),
and [attribution](ATTRIBUTION.md). National records are imported through a separate,
hashed adapter; the sibling pipeline remains authoritative for the original catalog.

Gridlock turns the pipeline-published DESC and Georgia Power project catalog into a local coordination dashboard. The website shows all canonical projects, labels geometry confidence, and publishes only geographically close, schedule-aligned opportunities.

## Data flow

```text
gridlock-data-pipeline/data/published/gridlock_master_projects.json
  → scripts/publish_downstream.py
  → data/published/website_data.json
  → Coordination Radar + Project Explorer + AI Analyst
```

The sibling `gridlock-data-pipeline` repository owns project identity, dates, provenance, and verified/estimated/unresolved geometry. Files under `data/published/` are generated outputs and must not be edited independently.

The Radar uses one project inventory. Verified and estimated geometry are confidence states, not separate datasets. Unresolved projects remain in Project Explorer but cannot produce spatial opportunities.

## Opportunity policy

Every published opportunity must satisfy both rules:

- closest-point distance is less than 40 km;
- the recorded project windows overlap or have a known gap of no more than two years.

Distance assigns the action tier:

| Distance | Action tier |
| --- | --- |
| Touching / crossing | Must coordinate |
| `< 1.6 km` | ROW / land coordination potential |
| `< 8 km` | Site logistics coordination potential |
| `< 40 km` | Crews / equipment coordination potential |

The publisher fails if project dates are invalid, coordinates leave the SC/GA planning region, identities drift, opportunity references are duplicated, or saved dates/distances/tiers disagree with a fresh deterministic calculation.

## Regenerate from the data pipeline

From the sibling pipeline checkout:

```bash
cd ../gridlock-data-pipeline
.venv/bin/python -m gridlock_pipeline publish --product-root ../gridlock-challenge
```

This regenerates the canonical JSON/NDJSON/CSV and manifest, then refreshes website data, summary statistics, Project Explorer data, integrity hashes, and `gridlock_all_project_pairs.xlsx`.

## Run locally

```bash
cd ../gridlock-challenge
.venv/bin/python -m analyst.server
```

Open `http://127.0.0.1:8002/`. The dashboard and Project Explorer work without an AI key. Ask GridLock requires the local `.env` setup documented in `AI_ANALYST.md`.

## Verify

```bash
cd gridlock-challenge
.venv/bin/python -m unittest discover -s tests
node --test tests/*.test.js

cd ../gridlock-data-pipeline
.venv/bin/python -m pytest -q
```

The workbook is an analyst report, never a source of truth. Legacy files under `data/` remain historical/demo inputs and are not consumed by the canonical website loader.
