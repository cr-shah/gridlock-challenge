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

## MongoDB canonical ingestion

`import_projects.py` now reads `data/published/gridlock_master_projects.json` and
its sibling publication artifacts, not the historical `data/projects.json`.
It checks all four receipt hashes, publication identity, the existing deterministic
publication validator, catalog completeness, and BSON encoding before connecting.
The current reviewed import baseline is 78 projects (54 DESC / 24 GPC), with
15 VERIFIED, 44 ESTIMATED, and 19 UNRESOLVED geometries. A future publication
with different counts or artifact inventory requires explicit code/test review;
counts are never silently adjusted to accept incomplete input.

Local validation, without credentials or a MongoDB connection:

```bash
python -B import_projects.py --dry-run
python -B -m unittest discover -s tests -p 'test_mongo_ingestion.py'
```

Dry-run constructs and BSON-validates the same documents as a real import.
Runtime dependencies must already be installed from `requirements.txt`.
For a separately approved real import, export `MONGODB_URI` and `MONGODB_DB`
privately in your shell and run `python -B import_projects.py`. The importer does
not load `.env`, display credentials, or modify published files.

Every original canonical field is copied unchanged, including nulls and all three
geometry fields. MongoDB `_id` equals the retained `project_id`; `_ingest` contains
separate import bookkeeping. Dataset metadata stores the master SHA-256,
publication version/commit/time, ordered project IDs, original master metadata,
and the receipt plus its hash. All project and dataset upserts share one transaction
with snapshot read concern and majority write concern. No records are deleted.
The old ten demo records may remain, so total collection size is not the canonical
catalog size (initially 88 projects if those ten records are still present).

A future reader must select the exact dataset hash, query its ordered canonical
IDs with the matching `_ingest.dataset_id`, verify count and membership, and
restore source order. Never use an unqualified `projects` scan for the catalog.
Metadata is an import record, not a historical project snapshot: importing a later
publication replaces matching project IDs. Old metadata must not be served as a
complete snapshot after those records have changed. Matching documents are fully
replaced, so database-only fields on those IDs are not retained. Concurrent imports
of different publications should be serialized operationally.

This ingestion layer does not change Explorer, Radar, Analyst, or their data source.
The upstream-manifest flag is preserved and required from the receipt; the importer
verifies local artifact hashes but does not independently authenticate the sibling
pipeline or treat the receipt as a cryptographic signature.
