# Gridlock nationwide integration plan

Research baseline: 2026-10-06. Reference commits: Atlas `05e1c82`, Gridsight `e9bf707`, Tandem/UtiliTies `5de6ee1`, Common Ground/fradicus `26b3b70`. References are research checkouts, not dependencies. This plan separates delivered work from future integrations; see `docs/NATIONWIDE.md` for implementation status and verification.

**User clarification, 2026-10-06:** the authors agreed at ShellHacks to open-source sharing and reuse. This permission supersedes the initial conservative no-reuse recommendation below. Integrate Common Ground's validated assembled static release (not its small base snapshot), retain source/review evidence and attribution, omit legacy DESC/GPC projections in favor of our canonical publication, and run the reference loader/matcher only during reproducible import. Runtime remains independent. API/data licensing and completeness limitations still apply. The original findings below are retained to distinguish the checkout's contents from the user's permission.

## 1. Existing architecture and migration boundary

Completion pass, 2026-10-07: the dated national release and authorized NOAA archive now justify advancing two initially deferred features. Implement a lazy MapLibre 5.11.0 time lens with server-bounded viewport data, precision spans and linked evidence; import the 1,979-station NOAA archive and add transparent historical work-window replay. Preserve all recorded uncertainty. These replace the earlier deferrals of time pillars and historical replay below. No paid routing, uncalibrated damage, invented savings or autonomous data acquisition is needed for this release.

`gridlock-challenge` is the product. Vanilla JavaScript/Leaflet renders the overview, Coordination Radar, Project Explorer and Project Discovery. `analyst/server.py` serves allowlisted assets and a same-origin AI API. `analyst/core.py` grounds AI answers in stored evidence. `canonical_repository.py`, `canonical-data.js` and `publication_validation.py` check the publication before consumption. `estimated_coverage.py` and `scoring_engine.py` calculate closest-point geometry, timing and coordination tiers.

The sibling `gridlock-data-pipeline` owns extraction and canonical publication. Its Pydantic observations retain PDF hashes, page references, raw fields, deterministic transformations and review flags. Publication writes verified JSON/NDJSON/CSV and downstream receipts. The current catalog has 78 records, 59 mapped locations and 24 eligible opportunities. Baseline product checks: 68 Python and 27 JavaScript tests pass.

KEEP: canonical IDs, source citations, geometry precedence, existing pages, analyst boundary, strict regional publication gate, existing working integrations. IMPROVE: navigation, national context, coverage reporting, geographic query limits. REFACTOR: add reusable provider contracts beside the existing publisher, with no rewrite of its artifact format. ADD: national explorer, provider diagnostics, state navigation, source-backed infrastructure and weather, site forecast, context screening, bounded exports. REPLACE: nothing wholesale. Existing uncommitted pipeline edits and `_to_delete/` are outside this change.

Do not relax SC/GA validation to pretend the current publisher produces nationwide records. Its bounds describe that source adapter. New providers use WGS84 validation and explicit coverage instead. National infrastructure is not the same entity as future construction projects.

## 2. Repository findings and capability matrix

| Capability | Ours | Atlas | Gridsight | Tandem | Common Ground | Strongest approach / decision |
|---|---|---|---|---|---|---|
| Publication integrity | Hash receipts; fail-closed deterministic validation | Quote audits and baseline evaluation | Generated JSON and contract tests | Run snapshots and validator agents | Versioned dataset pointer, schemas, sole DB writer | Keep ours; use immutable snapshot identity for new caches |
| Matching | Closest-point + known schedule gap ≤2 years | Claim-aware geometry and source-conflict timing | UTM17N closest points; uncertainty tier sensitivity | Grid candidate index; local planar segment distance | Earth-centered 3D buckets, haversine provisional pairs, routed regional pairs | Preserve ours; indexed queries for national assets; don't mix center and route distance |
| Date precision | Year-level schedule | Hard/soft intervals over source claims | Assumed build durations by project type | Exact dates plus inferred windows | Day/month/year/unknown, exact gaps only | Adopt precision-aware presentation; no invented construction dates |
| Nationwide coverage | SC/GA plans only | Additional regional plans | Mostly SC/GA network | Extensible source table; regional assumptions remain | Multi-region source adapters and coverage denominators | Common Ground's registry and explicit gaps; reacquire original sources |
| Map/UX | Leaflet radar and project details | Mapbox layers, pair closeups, Gantt | MapLibre/deck.gl storms and replay | MapLibre agent activity and filter rail | MapLibre/Three shared camera, scopes, hollow tentative markers, evidence | Adapt scopes, confidence and progressive detail in current Leaflet stack |
| Environment | No live nationwide context | GA/SC permit checks | Storm wind/tree models, wetlands | Research enrichment | NWS, soil, water, wetland, flood, truck routes | Start with national infrastructure + NWS; provider isolation for additional context |
| Forecasts | No damage forecasts | What-if displays | Monte Carlo damage and aid scheduling | Savings assumptions and research | Historical weather replay with editable work rules | NWS forecast first; defer damage/cost prediction until calibrated |
| Evidence UX | Source and geometry notes | Claim-level excerpt provenance | Modeled/observed distinction | Filing citations and validation stream | Project evidence, coverage ledger, clear unknowns | Add evidence drawer and per-layer status |
| Storage | Portable JSON artifacts | Static snapshot | Timescale outages, static simulation | SQLite source config, Postgres event runs | MongoDB 2dsphere, active dataset | Start local indexed memory + bounded providers; leave DB migration for measured scale |

