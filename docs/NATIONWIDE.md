# Nationwide release: architecture, delivery and verification

Implementation: October 6–7, 2026 (America/New_York). Imported evidence carries its original UTC timestamps.

## Delivered

The existing Python/Leaflet product now has a national landing page, normalized API,
indexed catalog, provider registry and independently cached public context services.
No React/Next migration, cloud database, paid model calls or deployment was necessary.

The catalog combines 12,256 Common Ground filing records with 78 original canonical
records. The national import omits 262 legacy DESC/GPC projections. There are 5,399
mapped records in the combined catalog, including historical records, and 1,352 saved
national candidates. The 24 original canonical opportunities retain their original
closest-geometry and known schedule-gap policy. Snapshot counts are not unique-asset
counts: separate filings/upgrade records can describe related physical work.

The default planning view contains 7,772 records (planned/proposed/under construction/
unknown; excludes explicit in-service and cancelled status). Of these, 3,231 are mapped:
61 reviewed, 270 official coordinates and 2,900 tentative. Unknown status is included
explicitly; a passed planned date is not treated as proof of completion.

New user workflows:

- Nation → state/territory → county vicinity → viewport → individual filing or sampled point.
- Alaska and Hawaii shortcuts; antimeridian-safe geographic queries. Empty territories
  show no imported records, not fabricated nationwide coverage.
- Project/owner/plan search, status and location-confidence filters, paginated record lists.
- National grid aggregation; individual geometry at local scales; automatic viewport
  filtering at zoom 7; at most 800 geographic features per response.
- Filed-year histogram with clickable filters; unknown and invalid dates remain unknown.
- Evidence drawer with original links, source page/sheet/row, location method, review
  state, raw source evidence and next-step coordination leads.
- Candidate comparison, display connectors (never described as driving routes), separate
  regional opportunity policy, exact day gaps only where both source dates are exact.
- NWS alert overlay and text list including alerts without polygons; point forecasts;
  USDA soil map units; FWS wetland point intersections; project/alert intersection screening.
- Provider-level unavailable/partial/stale responses, bounded CSV export with citations,
  coverage ledger, keyboard labels and responsive mobile layout.
- Optional 3D time lens with MapLibre 5.11.0, national aggregation, bounded local markers,
  date-height stems, precision spans, unknown-date ground markers, year playback, tilt toggle
  and selection linked back to the same evidence panel. It shares explorer filters and
  queries only its viewport; marker dimensions are symbolic, never asset dimensions.
- Milestone interval comparisons report possible minimum/maximum separation from the
  filed precision, without converting a milestone into an assumed construction window.
- Historical work-window lab from a filing or sampled map point: 1,979 imported NOAA
  stations, 3,653 aligned days per station (2016–2025), editable rain/wind/heat/freeze
  rules, monthly historical trials, median/range, exclusions and auditable trial details.

## Where the four references influenced the result

| Reference | Integration |
|---|---|
| Common Ground / fradicus | Validated assembled national release and saved candidate matcher output, scoped geography, inherited review confidence, date precision, evidence layout, environmental provider envelopes |
| Gridlock Atlas | Evidence-first decisions, keeping conflicting/imprecise dates visible, no false confirmation from point proximity, explicit source citations alongside results |
| Gridsight | Separate environmental observations from damage predictions, isolated live context, bounded asynchronous requests, clear uncertainty in map symbols |
| shellhacks26 / UtiliTies | Provider/query caching, independent failures, indexed geographic candidate selection, evidence-backed research workflow |

Reuse is based on the user's confirmation of the authors' ShellHacks agreement; see
`ATTRIBUTION.md`. Reference runtime code is not copied wholesale. The reference release
loader and matcher run during import only. The running product needs neither the
reference checkouts nor their cloud credentials.

## Modules and API

`nation/models.py`: coordinates, precision-aware milestones, query validation and provider
envelopes. `nation/service.py`: hash verification, canonical adapter, Shapely STRtree,
aggregation, filtering, detail, saved pair joins and alert intersection. `nation/providers.py`:
provider registry and NWS/SSURGO/FWS normalization. `nation/transport.py`: HTTPS host
allowlist, verified TLS, no redirects, 8-second socket timeout, 6 MB response cap,
coalescing TTL cache, 60-second retry cooldown and four concurrent upstream calls.
`nation/api.py`: read-only dispatch; existing server caps concurrent national requests at 8.

