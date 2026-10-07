/* National intelligence: one normalized API, independent of provider response formats. */
(() => {
  "use strict";
  const M = window.NationModel,
    $ = (id) => document.getElementById(id),
    e = M.esc;
  const fmt = (n) => Number(n).toLocaleString("en-US");
  const initialDetail = $("detail").innerHTML;
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const state = {
    geography: null,
    tab: "projects",
    year: "",
    offset: 0,
    selected: null,
    query: null,
    records: [],
    alerts: null,
  };
  let map,
    projectLayer,
    alertLayer,
    selectionLayer,
    controller,
    refreshTimer,
    detailVersion = 0,
    requestVersion = 0;
  const colors = {
    verified: "#a6d6c5",
    official: "#81b7dc",
    tentative: "#e8ba7a",
    unresolved: "#91a5ab",
  };
  const regions = {
    conus: [
      [24, -125],
      [50, -66],
    ],
    alaska: [
      [51, -180],
      [72, -130],
    ],
    hawaii: [
      [18.8, -160.5],
      [22.5, -154.5],
    ],
  };
  const badge = (r) =>
    `<span class="badge ${e(r.confidence)}">${e(M.confidenceLabel(r.confidence))}</span>`;
  const sourceLink = (url, label = "Open original source ↗") =>
    M.safeUrl(url)
      ? `<a class="source-link" href="${e(M.safeUrl(url))}" target="_blank" rel="noopener noreferrer">${e(label)}</a>`
      : "<p>Source URL not published.</p>";
  async function api(path, signal) {
    const r = await fetch("/api/nation/" + path, { signal });
    const data = await r.json();
    if (!r.ok) throw new Error(data.error || "Request failed.");
    return data;
  }
  function debounce() {
    clearTimeout(refreshTimer);
    refreshTimer = setTimeout(() => {
      state.offset = 0;
      refresh();
    }, 220);
  }
  function params() {
    const p = new URLSearchParams({
      status: $("status").value,
      limit: "60",
      zoom: String(Math.floor(map?.getZoom() || 3)),
    });
    for (const [key, id] of [
      ["state", "state"],
      ["text", "search"],
      ["confidence", "confidence"],
    ])
      if ($(id).value) p.set(key, $(id).value);
    if (state.year) p.set("year", state.year);
    if (map && $("viewport").checked) {
      const b = map.getBounds();
      p.set(
        "bbox",
        M.viewport({
          west: b.getWest(),
          south: b.getSouth(),
          east: b.getEast(),
          north: b.getNorth(),
        }),
      );
    }
    return p;
  }
  function initMap() {
    if (!window.L) {
      $("map").innerHTML =
        '<p class="empty">Map library unavailable. Search, records and evidence remain available.</p>';
      return;
    }
    map = L.map("map", {
      preferCanvas: true,
      zoomControl: true,
      minZoom: 2,
      maxZoom: 17,
    }).setView([38.5, -97], 4);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      maxZoom: 19,
      className: "basemap-tiles",
    })
      .addTo(map)
      .on("tileerror", () => {
        $("mapNotice").textContent =
          "Some basemap tiles are unavailable. Project overlays and the catalog still work.";
      });
    projectLayer = L.layerGroup().addTo(map);
    alertLayer = L.layerGroup();
    selectionLayer = L.layerGroup().addTo(map);
    map.on("moveend", () => {
      if (map.getZoom() >= 7) $("viewport").checked = true;
      debounce();
    });
    map.on("click", (event) => showSite(event.latlng.lng, event.latlng.lat));
    map.fitBounds(regions.conus, { animate: false });
  }
  function drawProjects(data) {
    if (!map) return;
    projectLayer.clearLayers();
    for (const f of data.map.features) {
      if (f.properties.cluster) {
        const count = f.properties.count,
          size = 30 + Math.min(26, Math.log2(count + 1) * 3);
        const marker = L.marker(
          [f.geometry.coordinates[1], f.geometry.coordinates[0]],
          {
            icon: L.divIcon({
              className: "cluster-icon",
              html: `<div class="cluster">${fmt(count)}</div>`,
              iconSize: [size, size],
            }),
          },
        );
        marker.bindTooltip(
          `${fmt(count)} located filing records · click to zoom`,
        );
        marker.on("click", () => {
          $("viewport").checked = true;
          map.setView(marker.getLatLng(), Math.min(map.getZoom() + 2, 10), {
            animate: !reduced,
          });
        });
        projectLayer.addLayer(marker);
      } else {
        const c = f.properties.confidence;
        const layer = L.geoJSON(f, {
          bubblingMouseEvents: false,
          style: {
            color: colors[c],
            weight: 2.5,
            dashArray: c === "tentative" ? "5 5" : null,
          },
          pointToLayer: (feature, latlng) =>
            L.circleMarker(latlng, {
              bubblingMouseEvents: false,
              radius: 5,
              color: colors[c],
              weight: 1.5,
              fillColor: colors[c],
              fillOpacity: c === "tentative" ? 0.1 : 0.8,
            }),
        });
        layer.bindTooltip(e(f.properties.name));
        layer.on("click", (ev) => {
          L.DomEvent.stopPropagation(ev);
          select(f.properties.id);
        });
        projectLayer.addLayer(layer);
      }
    }
    $("mapScale").textContent =
      map.getZoom() < 7 ? "Aggregated overview" : "Individual records";
    $("mapNotice").textContent = data.map_truncated
      ? "Map capped at 800 features. Enable “Limit records to map area” and zoom closer."
      : `${fmt(data.mapped)} located / ${fmt(data.total)} filtered records. ${data.scope_note} ${map.getZoom() < 7 ? "Click a group to explore." : "Hollow markers indicate tentative locations."}`;
  }
  function timeline(data) {
    const entries = Object.entries(data.summary.years).filter(([y]) =>
      /^\d{4}$/.test(y),
    );
    const max = Math.max(1, ...entries.map(([, n]) => n));
    $("timeline").innerHTML =
      entries
        .map(
          ([y, n]) =>
            `<button class="year-bar ${state.year === y ? "active" : ""}" style="--height:${Math.max(3, (n / max) * 48)}px" title="${e(y)}: ${fmt(n)} records" aria-label="Filter to ${e(y)}, ${fmt(n)} records" data-year="${e(y)}"><span>${e(y)}</span></button>`,
        )
        .join("") ||
      '<span class="empty">No filed dates in this selection.</span>';
    $("unknownDates").textContent =
      `${fmt(data.summary.years.Unknown || 0)} records have no usable filed in-service date. ${state.year ? "Showing " + state.year + "." : ""}`;
    $("clearYear").hidden = !state.year;
    $("timeline")
      .querySelectorAll("[data-year]")
      .forEach(
        (b) =>
          (b.onclick = () => {
            state.year = b.dataset.year;
            debounce();
          }),
      );
  }
  function recordRow(r) {
    return `<button class="record ${state.selected === r.id ? "selected" : ""}" data-project="${e(r.id)}"><strong>${e(r.name)}</strong><small>${e(r.owner || "Owner unknown")} · ${e(r.milestone.value || "Date unknown")}</small>${badge(r)}</button>`;
  }
  function pairRow(p) {
    return `<button class="record" data-pair="${e(p.a)}" data-other="${e(p.b)}"><strong>${e(p.a_name)}<br>↔ ${e(p.b_name)}</strong><small>${fmt(p.distance_km)} km · ${p.method === "closest_geometry" ? "closest geometry" : "straight-line centers"}</small><span class="badge">${p.classification === "provisional" ? "Provisional candidate" : "Regional opportunity"}</span></button>`;
  }
  function bindRows() {
    $("results")
      .querySelectorAll("[data-project]")
      .forEach((b) => (b.onclick = () => select(b.dataset.project)));
    $("results")
      .querySelectorAll("[data-pair]")
      .forEach(
        (b) => (b.onclick = () => select(b.dataset.pair, b.dataset.other)),
      );
  }
  async function refresh(append = false) {
    controller?.abort();
    controller = new AbortController();
    const seq = ++requestVersion;
    if (state.tab === "alerts") {
      await showAlerts();
      return;
    }
    const p = params();
    p.set("offset", String(state.offset));
    state.query = p;
    $("resultMeta").textContent = "Querying source-backed records…";
    $("more").disabled = true;
    try {
      const data = await api(`projects?${p}`, controller.signal);
      if (seq !== requestVersion) return;
      drawProjects(data);
      timeline(data);
      if (state.tab === "pairs") {
        const pairs = await api(`pairs?${p}`, controller.signal);
        if (seq !== requestVersion) return;
        $("results").innerHTML =
          (append ? $("results").innerHTML : "") +
          pairs.records.map(pairRow).join("");
        $("resultMeta").textContent =
          `${fmt(pairs.total)} pairs within both sides of the filter. National pairs remain provisional.`;
        $("more").hidden = pairs.next_offset === null;
        $("more").dataset.next = pairs.next_offset;
        if (!pairs.total)
          $("results").innerHTML =
            '<p class="empty">No saved pairs in this scope. Broaden the filters. Missing pairs do not prove that coordination is impossible.</p>';
      } else {
        state.records = append
          ? state.records.concat(data.records)
          : data.records;
        $("results").innerHTML = state.records.map(recordRow).join("");
        $("resultMeta").textContent =
          `${fmt(data.total)} records · ${fmt(data.mapped)} located. ${data.scope_note}`;
        $("more").hidden = data.next_offset === null;
        $("more").dataset.next = data.next_offset;
        if (!data.total)
          $("results").innerHTML =
            '<p class="empty">No imported records match these filters. This is a coverage gap, not proof that no projects exist.</p>';
      }
      bindRows();
      $("scopeLabel").textContent =
        state.geography?.states.find((s) => s.state_fips === $("state").value)
          ?.name || "United States";
    } catch (err) {
      if (err.name !== "AbortError") {
        $("resultMeta").textContent = "Could not load this selection.";
        $("results").innerHTML =
          `<p class="empty error">${e(err.message)} <a href="index.html?view=radar">Open regional radar ↗</a></p>`;
        $("more").hidden = true;
      }
    } finally {
      if (seq === requestVersion) $("more").disabled = false;
    }
  }
  function anchor(record) {
    const g = record.geometry;
    if (!g) return null;
    return g.type === "Point"
      ? g.coordinates
      : g.type === "LineString"
        ? g.coordinates[0]
        : g.type === "MultiLineString"
          ? g.coordinates[0][0]
          : null;
  }
  async function select(id, other) {
    const version = ++detailVersion;
    state.selected = id;
    $("detail").innerHTML = '<p class="empty">Loading filing evidence…</p>';
    try {
      const data = await api("project?" + new URLSearchParams({ id }));
      if (version !== detailVersion) return;
      const r = data.record,
        p = r.provenance,
        d = r.detail;
      let second = null;
      if (other) {
        second = (await api("project?" + new URLSearchParams({ id: other })))
          .record;
        if (version !== detailVersion) return;
      }
      $("detail").innerHTML =
        `<div class="pulse"><span class="eyebrow">${p.provider === "canonical" ? "GRIDLOCK CANONICAL" : "NATIONAL FILING RECORD"}</span><h2>${e(r.name)}</h2>${badge(r)}<div class="fact-grid"><div><label>Owner</label><strong>${e(r.owner || "Unknown")}</strong></div><div><label>Status</label><strong>${e(r.status.replaceAll("_", " "))}</strong></div><div><label>Filed milestone</label><strong>${e(M.dateLabel(r.milestone))}</strong></div><div><label>Planning region</label><strong>${e(r.planning_region || "Unknown")}</strong></div></div><p>${e(d.description || d.geometry_notes || d.status_text || "See the source filing for the project description.")}</p>${sourceLink(p.source_url)}<p>Publisher: ${e(p.publisher || "Unknown")}<br>Source retrieved: ${e((p.retrieved_at || "Unknown").slice(0, 10))}<br>Source page / sheet / row: ${e(d.evidence?.page ?? d.source_metadata?.source_page ?? "—")} / ${e(d.evidence?.sheet ?? "—")} / ${e(d.evidence?.row ?? "—")}</p><div class="note">${e(d.limitation)}<br>${e(d.geography_basis || "Geographic membership not stated.")}<br>Reviewed means reviewed in the originating dataset; it is not a new field survey.</div><h3>Nearby work & next action</h3><div id="relatedPairs"></div>${data.pairs_truncated ? "<p>First 50 related pairs shown.</p>" : ""}${anchor(r) ? '<h3>Worksite context</h3><p>Inspect weather, survey soils and wetlands at this record’s display point. For a line, this samples its first point, not the full corridor.</p><button id="loadContext">Inspect sampled point ↗</button><div id="siteContext"></div>' : "<p>No eligible location: worksite context is unavailable.</p>"}<details><summary>Source evidence & location method</summary><pre>${e(JSON.stringify({ location_review: d.location_review, location_candidate: d.location_candidate, location_verification: d.location_verification, evidence: d.evidence, geometry_method: d.geometry_method, geometry_notes: d.geometry_notes, date_raw: d.date_raw }, null, 2))}</pre></details></div>`;
      if (d.date_issue)
        $("detail").insertAdjacentHTML(
          "beforeend",
          `<p class="note">${e(d.date_issue)}</p><pre>${e(JSON.stringify(d.source_milestone, null, 2))}</pre>`,
        );
      if (second) {
        const gap = PlanningModel.compare(r.milestone, second.milestone);
        $("relatedPairs").insertAdjacentHTML(
          "beforebegin",
          `<div class="note"><b>Milestone interval comparison</b><p>${gap ? `Possible separation: ${fmt(gap.min)}–${fmt(gap.max)} days, using each filing’s date precision. ${gap.overlaps ? "The filed intervals overlap." : "The filed intervals do not overlap."}` : "At least one filed date is unknown; temporal proximity cannot be determined."} These are milestone intervals, not construction windows or proof of coordinated work.</p></div>`,
        );
      }
      if (anchor(r)) {
        $("loadContext").insertAdjacentHTML(
          "afterend",
          '<button id="planWeather" class="planning-launch">Historical work-window lab ↗</button>',
        );
        $("planWeather").onclick = () =>
          WeatherPlanner.open(...anchor(r), r.name);
      }
      $("relatedPairs").innerHTML =
        data.pairs
          .map(
            (pair) =>
              `<button class="record" data-neighbor="${e(pair.a === id ? pair.b : pair.a)}"><strong>${e(pair.a === id ? pair.b_name : pair.a_name)}</strong><small>${fmt(pair.distance_km)} km · ${e(pair.method.replaceAll("_", " "))}<br>${pair.time_gap_days === null ? "Exact day gap unknown" : fmt(pair.time_gap_days) + " days between filed milestones"}${pair.timeline_gap_years !== undefined ? "<br>Schedule gap: " + pair.timeline_gap_years + " years" : ""}</small><span class="badge">${pair.classification === "provisional" ? "Provisional candidate" : "Regional opportunity"}</span></button>`,
          )
          .join("") ||
        "<p>No saved nearby pair for this record. Check location and ownership evidence before expanding the search.</p>";
      $("relatedPairs")
        .querySelectorAll("[data-neighbor]")
        .forEach((b) => (b.onclick = () => select(b.dataset.neighbor, id)));
      if ($("loadContext"))
        $("loadContext").onclick = () => {
          const a = anchor(r);
          loadContext(a[0], a[1], version, r.id);
        };
      if (map && r.geometry) {
        selectionLayer.clearLayers();
        const g = L.geoJSON(r.geometry, {
          style: { color: "#fff0ba", weight: 4 },
          pointToLayer: (f, ll) =>
            L.circleMarker(ll, {
              radius: 11,
              color: "#fff0ba",
              weight: 2,
              fillOpacity: 0.15,
            }),
        }).addTo(selectionLayer);
        if (second?.geometry) {
          L.geoJSON(second.geometry, {
            pointToLayer: (f, ll) =>
              L.circleMarker(ll, { radius: 10, color: "#81b7dc" }),
          }).addTo(g);
          const a = anchor(r),
            b = anchor(second);
          L.polyline(
            [
              [a[1], a[0]],
              [b[1], b[0]],
            ],
            { color: "#fff0ba", dashArray: "5 7", weight: 2 },
          )
            .bindTooltip("Display connector; not a driving route.")
            .addTo(selectionLayer);
        }
        map.fitBounds(g.getBounds().pad(0.5), {
          maxZoom: 10,
          animate: !reduced,
        });
      }
    } catch (err) {
      if (version === detailVersion)
        $("detail").innerHTML = `<p class="empty error">${e(err.message)}</p>`;
    }
  }
  function showSite(lon, lat) {
    const version = ++detailVersion;
    $("detail").innerHTML =
      `<span class="eyebrow">LOCATION CONTEXT</span><h2>Inspect this location.</h2><p>${lat.toFixed(4)}, ${lon.toFixed(4)}</p><p>Point context from independent public providers. Clicking the map does not create an asset or assign a project location.</p><button id="loadContext">Load public site context ↗</button><div id="siteContext"></div>`;
    $("loadContext").onclick = () => loadContext(lon, lat, version);
    $("loadContext").insertAdjacentHTML(
      "afterend",
      '<button id="planWeather" class="planning-launch">Historical work-window lab ↗</button>',
    );
    $("planWeather").onclick = () =>
      WeatherPlanner.open(lon, lat, "Selected map point");
  }
  async function loadContext(lon, lat, version, id) {
    $("loadContext").disabled = true;
    const ids = [
      "nws-forecast",
      "ssurgo",
      "wetlands",
      ...(id ? ["exposure"] : []),
    ];
    $("siteContext").innerHTML = ids
      .map(
        (p) =>
          `<section class="provider" id="provider-${p}"><strong>${e(p)}</strong><span class="status">loading</span></section>`,
      )
      .join("");
    await Promise.all(
      ids.map(async (provider) => {
        try {
          const query =
            provider === "exposure"
              ? "exposure?" + new URLSearchParams({ id })
              : "site?" + new URLSearchParams({ provider, lon, lat });
          const data = await api(query);
          if (version !== detailVersion) return;
          const el = $("provider-" + provider);
          if (!el) return;
          el.innerHTML = `<strong>${e(provider)}</strong><span class="status">${e(data.status)}</span><p>${e((data.limitations || []).join(" "))}</p><p>Retrieved: ${e(data.retrieved_at || "Unavailable")}</p>`;
          if (data.periods)
            el.innerHTML += data.periods
              .slice(0, 12)
              .map(
                (p) =>
                  `<div class="forecast-row"><span>${e(new Date(p.start).toLocaleString("en-US", { hour: "numeric", weekday: "short" }))}</span><b>${e(p.temperature ?? "—")}°${e(p.unit || "")}</b><span>${e(p.wind || "—")}</span></div>`,
              )
              .join("");
          else if (data.records?.length)
            el.innerHTML += data.records
              .slice(0, 10)
              .map(
                (r) =>
                  `<p>${e(r.name || r.muname || r.WETLAND_TYPE || "Mapped feature")}${r.compname ? " · " + e(r.compname) : ""}${r.drainagecl ? " · " + e(r.drainagecl) : ""}</p>`,
              )
              .join("");
          else if (data.status === "available")
            el.innerHTML +=
              "<p>No returned intersection/records. Coverage limitations still apply.</p>";
          if (data.source_url)
            el.innerHTML += sourceLink(data.source_url, "Provider source ↗");
        } catch (err) {
          if (version === detailVersion && $("provider-" + provider))
            $("provider-" + provider).innerHTML =
              `<strong>${e(provider)}</strong><p class="error">${e(err.message)}</p>`;
        }
      }),
    );
    if (version === detailVersion && $("loadContext"))
      $("loadContext").disabled = false;
  }
  async function ensureAlerts() {
    if (!state.alerts || Date.now() - state.alertsLoaded >= 180000) {
      try {
        state.alerts = await api("alerts");
      } catch (err) {
        alertLayer?.clearLayers();
        state.alerts = null;
        throw err;
      }
      state.alertsLoaded = Date.now();
    }
    const data = M.activeAlerts(state.alerts);
    state.alerts = data;
    if (map) {
      alertLayer.clearLayers();
      for (const r of data.records || [])
        if (r.geometry)
          L.geoJSON(r.geometry, {
            bubblingMouseEvents: false,
            style: { color: "#df916d", weight: 1, fillOpacity: 0.12 },
          })
            .bindTooltip(e(r.name))
            .on("click", () => alertDetail(r))
            .addTo(alertLayer);
    }
    return data;
  }
  function alertDetail(r) {
    detailVersion++;
    $("detail").innerHTML =
      `<span class="eyebrow">NATIONAL WEATHER SERVICE</span><h2>${e(r.name)}</h2><span class="badge">${e(r.severity)} · ${e(r.certainty)}</span><p>${e(r.headline)}</p><p>${e(r.area)}</p><h3>Official alert</h3><p>${e(r.description)}</p><h3>Instructions from NWS</h3><p>${e(r.instruction || "No instruction supplied.")}</p><p>Expires: ${e(r.expires)}</p>${sourceLink(r.provenance.source_url)}<div class="note">${r.geometry ? "Polygon available." : "No polygon supplied. This alert is not drawn on the map."} This is a weather alert, not a grid-outage prediction.</div>`;
  }
  async function showAlerts() {
    $("resultMeta").textContent = "Loading official NWS alerts…";
    $("more").hidden = true;
    try {
      const data = await ensureAlerts();
      if (state.tab !== "alerts") return;
      $("resultMeta").textContent =
        `NWS: ${data.status} · ${fmt((data.records || []).length)} returned alerts nationwide${data.truncated ? " · partial feed" : ""}. Retrieved ${data.retrieved_at || "unknown"}. Project filters do not apply.`;
      $("results").innerHTML =
        (data.records || [])
          .map(
            (r, i) =>
              `<button class="record" data-alert="${i}"><strong>${e(r.name)}</strong><small>${e(r.area)}</small><span class="badge">${e(r.severity)}${r.geometry ? "" : " · no polygon"}</span></button>`,
          )
          .join("") ||
        `<p class="empty">${data.status === "available" ? "No active alerts returned." : e((data.limitations || []).join(" "))}</p>`;
      $("results")
        .querySelectorAll("[data-alert]")
        .forEach(
          (b) =>
            (b.onclick = () =>
              alertDetail(data.records[Number(b.dataset.alert)])),
        );
    } catch (err) {
      if (state.tab === "alerts")
        $("results").innerHTML = `<p class="empty error">${e(err.message)}</p>`;
    }
  }
  function fitScope() {
    if (!map) return;
    const s = state.geography?.states.find(
      (s) => s.state_fips === $("state").value,
    );
    map.fitBounds(
      s
        ? [
            [s.bounds.south, s.bounds.fit_west],
            [s.bounds.north, s.bounds.fit_east_unwrapped],
          ]
        : regions.conus,
      { animate: !reduced },
    );
  }
  async function localAreas() {
    const code = $("state").value;
    $("areaControl").hidden = !code;
    if (!code) {
      state.areas = [];
      return;
    }
    $("area").innerHTML = '<option value="">Loading local areas…</option>';
    try {
      const data = await api("areas?" + new URLSearchParams({ state: code }));
      if ($("state").value !== code) return;
      state.areas = data.areas;
      $("area").innerHTML =
        '<option value="">Choose a local area</option>' +
        data.areas
          .map(
            (a) =>
              `<option value="${e(a.county_geoid)}">${e(a.full_name)}</option>`,
          )
          .join("");
    } catch {
      if ($("state").value === code)
        $("area").innerHTML =
          '<option value="">Local areas unavailable</option>';
    }
  }
  function coverage() {
    const g = state.geography;
    if (!g) return;
    $("coverageContent").innerHTML =
      `<p>${e(g.limitations.join(" "))}</p><p>Reference revision: ${e(g.receipt.reference.commit.slice(0, 12))}. Snapshot imported ${e(g.receipt.imported_at)}. The catalog is static; live context has independent timestamps.</p><table class="coverage-table"><thead><tr><th>Provider</th><th>Coverage class</th><th>Scope</th></tr></thead><tbody>${g.providers.map((p) => `<tr><td>${e(p.name)}</td><td>${e(p.coverage)}</td><td>${e(p.scope)}</td></tr>`).join("")}</tbody></table><h3>Imported filing records by state</h3><p>Multi-state records appear in each listed state. Zero means no imported records, not no infrastructure.</p><table class="coverage-table"><thead><tr><th>State</th><th>Records</th></tr></thead><tbody>${g.states.map((s) => `<tr><td><button class="text-button" data-state="${e(s.state_fips)}">${e(s.name)} ↗</button></td><td>${fmt(s.record_count)}</td></tr>`).join("")}</tbody></table><p>Research and imported data: <a href="https://github.com/fradicus/Shellhacks-2026" target="_blank" rel="noopener">Common Ground</a>; architecture and techniques informed by Gridlock Atlas, Gridsight and UtiliTies. Author reuse permission confirmed by the project owner. See the repository attribution and integration plan.</p>`;
    $("coverageContent")
      .querySelectorAll("[data-state]")
      .forEach(
        (b) =>
          (b.onclick = () => {
            $("state").value = b.dataset.state;
            $("coverageDialog").close();
            state.year = "";
            $("viewport").checked = false;
            localAreas();
            fitScope();
            debounce();
          }),
      );
    $("coverageDialog").showModal();
  }
  async function exportRows() {
    const button = $("export");
    button.disabled = true;
    try {
      const p = params();
      p.set("limit", "200");
      let records = [],
        offset = 0,
        dataset;
      while (records.length < 2000) {
        p.set("offset", offset);
        const data = await api("projects?" + p);
        if (dataset && dataset !== data.dataset)
          throw new Error(
            "Dataset changed during export. Retry for a coherent snapshot.",
          );
        dataset = data.dataset;
        records.push(...data.records);
        if (data.next_offset === null) break;
        offset = data.next_offset;
      }
      const url = URL.createObjectURL(
        new Blob([M.csv(records)], { type: "text/csv;charset=utf-8" }),
      );
      const a = document.createElement("a");
      a.href = url;
      a.download = "gridlock-filings.csv";
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      $("resultMeta").textContent =
        `Exported ${fmt(records.length)} records${records.length === 2000 ? " (export cap; narrow filters for more)" : ""}. Source URLs and confidence included.`;
    } catch (err) {
      $("resultMeta").textContent = err.message;
    } finally {
      button.disabled = false;
    }
  }
  async function boot() {
    initMap();
    let alertsRefreshing = false;
    async function refreshVisibleAlerts() {
      if (
        document.hidden ||
        alertsRefreshing ||
        (!$("alertLayer").checked && state.tab !== "alerts")
      )
        return;
      alertsRefreshing = true;
      try {
        if (state.tab === "alerts") await showAlerts();
        else {
          const data = await ensureAlerts();
          $("mapNotice").textContent =
            `NWS ${data.status} · retrieved ${data.retrieved_at || "unknown"}. Expired alerts removed; feed refreshes every three minutes.`;
        }
      } catch {
        alertLayer?.clearLayers();
        state.alerts = null;
        $("mapNotice").textContent =
          "NWS refresh unavailable; alert overlay cleared. This is not an all-clear.";
      } finally {
        alertsRefreshing = false;
      }
    }
    setInterval(refreshVisibleAlerts, 15000);
    document.addEventListener("visibilitychange", refreshVisibleAlerts);
    $("search").oninput = debounce;
    for (const id of ["status", "confidence", "viewport"])
      $(id).onchange = debounce;
    $("state").onchange = () => {
      state.year = "";
      $("viewport").checked = false;
      localAreas();
      fitScope();
      debounce();
    };
    $("area").onchange = () => {
      const a = state.areas?.find((a) => a.county_geoid === $("area").value);
      if (!a || !map) return;
      $("viewport").checked = true;
      map.fitBounds(
        [
          [a.bounds.south, a.bounds.fit_west],
          [a.bounds.north, a.bounds.fit_east_unwrapped],
        ],
        { animate: !reduced },
      );
      debounce();
    };
    $("fit").onclick = fitScope;
    $("timeLens").onclick = () =>
      TimeLens.open({ query: params(), bounds: map?.getBounds(), select });
    document.querySelectorAll("[data-region]").forEach(
      (b) =>
        (b.onclick = () => {
          $("state").value = { conus: "", alaska: "02", hawaii: "15" }[
            b.dataset.region
          ];
          state.year = "";
          $("viewport").checked = false;
          localAreas();
          map?.fitBounds(regions[b.dataset.region], { animate: !reduced });
          debounce();
        }),
    );
    $("clearYear").onclick = () => {
      state.year = "";
      debounce();
    };
    $("reset").onclick = () => {
      $("state").value = "";
      $("search").value = "";
      $("status").value = "active";
      $("confidence").value = "";
      $("viewport").checked = false;
      state.year = "";
      state.offset = 0;
      state.selected = null;
      detailVersion++;
      selectionLayer?.clearLayers();
      $("detail").innerHTML = initialDetail;
      localAreas();
      fitScope();
      debounce();
    };
    document.querySelectorAll("[data-tab]").forEach(
      (b) =>
        (b.onclick = () => {
          state.tab = b.dataset.tab;
          state.offset = 0;
          document
            .querySelectorAll("[data-tab]")
            .forEach((t) => t.setAttribute("aria-selected", String(t === b)));
          refresh();
        }),
    );
    $("more").onclick = () => {
      state.offset = Number($("more").dataset.next);
      refresh(true);
    };
    $("projectLayer").onchange = () => {
      if (map)
        $("projectLayer").checked
          ? map.addLayer(projectLayer)
          : map.removeLayer(projectLayer);
    };
    $("alertLayer").onchange = async () => {
      if (!map) return;
      if ($("alertLayer").checked) {
        $("mapNotice").textContent = "Loading NWS polygons…";
        try {
          const r = await ensureAlerts();
          if ($("alertLayer").checked) map.addLayer(alertLayer);
          $("mapNotice").textContent =
            `NWS ${r.status}: ${(r.records || []).filter((a) => a.geometry).length} polygons. Alerts without polygons remain in the Alerts list.${r.truncated ? " Partial feed." : ""}`;
        } catch (err) {
          $("mapNotice").textContent = err.message;
        }
      } else map.removeLayer(alertLayer);
    };
    $("coverageButton").onclick = coverage;
    $("closeCoverage").onclick = () => $("coverageDialog").close();
    $("export").onclick = exportRows;
    try {
      const g = await api("geography");
      state.geography = g;
      $("state").innerHTML =
        '<option value="">United States · all states</option>' +
        g.states
          .map(
            (s) =>
              `<option value="${e(s.state_fips)}">${e(s.name)} · ${fmt(s.record_count)}</option>`,
          )
          .join("");
      for (const [id, key] of [
        ["totalCount", "records"],
        ["mappedCount", "mapped"],
        ["pairCount", "candidates"],
        ["opportunityCount", "opportunities"],
      ])
        $(id).textContent = fmt(g.counts[key]);
      $("datasetNote").textContent =
        `${fmt(g.counts.sources)} source groups · imported ${new Date(g.receipt.imported_at).toLocaleDateString()} · static filing evidence, not a live construction census. Live provider status is reported separately.`;
      await refresh();
    } catch (err) {
      $("resultMeta").textContent = "National catalog unavailable.";
      $("results").innerHTML =
        `<p class="empty error">${e(err.message)} Run this page through the Gridlock server. <a href="index.html">Regional tools ↗</a></p>`;
    }
  }
  boot();
})();
