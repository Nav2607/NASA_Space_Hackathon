# Claim-to-source audit — active integrated dashboard

Reviewed against `origin/backend` merge **641b6f2**, its implementation and
`backend/SCIENTIFIC_VALIDITY.md` / `backend/BLIND_SPOTS_API.md`.
No agricultural parameters, physics, scores or scientific algorithms changed.
Scope is the active `index.html`, `app.js`, `farm-form.js`, `dashboard-core.js`
and `dashboard.js`; the preserved legacy `results.js` is explicitly not loaded.

## Independently identified issues and corrections

- The fetched frontend still ran illustrative fixed-Kc browser calculations,
  live POWER downloads for 2012–2025 and preset alternatives. Disconnected that
  script and integrated the continuous backend; no duplicate engine remains
  active. Existing source is preserved for the team.
- Planning years, crop dates, budget, crop history and soil aliases were
  unsupported by the current API or could imply unsupported calculations.
  Removed those inputs from the active form; explain approximate model calendars
  and use only supported soils. Each crop stays in the supplied order, without
  filtering or truncation. No arbitrary planning year is shown as a forecast.
- The original map anchor request expected `/api/anchors` and an array, while
  the backend returns an ID-keyed object at `/anchors`. Corrected the adapter;
  added a real cached-anchor fallback for offline map/geocoder failures.
- No enhanced Blind Spots or real future model UI existed on this branch.
  Connected the actual endpoint, matched reference, weekly/model/phase outputs
  and event diagnostics. Model weather is never averaged by the frontend.
- Recommendation wording risked implying a single best rotation, soil protection
  or fertilizer benefit. Retain backend option order; show positive and negative
  differences; distinguish calendar occupancy and ordinal nitrogen from measured
  environmental outcomes. No percentage reduction or new resilience score.
- Form edits and overlapping requests could leave old results visible. Added
  input generation checks, aborts and explicit stale states. Failures never
  substitute synthetic numbers. Requests and large diagnostics load on demand.
- Small type, lengthy method sections and unsupported controls obscured decisions.
  Reused the visual theme with compact metric/sequence cards, bars, heatmaps,
  collapsible diagnostic tables, keyboard controls and distinct zero/N/A cells.

## Metric traceability

Backend paths below are relative to `backend/` at commit `641b6f2`.
`recommend` means the response from `POST /recommend`; `blind` means
`POST /blind-spots`. All displayed values are direct fields unless explicitly
marked as a display-only difference.

