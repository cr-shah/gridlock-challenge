# Canonical integration report

## Current architecture

- `gridlock-data-pipeline` owns the canonical 78-project publication and machine-readable manifest.
- `python -m gridlock_pipeline publish --product-root ../gridlock-challenge` regenerates both repositories end to end.
- `scripts/publish_downstream.py` creates website, explorer, summary, workbook, and integrity-receipt outputs.
- `publication_validation.py` fails publication when identities, dates, regional coordinates, geometry precedence, pair references, closest-point distances, distance tiers, or the two-year schedule policy are inconsistent.
- `canonical-data.js` and `canonical_repository.py` validate hashes and publication logic before browser or AI consumption.
- The Radar presents one unified coverage view. Geometry remains explicitly `VERIFIED`, `ESTIMATED`, or `UNRESOLVED`.

## Current publication

- 78 canonical projects: 54 DESC and 24 Georgia Power.
- 15 verified geometries, 44 estimated geometries, and 19 unresolved geometries.
- 59 mapped projects and 840 evaluable cross-utility pairs.
- 38 pairs are under 40 km.
- 24 of those pairs have a known timeline gap of at most two years and are published as opportunities.
- Pairs with unknown timing or gaps of three years or more remain analysis candidates but do not appear as coordination opportunities.

The local master artifact is verified against the sibling pipeline publication manifest. The import receipt records the pipeline commit, publication timestamp, policy, verification result, and hashes of every browser-consumed artifact.

## Boundaries

- Verified geometry always takes precedence over estimated geometry.
- Estimated geometry remains labeled and is for planning screening only.
- Unresolved projects remain in the catalog; coordinates are never invented.
- Excel is a generated review artifact and is never read by the application.
- AI explains saved evidence. It does not calculate distance, alter project facts, or create opportunities.
- Every opportunity still requires source review and human validation before coordination decisions.

## Verification

The website test suite covers canonical integrity, publication policy, date/place/distance corruption, the analyst boundary, scoring, and map-model helpers. The pipeline suite covers deterministic extraction, normalization, canonical publication, transport formats, manifests, and failure preservation. Desktop and mobile browser checks cover the Radar, schedule filtering, detail selection, Project Explorer, and responsive overflow.
