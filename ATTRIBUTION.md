# Sources and design research

Gridlock's existing canonical dataset retains its original publisher citations and integrity receipts.

Research repositories inspected on 2026-10-06:

- [Gridlock Atlas](https://github.com/Raamia/gridlock-atlas), `05e1c82`: claim provenance, date intervals, geographic confidence.
- [Gridsight / Mr.Gridy](https://github.com/VelvetDragon/gridsight), `e9bf707`: separating environmental observations from modeled outcomes.
- [shellhacks26 / UtiliTies](https://github.com/AlexWS12/shellhacks26), `5de6ee1`: provider boundaries, indexed queries, cached evidence.
- [Common Ground](https://github.com/fradicus/Shellhacks-2026), `26b3b70`: geographic scopes, visual evidence, source coverage and provider failure envelopes.

No root application license was found in these four checkouts. The project owner confirmed on 2026-10-06 that the authors agreed at ShellHacks to open-source sharing and reuse for this integration. We rely on that stated permission and retain repository attribution. The exact public redistribution license is not specified in the checkouts; this document does not invent one.

The national catalog is adapted from Common Ground's validated, assembled release using its own read-only release loader and candidate matcher during import. The import receipt pins the Git revision and hashes. Original source IDs, source links, review states and evidence are retained. Legacy DESC/GPC projections are excluded so our existing canonical catalog remains authoritative for those records. This is a static imported snapshot, not a live connection or a new independent location review. OSM-derived location candidates retain their original attribution and review limitations. Runtime code does not require the reference checkout.

Runtime data sources are linked on each record. Live weather comes from the [National Weather Service](https://www.weather.gov/documentation/services-web-api). Reference state geography comes from [U.S. Census TIGERweb](https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/State_County/MapServer). USDA SSURGO and the FWS National Wetlands Inventory supply independent point context. DOE NETL/HIFLD were researched but are not a separate delivered live infrastructure layer.

Map rendering uses Leaflet (BSD-2-Clause) and optional MapLibre GL JS 5.11.0 (BSD-3-Clause); upstream copyright/license notices remain in the pinned distributions. Basemap tiles display their provider and OpenStreetMap attribution. OpenStreetMap data is available under the ODbL; see https://www.openstreetmap.org/copyright. No reference repository is a runtime dependency.

The historical lab imports Common Ground's NOAA NCEI GHCN-Daily archive at the same pinned revision: 1,979 stations, 2016–2025. `scripts/import_weather.py` validates daily array lengths and finite observations, recomputes completeness, and records station and archive hashes. Original NOAA source URLs, hashes, units and retrieval dates stay in each station record. Source: [NOAA GHCN-Daily](https://www.ncei.noaa.gov/products/land-based-station/global-historical-climatology-network-daily). These are archived station observations, not generated demo weather. The selector adapts Common Ground's 30-mile rain / 60-mile wind and 95% completeness rules. The independently implemented replay excludes incomplete trials rather than assuming missing weather permits work.

The time lens adapts Common Ground's date-height / precision-span visual idea using MapLibre extrusions and a bounded viewport, without copying its Three.js renderer. Milestone interval comparisons independently implement Atlas's uncertainty principle. Scenario outcomes retain Gridsight's separation between observations, assumptions and predictions; provider isolation and caching follow the architecture researched in UtiliTies.
