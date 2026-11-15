"""Projected-climate lookups for ANY point in Southern Ontario (NEX-GDDP-CMIP6 delta grid).

Data comes from data_scripts/extract_nex_region.py. Deltas are PROJECTED climate changes,
per model and calendar month, on a 0.25 degree (~25 km) grid. Typical use:

    d = deltas_at(43.55, -80.25)                        # ensemble median + model spread
    future = apply_deltas(weather_df, d["median"])      # 'what if the 2050s looked like this'

Limits (show them in the app): the grid is coarse, models disagree (use the spread), and
applying monthly deltas changes only temperature and rain. Humidity, wind and sunlight keep
their historical values, so for projected evaporation prefer the Hargreaves column (needs
only temperature) over Penman-Monteith.
"""
import json
from functools import lru_cache
from pathlib import Path

import numpy as np

NEX_DIR = Path(__file__).resolve().parents[1] / "data" / "nex"
VARIABLES = ("tmax_c_delta", "tmin_c_delta", "pr_ratio")
MAX_EDGE_DEG = 0.2     # how far outside the grid a point may be before it is refused


class OutsideGridError(ValueError):
    pass


def available_files():
    return sorted(p.name for p in NEX_DIR.glob("delta_*.json"))


@lru_cache(maxsize=4)
def load_grid(scenario="ssp245", period="2041_2060"):
    path = NEX_DIR / f"delta_{scenario}_{period}.json"
    if not path.exists():
        raise FileNotFoundError(f"{path.name} not found. Run data_scripts/extract_nex_region.py --scenario {scenario}")
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["_lat"], doc["_lon"] = np.array(doc["lat"]), np.array(doc["lon"])
    return doc


def nearest_cell(doc, lat, lon):
    la, lo = doc["_lat"], doc["_lon"]
    if lat < la.min() - MAX_EDGE_DEG or lat > la.max() + MAX_EDGE_DEG \
            or lon < lo.min() - MAX_EDGE_DEG or lon > lo.max() + MAX_EDGE_DEG:
        raise OutsideGridError("Point is outside the Southern Ontario climate grid")
    i, j = int(np.abs(la - lat).argmin()), int(np.abs(lo - lon).argmin())
    return i, j, float(la[i]), float(lo[j])


def _cell(block, i, j):
    """{var: [12 monthly values]} for one grid cell; null -> NaN."""
    return {v: np.array([np.nan if x is None else x for x in block[v][i][j]]) for v in VARIABLES}


def deltas_at(lat, lon, scenario="ssp245", period="2041_2060"):
    """Monthly deltas at a point: per model, the ensemble median, and the spread across models.

    Returns a dict with: cell (grid centre used), scenario, periods, models {name: {var: [12]}},
    median {var: [12]}, spread {var: {"min": [12], "max": [12]}}. Missing values are None.
    """
    doc = load_grid(scenario, period)
    i, j, clat, clon = nearest_cell(doc, lat, lon)
    models = {m: _cell(block, i, j) for m, block in doc["models"].items()}
    median = _cell(doc["ensemble_median"], i, j)
    spread = {v: {"min": np.nanmin([models[m][v] for m in models], axis=0),
                  "max": np.nanmax([models[m][v] for m in models], axis=0)} for v in VARIABLES}

    def clean(x):
        return None if x is None else [None if np.isnan(v) else round(float(v), 3) for v in x]
    return {
        "cell": {"lat": clat, "lon": clon, "distance_deg": round(float(np.hypot(lat - clat, lon - clon)), 3)},
        "scenario": doc["scenario"], "baseline_period": doc["baseline_period"], "future_period": doc["future_period"],
        "source_type": doc["source_type"], "method": doc["method"],
        "models": {m: {v: clean(a) for v, a in d.items()} for m, d in models.items()},
        "median": {v: clean(a) for v, a in median.items()},
        "spread": {v: {k: clean(a) for k, a in d.items()} for v, d in spread.items()},
    }


def apply_deltas(weather, deltas):
    """Return a copy of a POWER weather frame shifted by one set of monthly deltas.

    deltas: {"tmax_c_delta": [12], "tmin_c_delta": [12], "pr_ratio": [12]} (e.g. d["median"]).
    Temperatures are shifted, rain is scaled, tmin is kept at or below tmax. Months with a
    missing delta are left unchanged.
    """
    month = weather.index.month.values - 1
    out = weather.copy()
    dmax = np.array([0.0 if v is None else v for v in deltas["tmax_c_delta"]])[month]
    dmin = np.array([0.0 if v is None else v for v in deltas["tmin_c_delta"]])[month]
    ratio = np.array([1.0 if v is None else v for v in deltas["pr_ratio"]])[month]
    out["tmax_c"] = weather["tmax_c"] + dmax
    out["tmin_c"] = np.minimum(weather["tmin_c"] + dmin, out["tmax_c"])
    out["precip_mm"] = weather["precip_mm"] * ratio
    return out