| GET endpoint | Contract |
|---|---|
| `/api/nation/geography` | State references, provider coverage, catalog counts and import receipt |
| `/api/nation/areas?state=45` | County reference bounds for a known state; bounds are not exact polygon membership |
| `/api/nation/projects` | Filtered count, ≤200 list records, confidence/year/state summary and ≤800 map features |
| `/api/nation/project?id=…` | One full evidence record and ≤50 related saved pairs |
| `/api/nation/pairs` | Saved candidates/opportunities, paginated and scoped to both project IDs |
| `/api/nation/alerts` | ≤500 normalized NWS alerts; capped or malformed feeds are explicitly partial |
| `/api/nation/site?provider=…&lon=…&lat=…` | `nws-forecast`, `ssurgo` or `wetlands`; independent point response |
| `/api/nation/exposure?id=…` | Intersections with eligible alert polygons; null polygons and tentative geometry remain caveats |
| `/api/nation/history?lon=…&lat=…` | Eligible NOAA station references, distance/completeness, original citations and at most five aligned daily arrays for one point |

Project/pair parameters: `bbox=west,south,east,north` (west>east crosses the antimeridian),
`state` (FIPS), `text` (≤120 chars), `status`, `confidence`, `year`, `zoom` (1–18),
`limit` (1–200), `offset` (0–100000). Unknown or repeated parameters are rejected.
Status defaults to `active`, which includes unknown status. Viewport queries exclude
unlocated records and state this explicitly. A state filter uses reported state membership,
not a claim that the entire route lies inside that state. Regional canonical state membership
follows its source service area. County navigation uses bounds to frame the viewport.

Public responses never contain credentials. The 2.7 MB compressed national archive and
raw Python modules are not statically served. Evidence is loaded for one record at a time.
CSV exports cap at 2,000 rows, reject mixed dataset identities, and escape spreadsheet
formula prefixes. Provider failure text does not expose arbitrary upstream content.

## Data integrity and regeneration

`data/nation/catalog.json.gz` is one compressed normalized snapshot, with a SHA-256 receipt
in `receipt.json`. Import uses Common Ground revision `26b3b70451faa7ba8c54d2c57662cbaa3086ac4e`.
Its loader validates all active regional releases before normalization; it is not sufficient
to import just `data/national/projects.json`, which is only the base layer.

From the product checkout:

```sh
../gridlock-data-pipeline/.venv/bin/python scripts/import_national.py
.venv/bin/python scripts/audit_references.py
.venv/bin/python scripts/import_weather.py
```

The importer needs `jsonschema` through the sibling pipeline environment. It makes no
network or database calls, writes only the product artifact/receipt and disables bytecode
writes in the reference checkout. Runtime uses existing product dependencies: Shapely and
python-dotenv. Pin the reference checkout before reimporting if reproducing a previous release.

The separate weather importer validates all 1,979 station records and writes a 23.6 MB
ZIP plus an index with archive and per-station SHA-256 receipts. Runtime opens only the
eligible station entries, verifies their hashes, and caches at most 64 series. No entire
country archive is sent to the browser. Restart the local server after reimporting weather.
Neither archive nor index is statically served. NOAA provenance stays in each entry.

Historical selection requires ≥95% whole-window rain/temperature completeness within
30 miles; optional wind uses the same completeness floor within 60 miles. No eligible
station returns unavailable. Replay considers starts on each month's first day, weekdays
only, 1–60 required workdays, and a 180-calendar-day cap. Unknown required conditions
exclude a trial unless another observed condition already stops work. Archive-end and
horizon exclusions are shown separately. This makes missing readings explicit but does
not eliminate selection bias. The results are scenarios, not probabilities, forecasts,
site safety rules or guaranteed schedules. Variable thresholds are user assumptions.

