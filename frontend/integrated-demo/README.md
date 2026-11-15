# Agronaut — future-focused frontend

Implementation branch: `frontend-dashboard-enhancement`, based on `origin/frontend`.
The backend is **unchanged**, running in a detached worktree at merge `641b6f2`.
No backend files were merged or copied into this frontend branch.

## Run locally

Use two terminals. From the frontend repository, install the backend's existing
requirements in your local virtual environment if needed:

```sh
.venv/bin/python -m pip install -r /private/tmp/fieldshift-backend-integration/backend/requirements-dev.txt
```

Terminal 1, initially in the frontend repository:

```sh
FIELD_SHIFT_REPO="$PWD"
cd /private/tmp/fieldshift-backend-integration
"$FIELD_SHIFT_REPO/.venv/bin/python" -m uvicorn backend.api.main:app --host 127.0.0.1 --port 8000
```

Terminal 2, in the frontend repository:

```sh
.venv/bin/python -m http.server 5500 --bind 127.0.0.1 --directory frontend/integrated-demo
```

Open **http://127.0.0.1:5500/**. `config.js` sets the API address. If you need another
backend worktree, create one separately from `origin/backend`; do not merge it
into this frontend branch merely to run the app.

## Current farmer workflow

1. Search for a Southern Ontario location, click the map, or use browser location.
   The cached-location selector has been removed as requested.
2. Enter 1–4 cash crops in their existing order, soil texture, equipment and crop
   constraints. Adjust priorities if useful. There are no unused irrigation or
   tile-drainage controls, and those fields are not sent to the API.
3. Compare once. The frontend always requests **future** scoring under SSP2-4.5,
   2031–2050. There is no historical/future choice to make.
4. Read the leaderboard. The original is blue-grey; the backend's balanced choice
   is green and marked **Algorithm's pick**. Nitrogen categories use low/medium/high
   colours but remain qualitative indicators, not fertilizer savings.
5. An ordered, continuous rotation timeline loads automatically for the recommended
   alternative. Year cards retain repeated crop positions. Daily soil storage,
   unmet-demand bars and water/heat/combined stress lanes replace percentage tiles.
   Selecting another row updates this view on the same page. A labeled single-model
   reference cycle illustrates continuity; full-period days/year totals summarize
   all phases and models. There are no result tabs or climate-outlook panel.
6. Open **How did we model this?** after the results. It opens a separate page/tab
   so the active farm inputs and results remain available.

The algorithm highlight uses the backend's `balanced` label (including combined
labels), falling back to its highest returned score if necessary. The frontend
neither changes scoring nor invents an agronomic best rotation. Options keep their
returned order. Review unfavorable differences as well as favorable ones.

## Two model limitations deliberately exposed

**Cover crops:** rye and red clover appear as disabled choices labelled unavailable.
Their water demand/calendar inputs are incomplete in the current backend. Enabling
them would falsely imply they participate in the simulation. They are not silently
removed or assigned water-free benefits. Actual support needs separately scoped
scientific/backend work.

**Corn → winter wheat:** the frontend accepts the entered cash-crop order. Under
some sequences the backend's fixed representative corn harvest falls after the
wheat planting window. If that makes the model calendar infeasible, the UI keeps
the original sequence and explains the prototype limitation, with unavailable
metrics. It does not tell a farmer their real rotation is inherently wrong, label
an uncomputable result merely “suboptimal,” or fabricate a recommendation.

## API integration and requests

- `GET /anchors`: internal metadata for regional map snapping/markers. No separate
  cached-anchor input remains.
- `POST /recommend`: always `climate_period: "future"`; baseline, constrained
  alternatives, existing scores/labels and future metrics come from the backend.
  Historical references remain internal to the scientific calculation.
- `POST /blind-spots`: always `climate_period: "future"`, only for the rotation
  currently shown. One response supplies **the complete rotation timeline**; no duplicate
  request per stress type or speculative daily downloads for every alternative.
- Existing backend historical periods are not deleted; they are simply removed
  from the primary farmer-facing result flow.