### Gridlock Atlas — source trace

`scripts/ingest/*` fetch and normalize source documents; `scripts/audit-data.ts` audits quoted evidence. `lib/domain/types.ts` distinguishes claims, places, relations and dates. `lib/matching/geo.ts` handles named-facility/locality/official-GIS precision and location uncertainty; `lib/matching/time.ts` intersects earliest/latest intervals and handles missing/conflicting windows. `lib/matching/engine.ts` retains source conflicts. `components/map/layers.ts`, `MapStage.tsx`, `components/closeup/Scene.tsx`, `TimeLayer.tsx` and `components/timeline/PairGantt.tsx` drive the map, Three scene and timelines. Zustand manages selection. Next route handlers expose snapshots/matches/permits. `lib/permits-live.ts` uses GA ASP.NET form state/cookies and SC ArcGIS within a fixed Savannah-area box; this is regional, not a generic national permit service. Mapbox needs a restricted public token. Extraction keys remain server-side. Best lessons: uncertainty affects claims, conflicting sources remain visible, transparent interval logic. Avoid its fixed permit counties and browser delivery of full growing snapshots.

### Gridsight — source trace

`pipeline/gridsight/plan/parse_desc.py`, `parse_sertp.py`, `gpc_web.py` feed geometry and overlap modules. `plan/overlap.py` uses UTM17N Shapely distances and four tiers, with confidence × robustness × weighted tier/distance/window/size scoring. Its build windows use 9–24 month assumptions; these are not filed dates. `response/network.py` segments OSM lines and attributes archived HIFLD owners. `wind.py` builds a Holland wind field; `fragility.py`, `treefall.py`, `simulate.py` propagate physical/track uncertainty using PyTorch. `zones.py`, `yards.py`, `mutual_aid.py` group repair demand and compare logistics schedules. `eaglei.py` range-reads historical outage CSVs. `outage_cost.py` combines EIA usage with interruption-cost assumptions. Frontend workers, deck.gl layers, replay state and Timescale buckets keep playback usable. Gemini utility search, grant research and ElevenLabs voice are optional server integrations. Strong ideas: separately display observations and model outputs; move expensive simulation offline; request deduplication and bounded workers. Do not transfer SC/GA calibration or arbitrary weighted scores nationally.

### shellhacks26 / Tandem — source trace

FastAPI `backend/app/main.py` exposes pipeline, sources, research and chat. `runtime/executor.py` validates a DAG, waits for dependency events, applies per-agent timeouts and skips descendants of failed jobs. The source table is SQLite; run/event persistence optionally uses Tiger Postgres. `clients/cache.py` keys responses by provider/version/payload. Provider clients have retry/fallback and redaction. `agents/geocoder.py` prefers overrides, sponsor points, OSM and towns, with source-state/span guards and judge calls. `core/overlap.py` bins geometry bounds into 0.5-degree cells before exact local segment comparisons; it retains a separate center-distance benchmark. Research, cost and writer agents preserve source evidence, but savings percentages remain assumptions. `frontend/components/MapView.tsx` has an offline vector fallback, source glyphs, queued animations and zoom-dependent detail. Zustand owns UI state. Static Next frontend and FastAPI deploy independently. Best lessons: source/provider separation, cached evidence, explicit validation and failure state. Do not bring an autonomous agent DAG into ordinary viewport requests.

