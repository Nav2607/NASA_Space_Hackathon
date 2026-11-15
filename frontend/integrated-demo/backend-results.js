/* Agronaut results — calls the Agronaut backend (POST /recommend).
   Every number shown comes from the API response; nothing is computed or invented here. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const CROP = {corn: 'Corn', soybean: 'Soybean', winter_wheat: 'Winter wheat', red_clover: 'Red clover', cereal_rye: 'Cereal rye'};
  const MAIN = ['corn', 'soybean', 'winter_wheat'];
  const SOIL = ['sandy_loam', 'loam', 'clay_loam', 'clay'];
  // Form soils the backend has no table for are mapped to the nearest one, and the user is told.
  const SOIL_FALLBACK = {
    sandy: ['sandy_loam', 'Sandy soil was modelled as sandy loam (closest available).'],
    silt_loam: ['loam', 'Silt loam was modelled as loam (closest available).'],
    unknown: ['loam', 'Soil texture not given; loam was assumed.'],
  };
  const cfg = window.AGRONAUT_CONFIG || {};
  const apiBase = (cfg.apiBase || (location.port === '8000' ? '' : 'http://localhost:8000')).replace(/\/$/, '');

  let lastInput = null, lastResponse = null, mode = 'typical', busy = false;

  const node = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; };
  const name = c => CROP[c] || c;
  const rotationText = rot => rot.map(y => name(y.crop) + (y.cover_crop ? ` + ${name(y.cover_crop)}` : '')).join(' → ');
  const mm = v => (v == null ? 'n/a' : `${Math.round(v)} mm`);
  const status = (text, error = false) => { $('results-message').textContent = text; $('results-message').className = error ? 'results-message error' : 'results-message'; };
  const setBusy = on => { busy = on; $('compareButton').disabled = on; if (on) $('results-state').textContent = 'Running simulation…'; };
  const markScenario = which => {
    for (const [id, k] of [['weather-typical', 'typical'], ['weather-dry', 'dry'], ['weather-future', 'future']])
      $(id).classList.toggle('scenario-selected', k === which);
  };

  function buildRequest(f) {
    const notes = [];
    let soil = f.soilTexture;
    if (!SOIL.includes(soil)) {
      const [mapped, note] = SOIL_FALLBACK[soil] || ['loam', 'Soil texture not recognised; loam was assumed.'];
      soil = mapped; notes.push(note);
    }
    const rows = f.currentRotation.slice().sort((a, b) => a.growingYear - b.growingYear);
    const current = rows.map(r => r.crop).filter(c => MAIN.includes(c)).slice(0, 4);
    if (rows.some(r => !MAIN.includes(r.crop))) notes.push('Cover crops in your rotation are not scored by the model and were left out of the baseline.');
    const p = f.priorities, raw = {water: p.water, nitrogen: p.nitrogen, soil_cover: p.soilCover, weather_risk: p.weatherRisk};
    const total = Object.values(raw).reduce((a, b) => a + b, 0) || 1;
    const priorities = Object.fromEntries(Object.entries(raw).map(([k, v]) => [k, v / total]));
    return {
      body: {
        lat: f.location.lat, lon: f.location.lon, soil,
        tile_drainage: f.drainage === 'yes', irrigation: f.irrigation.availability === 'yes',
        current_rotation: current, must_include: f.mustGrow, avoid: f.avoid, priorities,
      },
      notes,
    };
  }

  async function call(body, climate) {
    let res;
    try {
      res = await fetch(`${apiBase}/recommend`, {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({...body, climate_period: climate}),
      });
    } catch (e) {
      throw new Error(`Cannot reach the backend at ${apiBase || 'this site'}. Start it with: python -m uvicorn backend.api.main:app --port 8000`);
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const d = data.detail;
      if (Array.isArray(d) && d.some(x => ['lat', 'lon'].includes((x.loc || [])[1])))
        throw new Error('This location is outside the area the model covers (Southern Ontario). Choose a point on the map closer to Southern Ontario.');
      throw new Error(typeof d === 'string' ? d
        : Array.isArray(d) ? d.map(x => `${(x.loc || []).slice(1).join('.')}: ${x.msg}`).join('; ')
        : `Server error ${res.status}`);
    }
    return data;
  }

  function metricRow(label, value, delta, rating) {
    const row = node('div', 'ts-metric');
    row.append(node('span', 'ts-muted', label), node('strong', rating ? 'ts-rating' : '', value));
    if (delta) row.append(node('small', 'ts-muted', delta));
    return row;
  }
  const signed = (v, unit) => (v == null ? null : Math.abs(v) < 0.5 ? 'about the same as your plan'
    : `${v > 0 ? '+' : '−'}${Math.round(Math.abs(v))} ${unit} vs your plan`);

  function card(entry, base, featured) {
    const c = node('article', 'ts-card' + (featured ? ' ts-featured' : ''));
    const isBase = entry === base;
    c.append(node('p', 'ts-eyebrow', isBase ? 'Your current plan' : entry.label_text || 'Alternative'));
    c.append(node('h3', '', entry.name || rotationText(entry.rotation)));
    const m = entry.metrics || {}, bm = base.metrics || {};
    const key = mode === 'dry' ? 'dry_year_shortfall_mm' : 'typical_year_shortfall_mm';
    const diff = k => (isBase || m[k] == null || bm[k] == null ? null : m[k] - bm[k]);
    c.append(metricRow('Potential water demand per year', mm(m.water_use_mm), signed(diff('water_use_mm'), 'mm')));
    c.append(metricRow(mode === 'dry' ? 'Unmet demand, dry year' : 'Unmet demand, typical year', mm(m[key]), signed(diff(key), 'mm')));
    const r = entry.ratings || {};
    if (r.nitrogen) c.append(metricRow('Nitrogen need (indicator)', r.nitrogen.label, null, true));
    if (r.soil_cover) c.append(metricRow('Soil cover (indicator)', r.soil_cover.label, null, true));
    if (r.pest_break) c.append(metricRow('Pest / disease break', r.pest_break.label, null, true));
    if (entry.why) c.append(node('p', 'ts-why', entry.why));
    const notes = [...(entry.tradeoffs || []), ...(entry.warnings || [])];
    if (notes.length) {
      const d = node('details', 'ts-details'); d.append(node('summary', '', 'Trade-offs and cautions'));
      const ul = node('ul'); notes.forEach(t => ul.append(node('li', '', t))); d.append(ul); c.append(d);
    }
    return c;
  }

  function draw() {
    const data = lastResponse, host = $('comparison-cards');
    host.replaceChildren(); $('metrics-bar').replaceChildren();
    host.className = 'comparison-cards ts-layout';
    const future = !!(data.scoring_period && data.scoring_period.startsWith('future'));
    $('results-state').textContent = future ? 'Projected 2031–2050 (model scenario, not a forecast)' : 'Historical weather 2005–2024';
    $('source-years').textContent = future ? 'NASA POWER + NEX-GDDP-CMIP6 change factors' : 'NASA POWER · daily data, 1981–2024';
    $('results-subtitle').textContent = data.anchor
      ? `Regional data point “${data.anchor.id}”, ${Math.round(data.anchor.distance_km)} km from your field` : '';
    const methods = $('methods-text'); methods.replaceChildren();
    [data.simulation_method, ...(data.warnings || []), data.disclaimer].filter(Boolean)
      .forEach(t => methods.append(node('p', '', typeof t === 'string' ? t : JSON.stringify(t))));
    if (data.status === 'insufficient_data' || !data.baseline || !data.baseline.metrics) {
      host.append(node('div', 'ts-no-alts', data.reason || 'The model cannot evaluate this baseline.'));
      return;
    }
    host.append(card(data.baseline, data.baseline));
    if (data.options.length) data.options.forEach((o, i) => host.append(card(o, data.baseline, i === 0)));
    else host.append(node('div', 'ts-no-alts', data.reason || 'No alternatives match your crop preferences. Adjust Must-grow or Crops to avoid.'));
  }

  async function run(climate) {
    if (busy || !lastInput) return;
    setBusy(true);
    try {
      lastResponse = await call(lastInput.body, climate);
      draw();
      status(lastInput.notes.concat('Educational decision support: relative comparisons, not yield or irrigation predictions.').join(' '));
    } catch (e) {
      lastResponse = null; $('comparison-cards').replaceChildren(); $('metrics-bar').replaceChildren();
      $('results-state').textContent = 'Unavailable';
      status(e.message, true);
    } finally { setBusy(false); }
  }

  function selectScenario(which) {
    const wasFuture = mode === 'future';
    mode = which; markScenario(which);
    if (!lastInput) return;
    if (which === 'future' || wasFuture) run(which === 'future' ? 'future' : 'historical');
    else if (lastResponse) draw();
  }
  $('weather-typical').addEventListener('click', () => selectScenario('typical'));
  $('weather-dry').addEventListener('click', () => selectScenario('dry'));
  const fut = $('weather-future');
  fut.disabled = false; fut.title = 'Climate-model projection, 2031–2050'; fut.textContent = '2031–2050 projection';
  fut.addEventListener('click', () => selectScenario('future'));

  window.addEventListener('agronaut:compare', e => {
    lastInput = buildRequest(e.detail); mode = 'typical'; markScenario('typical');
    $('results').hidden = false; $('results').scrollIntoView({behavior: 'smooth', block: 'start'});
    run('historical');
  });
})();
