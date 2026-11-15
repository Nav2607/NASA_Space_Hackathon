# Agronaut — Integrated Ontario prototype

**This project was assembled from the two ZIP files the team supplied.** Person 1's original interactive map, basemap/satellite mode, AAFC overlay, Ontario geocoding and hero photo remain. Person 2's farmer-input workflow has been adapted into Person 1's right sidebar. A new full-width climate-screening results section has been added.

## Quick start

Unzip the folder. Open the folder in VS Code. Right-click `index.html` and select **Open with Live Server**. Alternatively, from this folder run:

```bash
python -m http.server 5500
```

Then visit `http://localhost:5500`. **You need an internet connection** for Leaflet, geocoding, map imagery, AAFC imagery, and NASA POWER requests.

## What works

1. Search or click a location in Ontario. This is retained from Person 1.
2. In the **same right-hand panel**, enter crop sequence, a planning year, soil, irrigation, priorities, optional constraints and crop history. The form allows missing/unknown values and reports multiple validation errors.
3. Click **Compare rotation options**. The browser requests *real* NASA POWER historical daily precipitation, maximum temperature and minimum temperature for 2012–2025 at the selected coordinates. If the API fails, there is **no fake-data fallback**.
4. Under the map, compare your usual four-year pattern against up to three **predefined illustrative** rotation alternatives under all historical four-year weather sequences or the approximately driest 30% of those sequences.
5. Results include indicative reference ET × fixed crop coefficients, daily climate shortfall, rainfall, extreme-heat days, and scheduled crop days, with plain-language caveats and expandable methods.

## Scientific limitations — read before presenting

- **These are indicative climate screenings**, not validated crop water-balance or irrigation requirement predictions. The screen uses Hargreaves–Samani reference ET (FAO-56) and **fixed demonstrative coefficients**, rather than stage-specific FAO-56 crop Kc, soil reservoirs, observed soil moisture, crop yields, root depth or water-stress response.
- The `daily climate shortfall` = sum of positive (daily estimated crop demand minus daily precipitation). **It is NOT actual irrigation need**, drought survival, observed moisture deficit or yield loss. Rainfall/runoff/storage terms are not simulated.
- The preset crop dates are **unverified illustrative calendar assumptions**, not Ontario provincial crop recommendations. Farmer-entered dates are used when available. Seasonal plans shorter than four years repeat their sequence. Crop overlap is permitted, but agronomic feasibility is not checked.
- Results use **real NASA POWER historical data**, which are regional gridded estimates, not farm measurements. Dry seasons are retrospective choices from the dataset, **not forecasts**.
- Alternatives are **predefined example crop sequences, not optimized recommendations**. Must-grow and avoid crop constraints are applied to these examples; nitrogen, budgets, equipment, yields, costs and effective soil cover are **not evaluated**. If the farmer specifies these constraints, the results explicitly say so. AAFC raster is an optional map visualization; it is **not used to infer verified field crop history**.
- **NEX-GDDP-CMIP6 is not connected in this browser-only deliverable.** The 2050s toggle is disabled. It needs real preprocessed, bias-adjusted, model- and scenario-labelled daily projections, preferably an ensemble, before implementation. Do not imply future scenarios are calculated yet.
- The app is a **pilot oriented toward Southern Ontario**, but the retained Person 1 map can select other Ontario locations; validated locality filtering remains a follow-up task.

## Files

- `index.html`: integrated single-page application
- `styles.css`: original Person 1 theme + integrated input/results styles
- `app.js`: original Person 1 map and place selection, with small integration changes
- `farm-form.js`: compact Person 2 inputs, validation and dispatch
- `results.js`: historical daily NASA climate-screening results
- `config.js`: retained Person 1 anchor configuration
- `assets/ontario-farm-hero.png`: original supplied asset

## Interfaces / events

Person 1 triggers `agronaut:location-changed`, with `{ lat, lon, name, anchorId, anchorName, distanceKm, cropYear }`. Person 2 subscribes to this event and enables Compare when a location exists. Person 2 dispatches `agronaut:compare` with `detail = farmData` (which includes `location`, `currentRotation`, `constraints`, `priorities`). Person 3's `results.js` listens to this event.

## Team branch workflow — keep existing work safe

Your individual branches already exist, so **do not overwrite `frontend/index.html` or merge into `main` immediately**. Create a separate integration feature branch based on the latest team `frontend` branch and put this folder under `frontend/integrated-demo/`:

```bash
git fetch origin
git switch -c feature/terrashift-integration origin/frontend
# Copy the unzipped TerraShift_Integrated folder to frontend/integrated-demo/
git add frontend/integrated-demo/
git commit -m "Add integrated Agronaut map farmer inputs and climate screening"
git push -u origin feature/terrashift-integration
```

Open a PR with **base `frontend`**, compare `feature/terrashift-integration`. Get Person 1 and Person 3 to review. When ready, choose whether the team wants to replace the main entry `frontend/index.html`; do so **in a reviewed integration PR**, not on a teammate's branch.

## NASA sources

- Historical daily POWER endpoint: https://power.larc.nasa.gov/docs/tutorials/service-data-request/api/
- NEX-GDDP-CMIP6 dataset and access: https://www.nccs.nasa.gov/data-collections/nex-gddp-cmip6/
- FAO-56 reference ET: https://www.fao.org/4/x0490e/x0490e00.htm

### Why the future toggle is currently disabled

NEX-GDDP-CMIP6 is generally distributed as NetCDF via THREDDS/AWS, **not the same daily JSON API as POWER historical weather**. A backend must extract the selected location, choose SSP/model ensemble, harmonize units (K→°C, precipitation kg m⁻² s⁻¹→mm/day), collect a multiyear window, and serve the same normalized daily data schema. Only then should the toggle be enabled with explicit scenario and model uncertainty labels.


## Lightweight OpenFreeMap edition (2026-11-14)

This update removes the optional AAFC satellite crop overlay and imagery export requests completely.
The basemap now uses OpenFreeMap vector tiles through MapLibre GL JS, with **Map** (Liberty) and **Light** (Positron) styles. OpenFreeMap does **not** provide satellite aerial imagery; the former Satellite toggle was replaced with Light.
NASA POWER historical weather screening, farmer inputs, location selection, and results are unchanged.
The map needs internet and a WebGL-capable browser. Test through Live Server.
If a map remains blank, inspect developer tools Console/Network for failed tile, script, or WebGL loads; removing AAFC alone does not solve all possible failures.

Official map sources: https://openfreemap.org/ and https://openfreemap.org/quick_start/


## Backend integration (current)

Results now come from the Agronaut backend (`POST /recommend`), not from in-browser NASA POWER calls. `results.js` was replaced by `backend-results.js`; the older sections above describing the browser-only screening are historical.

Run everything with one command from the repo root, then open http://localhost:8000/ :

```bash
pip install -r backend/requirements.txt
python -m uvicorn backend.api.main:app --port 8000
```

If the page is served elsewhere (Live Server, port 5500), set `apiBase` in `config.js` (default `http://localhost:8000`). The "2031–2050 projection" button re-runs the model with NEX-GDDP-CMIP6 change factors. Form soils the backend lacks (sandy, silt loam, unknown) are mapped to the nearest one and the user is told.