## 3. Common Ground / fradicus detailed trace

The active app is under `web/`; historical `plans/` are design material, not deployed capabilities. Next 16/React 19 uses read-only MongoDB or explicitly labeled fixtures. `web/lib/server/repository.ts`, `queries.ts`, `deadline.ts` and `cache.ts` isolate storage, impose deadlines and key cached reads by file or dataset identity. National filters enforce geographic parent relationships and page/export limits. Mongo viewport reads use geospatial indexes. `pipeline/national/*` and regional packages acquire primary filings, preserve source manifests and separate official/tentative location evidence. `pipeline/national_pairs/build.py` checks known distinct ownership and indexes centers in 3D Earth-centered buckets; straight-line pairs stay provisional. This differs from our closest-line geometry and schedule eligibility policy.

Visual implementation:

- `web/components/time/TimeView.tsx`: map lifecycle, selection, scope, legend, camera, 2D/3D toggle and story playback. Scope changes dim excluded projects; selection moves the camera toward stored evidence.
- `timeLayer.ts`: MapLibre custom 3D layer creates a Three renderer on the map's GL context; Mercator anchors and shared camera projection align pillars with geography. Beam heights encode dates, not risk or monetary benefit. Geometry updates are quantized as zoom changes; GL resources are disposed on removal.
- `timeScale.ts`: exact days become points; month/year precision becomes a vertical span; unknown dates have no invented height. Screen pixels per year scale with zoom and available room. `scenePrimitives.ts`, `stateInk.ts`, `sceneCamera.ts`, `scope.ts`, `story.ts` separate geometry, geographic focus, camera fitting and a data-driven narrative.
- `NationalMap.tsx`: GeoJSON sources, review-dependent circle opacity, hollow approximate markers, fit-to-scope. `NationalExplorer.tsx` connects filtering, summary charts and evidence. `history/historyLayer.ts` uses the same geographic language for historical milestones. History must not be confused with future plans.
- `pair/EvidencePanel.tsx`, `Cite.tsx`, `NationalProjectEvidence.tsx`: source links, precision, coverage and review states close to the chosen object. CSS modules use quiet surfaces and restrained accent colors, keeping geographic context dominant.
- `operations/providers.ts` normalizes NWS, SSURGO, WSDOT and Routes data into envelopes. `transport.ts` allowlists hosts, refuses redirects, caps bytes and bounds time. `water.ts` adds gauges/tides/flood/wetland context. `impact/delayModel.ts` replays historical weather with editable stop rules and reports missing observations; no fitted forecasting probability is claimed.

Adapt now: national/state/local navigation, muted basemap, confidence marker styling, evidence drawer, timeline distribution, coverage counts, isolated provider errors. Defer the Three time towers until national filed-date data and a WebGL performance budget justify the complexity. A date histogram with explicit unknowns is initially more truthful for our year-only dates.

## 4. API and dataset inventory

Rates/costs below describe code observations or official documentation, not guaranteed quotas. No secrets were inspected. Model prices and provider quotas require account-specific confirmation before enabling paid jobs. All private keys belong on the server.

