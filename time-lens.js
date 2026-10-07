/* A bounded, optional MapLibre renderer sharing the explorer API and evidence panel. */
(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const empty = () => ({ type: "FeatureCollection", features: [] });
  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  let map,
    options,
    loadPromise,
    response,
    timer,
    play,
    request,
    serial = 0,
    openSerial = 0;
  const colors = [
    "match",
    ["get", "confidence"],
    "verified",
    "#a6d6c5",
    "official",
    "#81b7dc",
    "tentative",
    "#e8ba7a",
    "#91a5ab",
  ];
  function library() {
    if (window.maplibregl) return Promise.resolve();
    if (!loadPromise)
      loadPromise = new Promise((resolve, reject) => {
        const link = document.createElement("link");
        link.rel = "stylesheet";
        link.href = "https://unpkg.com/maplibre-gl@5.11.0/dist/maplibre-gl.css";
        document.head.append(link);
        const script = document.createElement("script");
        script.src = "https://unpkg.com/maplibre-gl@5.11.0/dist/maplibre-gl.js";
        script.onload = resolve;
        script.onerror = () => {
          loadPromise = null;
          script.remove();
          reject(
            new Error(
              "3D library unavailable. The main map and evidence explorer still work.",
            ),
          );
        };
        document.head.append(script);
      });
    return loadPromise;
  }
  function stop() {
    clearInterval(play);
    play = null;
    $("playTime").textContent = "Play filed years";
  }
  function render() {
    if (!response || !map?.getSource("anchors")) return;
    const base = Number($("baseYear").value),
      through = Number($("throughYear").value);
    if (!Number.isInteger(base) || base < 1900 || base > 2199) {
      $("timeStatus").textContent = "Choose a base year between 1900 and 2199.";
      return;
    }
    $("throughLabel").textContent = through;
    const scale = 500000 / 2 ** map.getZoom(),
      radius = scale * 0.7,
      origin = Date.UTC(base, 0, 1),
      yearMs = 365.2425 * 86400000;
    const anchors = empty(),
      stems = empty(),
      caps = empty();
    let dated = 0,
      unknown = 0,
      outside = 0,
      groups = 0;
    for (const feature of response.map.features) {
      const p = feature.properties,
        g = feature.geometry;
      const c =
        g.type === "Point"
          ? g.coordinates
          : g.type === "LineString"
            ? g.coordinates[0]
            : g.type === "MultiLineString"
              ? g.coordinates[0][0]
              : null;
      if (!c) continue;
      if (p.cluster) {
        anchors.features.push(feature);
        groups++;
        continue;
      }
      const interval = PlanningModel.interval(p.date, p.precision);
      if (
        interval &&
        (interval.end <= origin ||
          interval.start >= Date.UTC(through + 1, 0, 1))
      ) {
        outside++;
        continue;
      }
      anchors.features.push({
        type: "Feature",
        properties: p,
        geometry: { type: "Point", coordinates: c },
      });
      if (!interval) {
        unknown++;
        continue;
      }
      dated++;
      const bottom = Math.max(0, ((interval.start - origin) / yearMs) * scale),
        top = Math.max(
          bottom + scale * 0.035,
          ((interval.end - origin) / yearMs) * scale,
        );
      const ring = (width) => {
        const dy = width / 111320,
          dx = dy / Math.max(0.1, Math.cos((c[1] * Math.PI) / 180));
        return [
          [c[0] - dx, c[1] - dy],
          [c[0] + dx, c[1] - dy],
          [c[0] + dx, c[1] + dy],
          [c[0] - dx, c[1] + dy],
          [c[0] - dx, c[1] - dy],
        ];
      };
      stems.features.push({
        type: "Feature",
        properties: { ...p, bottom: 0, top: bottom },
        geometry: { type: "Polygon", coordinates: [ring(radius * 0.14)] },
      });
      caps.features.push({
        type: "Feature",
        properties: { ...p, bottom, top },
        geometry: { type: "Polygon", coordinates: [ring(radius)] },
      });
    }
    map.getSource("anchors").setData(anchors);
    map.getSource("stems").setData(stems);
    map.getSource("caps").setData(caps);
    $("timeStatus").textContent = groups
      ? `${groups} aggregate groups. Zoom in to level 7 for individual dated records. ${response.mapped.toLocaleString()} located records in this scope.`
      : `${dated} dated markers · ${unknown} undated ground markers · ${outside} outside ${base}–${through}. ${response.map_truncated ? "800-feature cap: zoom closer. " : ""}Vertical scale changes with zoom; compare dates within the current view. Unlocated filings remain in the main catalog.`;
  }
  async function refresh() {
    if (!map || !$("timeDialog").open) return;
    request?.abort();
    request = new AbortController();
    const seq = ++serial;
    const p = new URLSearchParams(options.query),
      b = map.getBounds();
    p.set(
      "bbox",
      NationModel.viewport({
        west: b.getWest(),
        east: b.getEast(),
        south: b.getSouth(),
        north: b.getNorth(),
      }),
    );
    p.set("zoom", String(Math.floor(map.getZoom())));
    p.set("limit", "1");
    p.set("offset", "0");
    $("timeStatus").textContent = "Loading the visible filing records…";
    try {
      const r = await fetch("/api/nation/projects?" + p, {
          signal: request.signal,
        }),
        d = await r.json();
      if (!r.ok) throw new Error(d.error || "Query failed.");
      if (seq !== serial) return;
      response = d;
      render();
    } catch (err) {
      if (seq === serial && err.name !== "AbortError")
        $("timeStatus").textContent = err.message;
    }
  }
  function setup() {
    map = new maplibregl.Map({
      container: "timeMap",
      center: [-97, 38],
      zoom: 4,
      pitch: 55,
      bearing: -15,
      maxPitch: 70,
      minZoom: 2,
      maxZoom: 17,
      style: {
        version: 8,
        sources: {
          osm: {
            type: "raster",
            tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
            tileSize: 256,
            maxzoom: 19,
            attribution:
              '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
          },
        },
        layers: [
          {
            id: "base",
            type: "raster",
            source: "osm",
            paint: {
              "raster-saturation": -1,
              "raster-brightness-max": 0.28,
              "raster-brightness-min": 0.04,
            },
          },
        ],
      },
    });
    map.addControl(
      new maplibregl.NavigationControl({ visualizePitch: true }),
      "top-right",
    );
    map.on("error", () => {
      $("timeStatus").textContent =
        "A map resource could not load. The filing catalog remains available in the main explorer.";
    });
    map.on("load", () => {
      for (const id of ["anchors", "stems", "caps"])
        map.addSource(id, { type: "geojson", data: empty() });
      map.addLayer({
        id: "anchors",
        type: "circle",
        source: "anchors",
        paint: {
          "circle-radius": [
            "case",
            ["has", "cluster"],
            ["+", 8, ["*", 2, ["ln", ["get", "count"]]]],
            4,
          ],
          "circle-color": colors,
          "circle-opacity": [
            "case",
            ["==", ["get", "confidence"], "tentative"],
            0.12,
            0.8,
          ],
          "circle-stroke-color": colors,
          "circle-stroke-width": 1.5,
        },
      });
      for (const [id, opacity] of [
        ["stems", 0.3],
        ["caps", 0.85],
      ])
        map.addLayer({
          id,
          type: "fill-extrusion",
          source: id,
          paint: {
            "fill-extrusion-color": colors,
            "fill-extrusion-base": ["get", "bottom"],
            "fill-extrusion-height": ["get", "top"],
            "fill-extrusion-opacity": opacity,
          },
        });
      const popup = new maplibregl.Popup({
        closeButton: false,
        closeOnClick: false,
      });
      map.on("mousemove", (event) => {
        const f = map.queryRenderedFeatures(event.point, {
          layers: ["caps", "anchors"],
        })[0];
        map.getCanvas().style.cursor = f ? "pointer" : "";
        if (!f) {
          popup.remove();
          return;
        }
        const p = f.properties;
        popup
          .setLngLat(event.lngLat)
          .setText(
            p.cluster
              ? `${p.count} located records · click to zoom`
              : `${p.name} · ${p.date || "Date unknown"} (${p.precision || "unknown"}) · ${NationModel.confidenceLabel(p.confidence)}`,
          )
          .addTo(map);
      });
      map.on("click", (event) => {
        const f = map.queryRenderedFeatures(event.point, {
          layers: ["caps", "anchors"],
        })[0];
        if (!f) return;
        if (f.properties.cluster) {
          map.easeTo({
            center: f.geometry.coordinates,
            zoom: Math.min(10, map.getZoom() + 2),
            duration: reduced ? 0 : 650,
          });
          return;
        }
        close();
        options.select(f.properties.id);
      });
      map.on("moveend", () => {
        clearTimeout(timer);
        timer = setTimeout(refresh, 200);
      });
      refresh();
    });
  }
  function close() {
    openSerial++;
    stop();
    request?.abort();
    clearTimeout(timer);
    $("timeDialog").close();
  }
  window.TimeLens = {
    async open(settings) {
      options = settings;
      response = null;
      request?.abort();
      serial++;
      for (const id of ["anchors", "stems", "caps"])
        map?.getSource(id)?.setData(empty());
      const seq = ++openSerial;
      $("timeDialog").showModal();
      $("timeStatus").textContent = "Loading time lens…";
      try {
        await library();
        if (seq !== openSerial || !$("timeDialog").open) return;
        if (!map) setup();
        map.resize();
        const b = settings.bounds;
        if (b)
          map.fitBounds(
            [
              [b.getWest(), b.getSouth()],
              [b.getEast(), b.getNorth()],
            ],
            { padding: 25, duration: 0, pitch: 55, bearing: -15 },
          );
        if (map.isStyleLoaded()) refresh();
      } catch (err) {
        $("timeStatus").textContent = err.message;
      }
    },
  };
  $("closeTime").onclick = close;
  $("timeDialog").addEventListener("cancel", close);
  $("baseYear").onchange = () => {
    stop();
    const base = Number($("baseYear").value);
    if (Number.isInteger(base) && base >= 1900 && base <= 2199) {
      $("throughYear").min = base;
      $("throughYear").max = Math.min(2200, base + 30);
      $("throughYear").value = Math.min(2200, base + 30);
    }
    render();
  };
  $("throughYear").oninput = () => {
    stop();
    render();
  };
  $("flatTime").onclick = () =>
    map?.easeTo({
      pitch: map.getPitch() > 10 ? 0 : 55,
      duration: reduced ? 0 : 500,
    });
  $("playTime").onclick = () => {
    if (play) {
      stop();
      return;
    }
    $("throughYear").value = $("throughYear").min;
    render();
    $("playTime").textContent = "Pause playback";
    play = setInterval(() => {
      if (Number($("throughYear").value) >= Number($("throughYear").max)) {
        stop();
        return;
      }
      $("throughYear").value = Number($("throughYear").value) + 1;
      render();
    }, 900);
  };
})();