| User-facing metric/claim | Exact field / implementation | Display and scientific limit |
|---|---|---|
| Current/alternative crop sequence | `recommend.baseline.rotation` / `options[].rotation`; `engine/recommend.py` | Exact backend order. Input crop order is preserved; unsupported crops are rejected. |
| Option order / selection reason | `recommend.options[]` and `label`, `labels`; `pick_options()` | Backend selection order across criteria, **not** descending overall score or a universal ranking. No numeric score invented. |
| Potential water demand, mm/yr | `metrics.potential_demand_mm`; alias `water_use_mm` | Potential ETc demand; not observed consumption, water savings or irrigation need. |
| Typical unmet demand, mm/yr | `metrics.typical_year_shortfall_mm` | Existing phase-averaged annual median shortfall; lower demand and shortfall must be considered together. |
| P90 unmet demand, mm/yr | `metrics.dry_year_shortfall_mm` | Existing within-phase annual p90, then phase average; future uses model median. Not an adverse-year replay or probability of crop failure. |
| Modeled actual ET, mm/yr | `metrics.actual_et_mm` | Existing water-limited ET summary. Stress-limited low ET is not presented as an improvement. Independently summarized medians need not add up. |
| Sensitive-window water stress, days/yr (leaderboard) | `metrics.critical_stress_days_typical` | Existing depletion-threshold annual-median statistic, distinct from unmet-demand days. |
| Heat exposure, days/yr (leaderboard) | `metrics.heat_stress_days_typical` | Existing crop-specific threshold in approximate sensitive windows; not measured heat damage. |
| Signed baseline differences | `candidate.metrics[key] - baseline.metrics[key]`, same response/period | Display-only arithmetic in original units; only finite values. No percentages, ratios, zero-denominator division, cross-period difference or composite score. Unfavorable values remain visible. |
| Qualitative nitrogen demand | `ratings.nitrogen.label`; `engine/ratings.py::nitrogen_rating`; `data/reference/crops.json::n_base_class` | **Assumed ordinal** low/medium/high demand. Corn high, soybean low, wheat medium are team assumptions; rotation mean uses ordinal 1/2/3 and assumed label cutoffs 1.67/2.34. No kg N/ha, measured savings, nitrogen loss or emissions claim. |
| Legume/predecessor benefit | `ratings.nitrogen.legume_credit_crops=[]`; `rotation_rules.json::legume_credit` status `needs_citation` | No credits are applied. No unsupported legume savings or fertilizer percentage is displayed. |
| Living-crop indicator | `ratings.soil_cover.label`; corrected `living_cover_fraction` derives from modeled crop-calendar occupancy | Labeled calendar-derived living-crop indicator. Not protective cover, residue fraction, erosion reduction or measured soil health. |
| Compatibility and warnings | Backend candidate filters, input constraints, `warnings`, `tradeoffs`, `engine/rotations.py` | Alternatives retain mandatory constraints. Original baseline stays even if incompatible. Pest/yield/timing notes are explicitly tagged prototype assumptions; some require citations. No prediction of pest control or yield. |
| Time Machine values/ranges | Baseline `recommend.time_machine`; candidate `options[].time_machine`; `metrics` and future `model_range` | Exact historical decades; future model-median outcomes with min/max spread after independent simulations. No frontend averaging of weather, significance test or probability. |
| Annualized Blind Spots days | `blind.summary.annualized_days.{water,heat,combined}`; future `model_range.annualized_days` | Mean annual counts after phase averaging; future model median. **Not identical to recommendation annual-median metrics.** Water and heat include combined days. |
| Weekly exposure frequency | `runs[].weekly_vulnerabilities[].frequency_pct` | Direct backend percent of eligible season equivalents. At least one flagged day/week. Not percent crop damage, exposed days, observed farm frequency or calibrated probability. |
| Eligible crop seasons | `eligible_seasons`, `eligible_season_years` in same weekly row | Absent/ineligible crop years excluded. Phases are alternative placements averaged within climate years, not independent observed years. N/A weeks use a hatch/—, zero uses 0. Small nonzero annual counts retain extra display precision. |
| Average weekly intensity/unmet demand | `mean_water_depletion_intensity`, `mean_daily_unmet_demand_mm`, `mean_heat_exceedance_c` | Direct averages from the backend, available on selected-week inspection. No Kc-to-cover substitution or frontend stress calculation. |
| Event date, duration and intensity | `runs[].phases[].events[]`: `start_date`, `end_date`, `duration_days`, mean/max intensity, cumulative unmet mm, cumulative heat degree-days, max temperature | Consecutive same-crop/type events; splits on type change. Heat degree-days sum daily Tmax exceedance, not hourly heat dose. Events/year/phase remain separate. |
| Longest and average event | `phases[].event_statistics` | Full selected phase/period, clearly distinguished from the selected year's event table. Null average if no events. |
| Daily water and temperature | `phases[].daily[]`: rain, Tmax, storage, unmet demand, depletion intensity, heat exceedance | Direct diagnostics; storage is end-of-day, intensity uses the engine's after-rain/pre-ET threshold. 0–1 intensity never means percentage damage. No frontend water physics. |
| Future weekly changes / agreement | `emerging_vulnerabilities[].exposures[indicator]` | Historical frequency, each model, median/range, absolute percentage-point change, increased/decreased/unchanged model counts. Uses matched 1995–2014 unadjusted/adjusted sequences. No probabilities. |
| Vulnerability descriptions | `classification` and `classification_rules` | Emerging: zero historical, every model increases; diminishing: all decrease from positive historical; persistent: positive historical and no decrease; uncertain: remaining mixed/partial outcomes; no exposure: all zero. Descriptive only, not statistical confidence. |

## Data attribution and limits

- **NASA POWER**: `engine/weather.py::load_weather`, cached anchor CSVs and
  `engine/recommend.py::SOURCES` supply daily Tmin/Tmax/precipitation. Regional,
  NASA-derived estimates, not on-field observations. This runtime uses POWER
  precipitation; it neither requests nor adds GPM rainfall.
- **NEX-GDDP-CMIP6**: `engine/climate_future.py`, committed
  `data/nex/delta_ssp245_2031_2050.json`, `baseline_period=1995–2014`,
  `future_period=2031–2050`, three named models. Monthly temperature/DTR and
  precipitation factors adjust historical daily sequences independently.
- **FAO-56/reference assumptions**: `engine/et0.py`, `rotation_simulation.py`,
  `data/reference/crops.json`, `soil_texture.json`, `sources.json`.
  FAO Hargreaves and Kc methods coexist with analogue stage durations and assumed
  regional calendars, sensitive windows and soil presets. Do not label every
  reference parameter as Ontario-calibrated or validated.
