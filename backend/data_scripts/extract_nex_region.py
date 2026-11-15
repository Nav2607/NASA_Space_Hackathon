"""Extract NEX-GDDP-CMIP6 climate-change deltas for ALL of Southern Ontario (a 0.25 degree grid).

Instead of one point, this pulls the whole region as a grid, so any map click can be served.
For each model, grid cell and calendar month it computes how much the future differs from a
historical baseline of the SAME model (this removes the model's own bias):

    tmax_c, tmin_c : future mean minus baseline mean (degrees C)
    pr_ratio       : future mean daily rain divided by baseline mean daily rain

The deltas are meant to be applied to observed-style NASA POWER weather ("delta method").
Each climate model is kept separate; an ensemble median is added for convenience.
Results are PROJECTED climate, not observed weather.

Run from the repo root:
    python backend/data_scripts/extract_nex_region.py                  # ssp245, 2041-2060
    python backend/data_scripts/extract_nex_region.py --scenario ssp585
Raw downloads are reduced to monthly means and cached in .nex-cache/region/, so a re-run resumes.
Source: https://ds.nccs.nasa.gov/thredds/catalog/AMES/NEX/GDDP-CMIP6/catalog.html
"""
import argparse
import concurrent.futures
import datetime as dt
import io
import json
import pathlib
import re
import threading
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

import numpy as np
from scipy.io import netcdf_file

BASE = "https://ds.nccs.nasa.gov/thredds/"
NS = {"t": "http://www.unidata.ucar.edu/namespaces/thredds/InvCatalog/v1.0"}
MODELS = ["ACCESS-CM2", "MPI-ESM1-2-HR", "MRI-ESM2-0"]
VARIABLES = {"tasmax": "tmax_c", "tasmin": "tmin_c", "pr": "pr"}
BBOX = {"north": 45.8, "south": 41.6, "east": -74.4, "west": -83.6}   # Southern Ontario plus margin
CACHE = pathlib.Path(".nex-cache") / "region"

_catalogs, _catalog_lock = {}, threading.Lock()


def download(url, timeout=240, tries=4):
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as response:
                return response.read()
        except Exception:
            if attempt == tries - 1:
                raise
            time.sleep(3 * (attempt + 1))


def dataset_path(model, experiment, variable, year):
    key = (model, experiment, variable)
    with _catalog_lock:
        if key not in _catalogs:
            url = f"{BASE}catalog/AMES/NEX/GDDP-CMIP6/{model}/{experiment}/r1i1p1f1/{variable}/catalog.xml"
            _catalogs[key] = ET.fromstring(download(url, timeout=60))
    name = f"{variable}_day_{model}_{experiment}_r1i1p1f1_gn_{year}_v2.0.nc"
    paths = [d.attrib["urlPath"] for d in _catalogs[key].findall(".//t:dataset", NS) if d.attrib.get("name") == name]
    if len(paths) != 1:
        raise ValueError(f"Dataset not found: {name}")
    return paths[0]


def monthly_means(model, experiment, variable, year):
    """Download one model-variable-year for the region and reduce it to 12 monthly means per cell.

    Returns (lat, lon_minus180_180, array[12, lat, lon]); temperature in degC, rain in mm/day.
    """
    cache = CACHE / model / experiment / f"{variable}_{year}.npz"
    if cache.exists():
        z = np.load(cache)
        return z["lat"], z["lon"], z["monthly"]

    query = urllib.parse.urlencode({
        "var": variable, **BBOX, "accept": "netcdf",
        "time_start": f"{year}-01-01T00:00:00Z", "time_end": f"{year}-12-31T23:59:59Z",
    })
    raw = download(BASE + "ncss/grid/" + dataset_path(model, experiment, variable, year) + "?" + query)
    with netcdf_file(io.BytesIO(raw), mmap=False) as nc:
        lat = np.array(nc.variables["lat"][:], dtype=float)
        lon = np.array(nc.variables["lon"][:], dtype=float)
        data = np.array(nc.variables[variable][:], dtype=float)
        time_var = nc.variables["time"]
        units = time_var.units.decode() if isinstance(time_var.units, bytes) else time_var.units
        times = np.array(time_var[:], dtype=float)
    lon = np.where(lon > 180, lon - 360, lon)

    # time axis -> calendar month
    m = re.search(r"since\s+(\d+)-(\d+)-(\d+)(?:[ T]+(\d+):(\d+):(\d+))?", units)   # models differ: '1850-01-01' vs '1850-1-1 00:00:00'
    if not m:
        raise ValueError(f"Cannot read time units: {units!r}")
    since = dt.datetime(*(int(g or 0) for g in m.groups()))
    months = np.array([(since + dt.timedelta(days=float(t))).month for t in times])
    days_in_year = 366 if (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)) else 365
    if data.ndim != 3 or len(times) != days_in_year or {*months} != set(range(1, 13)):
        raise ValueError(f"Unexpected time axis for {model} {variable} {year}: {len(times)} days")
    data[data > 1e19] = np.nan

    if variable == "pr":
        if np.nanmin(data) < 0 or np.nanmax(data) >= 1:
            raise ValueError("Invalid precipitation flux")
        data = data * 86400
    else:
        if not 150 < np.nanmin(data) < np.nanmax(data) < 350:
            raise ValueError("Invalid temperature")
        data = data - 273.15

    monthly = np.stack([np.nanmean(data[months == m], axis=0) for m in range(1, 13)])
    cache.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(cache, lat=lat, lon=lon, monthly=monthly)
    return lat, lon, monthly