| Provider / dataset | References | Endpoints / format / processing | Coverage; auth; cost/rate | Recommendation |
|---|---|---|---|---|
| SCRTP DESC, SERTP, Georgia Power | All, ours | `scrtp.com/assets/pdfs/home/*`, `southeasternrtp.com/docs/general/*`, Georgia Power project pages; PDF/HTML → cited project rows | Regional public filings; no key; source publication cadence | Preserve audited pipeline |
| ISO-NE, PJM, MISO, SPP, ERCOT/PUCT, CAISO, BPA, utilities | Common Ground; additional regional Atlas/Tandem research | National source manifest plus `pipeline/{national,greatlakes,texas,california,pnw,southeast,...}`; XLSX/CSV/PDF/HTML parsers | Regional sources collectively broad but incomplete; public access varies; no universal rate | Add reviewed adapters separately; never copy derived unlicensed snapshots |
| Census TIGER, Gazetteer, GNIS | All location pipelines | `www2.census.gov/geo/`, TIGERweb queries; state/county/place references, bounds | Nationwide static; no key; public government geography | Use state navigation; never substitute centroid for asset location |
| OSM Overpass / Nominatim | All | `/api/interpreter`, `/search`; tags → candidate facilities/lines; cached geocoding | Broad, incomplete inventory; no key; public Nominatim ~1 req/sec, no autocomplete; ODbL attribution | Defer bulk extraction; reviewed caches only |
| HIFLD / DOE NETL | Gridsight, Common Ground | ArcGIS feature query / archives; transmission, plants, facilities | Nationwide static with gaps/vintage; no key for public services; verify service availability | Add bounded public infrastructure adapter; separate from projects |
| NWS | Common Ground | `api.weather.gov/alerts/active`, `/points/{lat},{lon}`, `/gridpoints/.../forecast/hourly`; GeoJSON and forecast periods | US service coverage incl AK/HI, not every point; no key; identifying User-Agent; free, unpublished rate limit | Implement cached alerts and site forecast |
| NOAA NCEI GHCN | Common Ground | `/access/services/search/v1/data`, `/access/services/data/v1`; station daily observations | National/global stations, uneven variables; no key for these access endpoints | Future historical replay with missing-day denominator |
| NOAA HURDAT2 / ATCF / NHC | Gridsight | NHC text track archives, a/b-deck gzip, active storm products | Basin-specific historical/live; no key | Future historical replay; no national damage claim |
| Iowa IEM ASOS | Gridsight | `mesonet.agron.iastate.edu/cgi-bin/request/asos.py`; CSV wind observations | Stations, not continuous coverage; no key | Calibration input only |
| EAGLE-I / ORNL Figshare | Gridsight | article API `24237376`, file byte ranges; county outage time series | Historical US, reporting gaps; archive, not live outage truth | Optional archive importer and Timescale later |
| HHS emPOWER | Gridsight | ArcGIS county beneficiary counts | US aggregate vulnerability; publication lag, no individual inference | Future county context, with vintage |
| USFS NLCD canopy | Gridsight | `.../USFS_EDW_NLCD_TCC_CONUS/ImageServer` | CONUS raster, not all states; no key | Future calibrated tree exposure |
| Open-Meteo historical weather | Gridsight | `archive-api.open-meteo.com/v1/archive` | Broad modeled/reanalysis data; free-use terms depend on use; not an observed station | Optional explicit modeled provider |
| USDA SSURGO SDA | Common Ground | `sdmdataaccess.nrcs.usda.gov/Tabular/post.rest`; fixed point-intersection SQL → map units/components/horizons | National survey with gaps; no key; not site soil test | Add after core; finite validated coordinates only |
| USGS NWIS | Common Ground | `waterservices.usgs.gov/nwis/iv/`; gauges and measurements | US gauge locations; no key; units and timestamps required | Add bounded river observations later |
| NOAA CO-OPS | Common Ground | station metadata + `api.prod/datagetter`; tides/water level | Coastal stations only; no key; datum/time zone matter | Regional adapter later |
| FEMA NFHL / FWS NWI | Common Ground, Gridsight wetlands | ArcGIS `/query`; flood zones and wetland polygons | National static coverage with missing surveys; no key | Bounded point/viewport context later, not engineering approval |
| WSDOT WZDx | Common Ground | `wzdx.wsdot.wa.gov/api/v4/WorkZoneFeed`; events/restrictions GeoJSON | Washington only; no key; version/freshness checks | Regional provider only; never national road-closure coverage |
| Google Routes | Common Ground | `routes.googleapis.com/directions/v2:computeRoutes` | Supported road network; `GOOGLE_ROUTES_API_KEY`, `GOOGLE_LVR_ENABLED`; billable/quota | Optional server routing, capability check for truck restrictions |
| OSRM demo | Common Ground, Gridsight | `/route/v1/driving`, `/table/v1/driving`; polylines/matrix | Car routes; demo limited/no SLA; Gridsight paces ≤1/sec | Do not use public demo for national production workloads |
| GA GEOS / SC DES permits | Atlas | ASP.NET application list, OCRM ArcGIS layer 0 | Fixed GA counties/SC coastal area; no key, brittle forms | Regional adapters later |
| Grants.gov | Gridsight | `api.grants.gov/v1/api` search/fetch; results validated against funding records | US programs; not project eligibility | Defer grant claims until verified |
| AlphaEarth satellite embeddings | Common Ground | GCS annual embeddings and Earth Engine catalog | Global static vector raster; access/processing cost varies | Experimental environmental context; not material tests |
| EIA-861, MISO cost guides, USDA land values, LBNL ICE | Gridsight, Atlas/Tandem cost models | ZIP/XLSX/PDF → utility averages and assumed cost ranges | Dataset-specific region/year; public data, not bids | Retain explicit assumptions; don't present savings as measured |
| OpenAI / Gemini / Anthropic | Atlas, Gridsight, Tandem, Common Ground, ours | Structured extraction, search, explanations; JSON validated against evidence | `OPENAI_API_KEY`, `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`; metered | Keep existing AI; no new paid calls during baseline implementation |
| Jev / TypeSafe / OpenRouter / Cloudflare | Tandem | typed `/systemone` decisions and hosted model routes | `TYPESAFE_API_KEY`, provider-specific credentials; account quotas | No requirement for deterministic geographic queries |
| ElevenLabs | Gridsight | speech/dialogue/signed agent sessions | `ELEVENLABS_API_KEY`, agent/voice IDs; metered | Defer voice; accessibility first |
| MongoDB Atlas / Tiger Timescale | Common Ground / Gridsight, Tandem | versioned collections/2dsphere; SQL outage buckets/event streams | `MONGODB_URI_RO/RW`, `MONGODB_DB`, `TIGER_DATABASE_URL`/`DATABASE_URL`; hosting costs | Do not force a DB migration yet |
| Mapbox / MapLibre / OpenFreeMap / OSM basemap | Atlas / other references | tiles/styles/glyphs + WebGL rendering | Mapbox public restricted token and usage billing; others service policy/attribution | Retain Leaflet, attributed raster tiles; vector tiles as scale warrants |