- Official source links in the UI are NASA POWER, NASA's NEX collection and
  FAO-56. OpenFreeMap is attributed separately as the map provider.
- GPM is explicitly not integrated into runtime simulation. SMAP and MODIS are
  not advertised as integrated. No crop-survival, measured fertilizer/water
  savings, erosion, carbon, yield, profitability or cover-crop benefit claim.
- Future results do not project exact weather dates, rainfall occurrence,
  changes in heatwave sequencing, phenology or field-level damage.

## Verification evidence

- Eleven Node adapter/display tests, JavaScript syntax checks and diff whitespace
  validation pass. No project build/lint/TypeScript configuration exists.
- The isolated unchanged backend at `641b6f2` passes all 94 tests.
- Real Chrome + HTTP backend workflow checks baseline and alternative metrics,
  exact option/crop order, historical and future periods, three model controls,
  annualized diagnostics, weekly eligibility and event inspection, caching,
  invalidation and explicit insufficient/unsupported-location states. Desktop
  and 390 px mobile views had no page overflow. Cached regional selection still
  produced real results with online map/geocoder/font services blocked.
- Review screenshots are saved outside the application under
  `/private/tmp/fieldshift-before.png`, `fieldshift-after.png`,
  `fieldshift-blind-spots.png`, `fieldshift-comparisons.png`, `fieldshift-mobile.png`.
  Timing checks on this machine are not a deployment latency guarantee.

## Plain-language display revision

- Water need remains `potential_demand_mm` / Time Machine `water_use_mm`,
  not measured consumption; water shortfall remains the existing unmet-demand
  fields. Short labels do not change their scientific meaning.
- A single leaderboard preserves the original option order and baseline
  reference. Its position numbers are selection positions, not new scores.
- One climate table preserves all period values and returned model ranges.
- Approximate month and early/mid/late labels are reference-calendar navigation
  aids for ISO week numbers; no event dates or crop calendars are changed.
- Future calendar median percentages are read directly from the backend's
  `future_median_frequency_pct`; per-model diagnostics remain independent.
  Median intensity is unavailable and is not synthesized.
- “% of modeled crop seasons” is the plain-language presentation of the same
  phase-averaged eligible-season frequency, not a newly calculated percentage
  or crop-damage probability. Full denominator explanations remain expandable.

## Latest future-first presentation (supersedes prior layout descriptions)

- The active result page now always requests future scoring/calendars under
  SSP2-4.5 for 2031–2050. Historical references remain in the backend and the
  methodology explanation; no historical result selector or climate-outlook
  comparison appears in the main page.
- The recommendation highlight uses the existing backend `balanced` label,
  falling back to the highest returned backend score. No frontend score is
  calculated and no universal superiority is asserted. Original rotation is
  neutral blue-grey, distinct from the green suggested alternative.
- The main stress display is now an ordered rotation timeline, without percentage
  tiles. It directly plots daily storage, unmet demand and sensitive-window flags
  from one explicitly named model/phase and a complete interior reference cycle.
  Full-period annualized totals and model ranges remain direct backend fields.
  Year cards preserve duplicate crops and rotation order. Winter wheat bands cross
  calendar boundaries; year cards denote harvest years. No daily demand or water
  physics is reconstructed, and no weather is averaged across models. Changing
  illustrative model/phase/cycle reuses the existing response. Historical sequence
  dates are labeled as future-adjusted examples, not forecasts of future dates.
- Unused irrigation/tile-drainage inputs are removed and not sent. The underlying
  backend remains rainfed; the scope is stated in the form and methodology.
- Cover crops are visible but disabled because their demand is unsupported; they
  are not silently dropped or assigned fabricated benefits.
- Corn-followed-by-wheat entries are retained. Fixed-calendar infeasibility is
  explained as a model limitation, with unavailable outputs, not an invented
  “suboptimal” score or a blanket agronomic prohibition.
- Nitrogen colours encode the same ordinal demand labels, not amounts saved.
- The separate methodology page shows a schematic (explicitly not measured),
  exact existing equations, the actual priority weights and actual future
  original/recommended metrics. Weight percentages are not fertilizer benefits
  or probabilities. A small displayed-result snapshot travels only in a URL
  fragment/session context; daily data is not duplicated for the page.
- GPM, SMAP, MODIS, irrigation, drainage, cover-crop demand, field validation,
  measured fertilizer savings, yield and profit are not presented as implemented.
