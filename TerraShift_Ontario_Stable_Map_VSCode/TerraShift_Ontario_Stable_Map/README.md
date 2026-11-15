# TerraShift — Ontario Map (Single-Image Basemap)

**Person 1 only.** No farm input form included. Design and farm photo from the prior TerraShift project are preserved.

## Running in VS Code
1. Open the extracted `TerraShift_Ontario_Stable_Map` folder.
2. Open `index.html` with your browser, or run a local server (recommended for external APIs).
3. If Live Server is installed, right-click `index.html` > Open with Live Server.
4. On Windows with Node installed: `npx --yes serve . -l 5500` then open http://localhost:5500.

## What changed
- Basemap now requests **one ArcGIS image per settled map view** using `MapServer/export`, rather than hundreds of small tiles.
- Old image remains on screen until the new one arrives; 20% view padding reduces blank edges while panning.
- If the image request fails entirely, a CARTO street-map fallback is attempted.
- AAFC annual crop classification overlay remains separate and optional.
- Address search, Ontario verification, map click, current location, shared event and hero photo are retained.

## Caveats
The map relies on public external imagery/geocoding services; no browser can guarantee zero network lag. If remote ArcGIS `export` is unavailable or denied, a CARTO fallback is used, and the UI says so. The crop layer may load slowly or be temporarily unavailable. Public endpoint use is subject to providers’ service terms and limits.

## Backend integration
The map dispatches `terrashift:location-selected` with `{lat,lon,name,anchorId,anchorName,distanceKm,cropYear}`. Backend climate anchors can be provided with `GET /api/anchors` or in `config.js`. Empty anchors are intentional—no invented data.

Use `config.js` for crop years and API base. The crop-year selector only controls the AAFC map layer, not planning year.
