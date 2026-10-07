/* Scenario UI backed only by the local, cited NOAA station archive. */
(() => {
  const $ = (id) => document.getElementById(id),
    e = NationModel.esc;
  let data,
    version = 0;
  const month = (n) =>
    new Date(Date.UTC(2000, n - 1, 1)).toLocaleDateString("en-US", {
      month: "short",
      timeZone: "UTC",
    });
  function render() {
    if (!data?.observations) return;
    try {
      const rules = {
        workdays: Number($("workdays").value),
        rain: Number($("rainStop").value),
        wind: $("useWind").checked ? Number($("windStop").value) : null,
        heat: $("useHeat").checked ? Number($("heatStop").value) : null,
        freeze: $("useFreeze").checked ? Number($("freezeStop").value) : null,
      };
      const results = PlanningModel.replay(data, rules);
      const max = Math.max(1, ...results.map((r) => r.max || 0));
      $("replayResults").innerHTML =
        `<p class="eyebrow">EXTRA CALENDAR DAYS · HISTORICAL SCENARIO</p><p>Start on the first of each month; complete ${rules.workdays} weekdays of work. Stops use your thresholds, not a safety standard. Each row replays ${results[0].attempted} historical years. Medians use only complete trials; exclusions can bias comparisons.</p><table class="replay-table"><thead><tr><th>Start</th><th>Median / range</th><th>Used</th><th>Excluded<br>missing / window / cap</th></tr></thead><tbody>${results.map((r) => `<tr><th>${month(r.month)}</th><td><div class="replay-bar" style="--bar:${((r.max || 0) / max) * 100}%"><span>${r.median === null ? "Unavailable" : `${r.median} days · ${r.min}–${r.max}`}</span></div></td><td>${r.trials.length}/${r.attempted}</td><td>${r.excluded.missing} / ${r.excluded.window} / ${r.excluded.horizon}</td></tr>`).join("")}</tbody></table><p class="note">Weekends are excluded from work; extra days include weekends caused by a delay. Trials with unknown required conditions are excluded unless another observed condition already stops work. Trials exceeding the archive or 180 calendar days are excluded. No trial is a probability estimate or future forecast.</p><details><summary>Inspect every completed trial and stop count</summary><pre>${e(JSON.stringify({ rules, results }, null, 2))}</pre></details>`;
    } catch (err) {
      $("replayResults").textContent = err.message;
    }
  }
  window.WeatherPlanner = {
    async open(lon, lat, label) {
      const seq = ++version;
      data = null;
      $("weatherTitle").textContent = label || "Selected location";
      $("weatherSources").textContent = "Selecting eligible NOAA stations…";
      $("replayResults").textContent = "";
      $("weatherRules").hidden = true;
      $("weatherDialog").showModal();
      try {
        const response = await fetch(
          "/api/nation/history?" + new URLSearchParams({ lon, lat }),
        );
        const r = await response.json();
        if (seq !== version) return;
        if (!response.ok)
          throw new Error(r.error || "Weather archive unavailable.");
        data = r;
        const station = (s, label) =>
          s
            ? `<p><b>${label}: ${e(s.name)}</b> · ${s.distance_mi} mi away<br>${e(s.id)} · retrieved ${e(s.retrieved_at.slice(0, 10))}<br>${NationModel.safeUrl(s.source_url) ? `<a href="${e(NationModel.safeUrl(s.source_url))}" target="_blank" rel="noopener">NOAA original data ↗</a>` : ""}</p>`
            : `<p>${label}: no eligible station.</p>`;
        $("weatherSources").innerHTML =
          `<p>${e(r.window.start)} → ${e(r.window.end)} · station archive · ${e(r.status)}</p><p>${e(r.limitations.join(" "))}</p>${station(r.rain, "Rain / temperature")}${station(r.wind, "Wind")}`;
        if (!r.observations) return;
        $("weatherRules").hidden = false;
        $("useWind").disabled = !r.wind;
        if (!r.wind) $("useWind").checked = false;
        render();
      } catch (err) {
        if (seq === version) $("weatherSources").textContent = err.message;
      }
    },
  };
  $("closeWeather").onclick = () => {
    version++;
    $("weatherDialog").close();
  };
  $("weatherRules").oninput = render;
})();