The optional time renderer lazy-loads pinned MapLibre JS/CSS; the original Leaflet map
stays primary. The reference's 6.11.2 distribution returned 404 during verification, so
the implementation uses the available 5.11.0 release. It needs WebGL; unavailable library
or map resources leave the main list and evidence workflow intact. National clusters
show counts, not averaged dates. Local stems use the first geometry point as a symbolic
anchor. Day/month/year caps preserve precision; extremely thin caps have a minimum
display thickness. Scale changes with zoom and is explicitly described in the UI.

Original hashes, evidence, raw milestones, publisher links, inherited location review and
OSM attribution stay attached to the records. Three active source milestones with year
`3033` were excluded from the normalized timeline; raw values and explicit date issues are
retained in the evidence. No replacement year was guessed. National imports do not alter
the original publication, receipt, scoring policy or sibling pipeline outputs.

`docs/REFERENCE_INVENTORY.json` records 476 URL-template occurrences, environment-variable
names and geographic-assumption locations across the four reference codebases. It is a
lexical inventory, not a guarantee that every mentioned endpoint is live. Query strings
are omitted and `.env` files are not read. The plan supplies the comparative assessment.

## Reliability and operations

Set `GRIDLOCK_OFFLINE=1` for an offline catalog session; live providers explicitly show
unavailable. `NWS_USER_AGENT` can identify a deployment contact. No new paid keys are needed.
Python.org macOS builds can lack the operating-system CA path: the transport uses
`/etc/ssl/cert.pem` on macOS when present, or an explicit `SSL_CERT_FILE`. Certificate and
hostname verification remain enabled.

NWS alerts cache for 3 minutes, with at most 15 minutes of stale-on-error retention;
expired alerts are removed even from cached responses. Site context caches for 15 minutes,
with at most 1 hour of stale retention. Failure cooldowns prevent repeated refresh storms.
One provider never supplies invented fallback data for another. Tile/library failures leave
the searchable list and evidence UI available. OSM standard tiles are for modest interactive
use; a public high-volume deployment needs an appropriate tile service and shared caching.

The built-in HTTP server is a local development server, not a hardened multi-tenant public
deployment. A public rollout still needs a production server, shared upstream budgets,
metrics, deployment configuration and load testing. No site has been published.

## Verification

```sh
.venv/bin/python -m unittest discover -s tests
node --test tests/*.test.js
node --check nationwide.js
node --check nationwide-model.js
../gridlock-data-pipeline/.venv/bin/ruff check nation scripts/import_national.py scripts/audit_references.py scripts/smoke_national.py tests/test_nation.py --select E9,F
.venv/bin/python scripts/smoke_national.py --live
```

The added tests cover malformed coordinates/dates, precision, antimeridian queries,
SSRF refusal, null alert polygons, expired/test alerts, partial feeds, cache coalescing,
TTL/cooldown/stale expiry, hash corruption, canonical preservation, bounded payloads,
spatial index correctness, evidence detail, CSV safety and county reference navigation.

Baseline before edits: product 68 Python + 27 JS tests; sibling pipeline 122 tests.
Verified suite: product 98 Python + 41 JS tests. The sibling pipeline remains
unchanged from its initial dirty state. Live checks at the public test coordinate
(-82, 34) returned a 48-period NWS forecast, one USDA soil component and an available,
empty FWS intersection. The final national NWS request returned 188 alerts at verification.
These are smoke observations at that time, not guaranteed ongoing provider availability.

Final independent review found and prompted fixes for combined dataset identity and
browser alert freshness. Export identity now hashes both validated national and canonical
content. Visible alerts prune expiration every 15 seconds and refresh their feed every
three minutes, including after a background tab returns; failed refresh clears the overlay.
Desktop time-map playback and real NOAA scenario recomputation were browser-verified;
the planner fits a 390-pixel mobile viewport without horizontal overflow.

## Product boundaries

The selected nationwide exploration and planning workflows are implemented. Research
directions needing new source acquisition, paid services or calibration are intentionally
not represented as working integrations: live nationwide construction updates,
cross-filing asset deduplication, independent national geocoding review, truck routing,
live outages, national permit coverage, calibrated storm damage, crew dispatch and
autonomous source ingestion. Production vector tiles/shared storage are scaling options,
not required by the current bounded snapshot. Forecasts shown are official NWS forecasts;
historical replay is explicitly a scenario. We do not claim to predict outages,
construction completion or monetary savings from these data.