See official NWS API docs <https://www.weather.gov/documentation/services-web-api>, Census REST catalog <https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/State_County/MapServer>, DOE public infrastructure catalog <https://arcgis.netl.doe.gov/server/rest/services/Hosted/US_Power_Plants/FeatureServer>. Runtime failures are unavailable, never replaced by fixtures.

## 5. Unified architecture and models

Original filings / public services → provider adapters → validation and normalized records → bounded cache/index → explainable analysis → `/api/nation/*` → national map, list, evidence, timeline and coverage.

Shared Python dataclasses and documented JSON contracts:

- `GeoQuery`: WGS84 bbox (including antimeridian), optional state, text, zoom, limit, offset. National/regional/state/metro/corridor/point are scales, not fixed city coordinates.
- `Record`: stable provider-prefixed ID, kind (`project`, `infrastructure`, `hazard`), name, geometry/null, owner/null, state/null, confidence, date precision, properties, provenance. Geometry anchors are display positions only.
- `Provenance`: original source URL, provider, retrieved time, source update/vintage, evidence quality and coverage class (`nationwide_live`, `nationwide_static`, `regional`, `modeled`, `unavailable`).
- `ProviderResult`: available/partial/stale/unavailable, records, totals, truncation, issues, cache metadata. Unknown counts remain null.
- `Opportunity`: existing canonical saved match, policy version, distance method, schedule precision, source project IDs. Never invent opportunities for nearby existing assets.
- `Exposure`: geometric intersection with returned alert polygons; report missing polygons and incomplete provider data. Intersection means possible exposure, never predicted outage.

Backend stays Python. The local server gains read-only routes without weakening existing static-file restrictions. A provider registry supports additional regions without frontend schema changes. National view uses aggregate counts; local detail requests are bounded. Static canonical snapshots are validated on identity change. Live responses have TTL, stale fallback, retry cooldown, request coalescing, byte limits, allowlisted hosts and no redirect-following to arbitrary URLs.

## 6. Integration choices