def nested(arr):
    """[month, lat, lon] -> [lat][lon][month] list with NaN as null."""
    out = np.round(np.transpose(arr, (1, 2, 0)), 3)
    return [[[None if np.isnan(v) else float(v) for v in cell] for cell in row] for row in out]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", choices=["ssp245", "ssp585"], default="ssp245")
    parser.add_argument("--baseline", type=int, nargs=2, default=[1995, 2014])
    parser.add_argument("--future", type=int, nargs=2, default=[2041, 2060])
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--output")
    args = parser.parse_args()
    b0, b1 = args.baseline
    f0, f1 = args.future
    if not (1981 <= b0 <= b1 <= 2014 and 2015 <= f0 <= f1 <= 2100):
        parser.error("baseline must lie in 1981-2014 and future in 2015-2100")
    output = pathlib.Path(args.output or f"backend/data/nex/delta_{args.scenario}_{f0}_{f1}.json")

    jobs = [(model, exp, var, year)
            for model in MODELS for var in VARIABLES
            for exp, years in (("historical", range(b0, b1 + 1)), (args.scenario, range(f0, f1 + 1)))
            for year in years]
    results, failures, started = {}, [], time.time()
    print(f"{len(jobs)} requests, {args.workers} at a time (cached ones are instant)", flush=True)

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(monthly_means, *job): job for job in jobs}
        for n, future in enumerate(concurrent.futures.as_completed(futures), 1):
            job = futures[future]
            try:
                results[job] = future.result()
            except Exception as err:
                failures.append((job, str(err)))
                print(f"FAILED {job}: {err}", flush=True)
            if n % 10 == 0 or n == len(jobs):
                print(f"{n}/{len(jobs)} done, {time.time() - started:.0f}s", flush=True)
    if failures:
        raise SystemExit(f"{len(failures)} requests failed; re-run to retry (finished ones are cached).")

    grid = {(tuple(lat), tuple(lon)) for lat, lon, _ in results.values()}
    if len(grid) != 1:
        raise SystemExit("Models/variables use different grids: cannot combine without regridding")
    lat, lon = (np.array(g) for g in next(iter(grid)))

    deltas, summary = {}, {}
    for model in MODELS:
        deltas[model] = {}
        for var, name in VARIABLES.items():
            base = np.mean([results[(model, "historical", var, y)][2] for y in range(b0, b1 + 1)], axis=0)
            fut = np.mean([results[(model, args.scenario, var, y)][2] for y in range(f0, f1 + 1)], axis=0)
            if var == "pr":
                ratio = np.where(base > 0.02, fut / np.maximum(base, 1e-9), np.nan)   # skip near-zero baselines
                deltas[model]["pr_ratio"] = ratio
            else:
                deltas[model][f"{name}_delta"] = fut - base

    keys = list(next(iter(deltas.values())))
    ensemble = {k: np.nanmedian([deltas[m][k] for m in MODELS], axis=0) for k in keys}

    doc = {
        "dataset": "NEX-GDDP-CMIP6", "version": "2.0", "source_type": "Projected",
        "method": "delta change: per model, future monthly mean minus (temperature) or divided by (rain) the same model's baseline",
        "scenario": args.scenario, "member": "r1i1p1f1",
        "baseline_period": {"start": b0, "end": b1}, "future_period": {"start": f0, "end": f1},
        "region_bbox": BBOX, "resolution_deg": 0.25,
        "extracted_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "units": {"tmax_c_delta": "degC change", "tmin_c_delta": "degC change", "pr_ratio": "future/baseline mean daily rain (1.0 = no change)"},
        "layout": "variable[lat_index][lon_index][month-1]; null = no value",
        "lat": [round(float(v), 4) for v in lat], "lon": [round(float(v), 4) for v in lon],
        "models": {m: {k: nested(v) for k, v in deltas[m].items()} for m in MODELS},
        "ensemble_median": {k: nested(v) for k, v in ensemble.items()},
        "note": "Projected climate, not observed weather. Models disagree; show the spread, not just the median.",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, allow_nan=False, separators=(",", ":")) + "\n", encoding="utf-8")
    tmp.replace(output)
    print(f"Saved {output} ({output.stat().st_size / 1e6:.2f} MB); grid {len(lat)} x {len(lon)} cells")


if __name__ == "__main__":
    main()