Up to eight in-memory response promises are reused for unchanged inputs. Duplicate
pending requests are shared. Farm edits abort/invalidate old requests and results;
late responses cannot redraw an earlier farm. Failures do not substitute examples.
The API has no summary-only or `include_daily` option, so full Blind Spots responses
remain large (roughly 4–20 MiB for previously measured rotations).

## Methodology page

`methodology.html` / `methodology.js` contain:

- NASA POWER, NEX-GDDP-CMIP6 and crop/soil reference roles, resolutions and official links.
- The historical-reference → independent-model → rotation-comparison pipeline.
- A labelled schematic soil-water diagram (not a farm measurement).
- Hargreaves, crop demand, daily storage/mass balance and stress equations.
- Actual priority weights and original/recommended result bars when opened from a run.
- Model assumptions, nitrogen interpretation, infeasible calendars and unsupported cover crops.

A **small result snapshot**, not daily datasets, is carried in the link's URL
fragment so it works in a separate tab without an opener. It contains displayed
regional/metric/priority information, not credentials. The fragment is not sent
as part of an HTTP request. The page also accepts same-tab session context. A
standalone source-page visit has no fake result-chart fallback.

The future graphs are climate sensitivity projections: monthly model changes are
applied to historical weather sequences. They do not forecast exact future dates,
new rainfall occurrence, heatwave timing or crop damage. Timeline month labels follow the returned reference dates; crop bands follow the
engine’s approximate calendars, not observed phenology.

## Tests and review

```sh
node --test frontend/integrated-demo/tests/dashboard-core.test.cjs
node --check frontend/integrated-demo/dashboard.js
node --check frontend/integrated-demo/dashboard-core.js
node --check frontend/integrated-demo/farm-form.js
node --check frontend/integrated-demo/app.js
node --check frontend/integrated-demo/methodology.js
git diff --check
```

Nineteen adapter/display tests cover request/sequence preservation, ignored-water
field omission, unsupported inputs, missing vs zero values, priority normalization,
period mapping, actual median-field use, recommendation selection and calendar-error
wording, rotation-cycle ordering, winter transitions, missing daily diagnostics
and stress-band grouping. The unchanged separate backend passed its 94-test suite in the preceding
integration milestone; no new backend-test result is implied by frontend edits.

Browser checks use actual HTTP backend responses for future scoring, automatic
continuous rotation timeline rendering, algorithm selection, neutral baseline, coloured nitrogen,
methodology snapshots and corn/wheat calendar rejection. If an external geocoder
is unavailable, the test harness records that and uses the location-event contract
with real anchor coordinates; it never mocks simulation outputs. Test output must
be consulted before claiming external search was verified.

This is a static vanilla-JavaScript application. There is no configured build,
TypeScript or lint pipeline and no new runtime dependencies.

## Network dependencies and preserved work

The optional map uses MapLibre CDN scripts/styles, OpenFreeMap tiles/styles and
Nominatim search/reverse geocoding. The cached-location fallback was intentionally
removed, so test map/search connectivity before a live demo. Backend weather and
projections remain offline caches; no runtime NASA calls are introduced. The hero
photo and methodology illustration are local; there are no Google Fonts requests.

The original `results.js` and standalone `frontend/farmer-form/` remain preserved
but are not loaded by the integrated page. Do not load the legacy browser-only
simulation alongside the real backend dashboard. See
[SCIENTIFIC_CLAIM_AUDIT.md](SCIENTIFIC_CLAIM_AUDIT.md) for field-level traceability.

## Continuous rotation visual

The timeline plots returned daily `storage_mm` and `unmet_demand_mm` without
recalculating water balance. Stress lanes group existing flags for display only.
The crop band uses actual daily crop identities; year headers identify harvest
years, so winter wheat can start the previous autumn. A complete interior cycle
is shown by default; advanced controls select an existing model, starting position
or reference cycle without new API requests. No daily weather is averaged across
models. Missing diagnostics leave the illustration unavailable. The API does not
expose daily potential demand, so no demand curve is manufactured in JavaScript.
Reference dates remain explicitly historical weather sequences adjusted by monthly
2031–2050 climate factors, never deterministic future-year forecasts.