| Feature / idea | Source | Value | Difficulty | Dependencies | National scalability | Recommendation | Target module |
|---|---|---|---|---|---|---|---|
| Provider envelopes + honest gaps | Common Ground | Prevents false all-clear | Medium | Python stdlib | High | Implement | `nation/models.py`, `providers.py` |
| Coverage-first national map | Common Ground | Immediate country/state/local understanding | Medium | Leaflet already used | High with bounded layers | Implement | `nationwide.*` |
| Confidence and evidence drawer | Atlas/Common Ground | Makes results auditable | Low | normalized source records | High | Implement | `nationwide.js` |
| Cached source adapters | Tandem | Limits requests; repeatable results | Medium | bounded transport/cache | High | Implement | `nation/transport.py` |
| Environmental context | Gridsight/Common Ground | Relates hazards to work | Medium | NWS polygons/forecasts | Broad official coverage | Implement | `nation/providers.py`, `analysis.py` |
| Indexed geometry queries | Tandem/Common Ground | Avoids raw national browser dumps | Medium | Shapely available | High | Implement | `nation/service.py` |
| Explainable ranking | Ours/Atlas | Keeps tier and evidence ahead of arbitrary score | Low | saved matches | High | Preserve | existing scoring + national detail links |
| Timeline precision | Atlas/Common Ground | Shows timing without invented days | Low | filed years | High | Implement histogram | `nationwide-model.js` |
| Arbitrary source ingestion | Tandem | Broadens future project inventory | High | reviewed parsers, source safety | Regional adapters | Stage separately | sibling pipeline |
| 3D time pillars/story | Common Ground | Strong presentation for dated national plans | High | MapLibre/Three, validated national dates | Requires LOD/instancing | Defer | future map renderer |
| GPU storm damage | Gridsight | Scenario research | Very high | network, calibration, hardware | Not validated nationally | Defer | future offline model |
| Voice/agent choreography | Gridsight/Tandem | Demo appeal | Medium | paid services | Cost/latency | Defer | optional assistant |
| Guaranteed savings/permit certainty | None supports it | Misleading | N/A | absent evidence | No | Reject | nowhere |

## 7. Performance, reliability and deployment

No nationwide raw-line download to the browser. Aggregate state/national metrics server-side; infrastructure detail only at local scales; cap records per response and show partial coverage. Abort outdated viewport requests and debounce navigation. Cache independently per source/query; cap memory entries and upstream concurrency; retain stale records with their original timestamp after transient failures, for a bounded period. Provider failures must not hide canonical projects. Lists remain available when map tiles fail. Missing geometry remains visible in catalog counts.

Initial deployment stays the local same-origin server (`python -m analyst.server`). External/public production deployment needs a production HTTP server, shared cache/rate budget, observability and load testing; this change does not publish a site. No new cloud accounts or database required. Initial backend dependencies use the existing Shapely installation and standard library. Leaflet version remains pinned. Environment: existing analyst settings retained; optional identifying `NWS_USER_AGENT`; national offline switch for reproducible tests. No new paid keys required.

## 8. Licensing and risks

None of the four reference roots has a project LICENSE/COPYING grant at the inspected commits. Bundled skills' license files are not licenses for the application. Treat source implementations, branded artwork and derived datasets as research only. Independently implement techniques, document inspiration, and acquire public datasets directly with source attribution. No reference code or snapshots enter product runtime. A later reuse request needs an explicit license grant. Maintain `ATTRIBUTION.md`.

Risks: upstream schemas/services change; static inventories have lag; alerts may have null geometry; bbox coverage is not a state polygon; incomplete data can bias ranking; state totals are not project totals; public endpoint quotas aren't SLAs; fixed regional projections do not generalize; references' README counts are historical claims rather than independently reproduced results. Automated URL scans cannot prove integration behavior. Every enabled adapter gets source-specific tests and a live smoke check where reachable.

## 9. Implementation phases and acceptance

1. Research, capability matrix, source/algorithm/visual inventory, license findings, baseline tests (this document before implementation).
2. Shared normalized models, geographic validation, bounded transport/cache, regional canonical adapter and provider registry. Test invalid coordinates, duplicate queries, missing values, cache expiry, failure isolation.
3. Primary-source nationwide geography/infrastructure and NWS adapters. Test normalization, service limits, timestamps, out-of-coverage and zero vs unknown counts; live-smoke approved public endpoints.
4. National explorer with state/local navigation, layer toggles, aggregate map, detail list, provenance, forecast, timeline and saved regional opportunity links. Check responsive desktop/mobile and network failure behavior.
5. Explainable hazard intersection, bounded exports, query cancellation, diagnostics, regression suite, documentation and implementation status.
6. Subsequent source expansion: reviewed ISO/RTO filing adapters, interval-aware nationwide candidate generation, historical weather replay, vector tiles/shared DB when measured volumes justify them. These require source-specific acquisition and validation; do not label them delivered with the first platform release.

After each major implemented phase, run Python/JS checks, exercise the HTTP app and inspect the UI. Keep changes additive and reviewable; do not commit, deploy or alter reference checkouts as part of implementation. The architecture supports countrywide exploration while the UI states exactly which datasets are actually available.
