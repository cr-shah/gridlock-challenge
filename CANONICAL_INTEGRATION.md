# Canonical integration report

Imported the product publication from `cr-shah/gridlock-challenge`, branch `feat/real-data-integration`, commit `94156f6cd373bff4def28b7daa8263841b54dbea`.

## Architecture

- `data/published/`: unchanged upstream master, website, explorer and statistics JSON; `import_receipt.json` records source commit, publication metadata, local SHA-256 hashes and import time.
- `canonical-data.js`: shared browser loader validates identity, version, local hashes and match references. It adapts `project_id` to the existing UI's `id` without changing identity. It uses published `analysis_geometry` directly.
- `master_dataset.py`: upstream adapter, unchanged.
- `canonical_repository.py`: validates local hashes, catalog consistency and saved match references for the Assistant. No GIS recomputation or data writes.
- `index.html` / `radar.js`: full coverage is default; Verified is optional; Demo is removed from dataset controls. Landing metrics use canonical counts.
- `project-explorer.html/js`: all 78 projects, including unresolved records; utility, year, type, voltage and geometry-status filters.
- `analyst/core.py` / `analyst/server.py` / `ai-analyst.js`: canonical-only grounding, publication provenance on citations, nested published assets served safely.

Full Radar: 59 mapped projects, 38 matches. Verified-only: 15 mapped projects, 6 matches. Catalog: 54 DESC + 24 GPC = 78 projects; geometry states: 15 VERIFIED, 44 ESTIMATED, 19 UNRESOLVED. Unresolved projects are not mapped. Saved geometry, distances, tier rules, scoring code and original legacy data files are unchanged.

## Integrity limitation

The pipeline repository could not be authenticated, and its raw publication manifest URL returned 404. Therefore **upstream manifest verification has not been completed**. The imported product files are pinned to the above Git commit; local hashes detect subsequent changes but do not substitute for the publisher's manifest. `upstream_manifest_verified` is explicitly false in the import receipt. Obtain the authentic pipeline manifest and verify the master artifact against it before treating this import as fully publisher-verified. The publisher scripts were not copied or run; this integration consumes an existing snapshot.

After a new publication, import the complete matching set and verify it against the authentic upstream manifest before updating the receipt. Never mix publication versions or edit generated project fields by hand.

## Validation

- `.venv/bin/python -m unittest discover -s tests`: 60 passing tests, including existing scoring/estimated-coverage tests and new canonical integration tests.
- JavaScript syntax checks and execution of the shared browser adapter against the imported files: passed; verified 78 catalog records, 59/38 full projects/matches and 15/6 verified projects/matches.
- Inline JavaScript parsing: passed.
- No live Gemini calls needed for this integration. No billing changes or paid services added.

## Database readiness

The app consumes JSON directly and needs no database. No MongoDB/SQL server, migration or import was created. The canonical IDs and provenance are available for a future database adapter. Pipeline NDJSON/CSV and authenticated publication manifest access are still required for the handoff's full database import workflow.

Changes are local; nothing was committed or pushed.
