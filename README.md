# Gridlock — coordination radar

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
node --test tests/radar-model.test.js

cd ../gridlock-data-pipeline
.venv/bin/python -m pytest -q
```

The workbook is an analyst report, never a source of truth. Legacy files under `data/` remain historical/demo inputs and are not consumed by the canonical website loader.
