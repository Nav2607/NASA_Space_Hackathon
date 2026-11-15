"""Projected-climate lookups for ANY point in Southern Ontario (NEX-GDDP-CMIP6 delta grid).

Data comes from data_scripts/extract_nex_region.py. Deltas are PROJECTED climate changes,
per model and calendar month, on a 0.25 degree (~25 km) grid. Typical use:

    d = deltas_at(43.55, -80.25)                        # ensemble median + model spread
    future = {model: apply_deltas(weather_df, values) for model, values in d["models"].items()}

Limits (show them in the app): the grid is coarse, models disagree (use the spread), and
applying monthly deltas changes only temperature and rain. Humidity, wind and sunlight keep
their historical values. The corrected engine uses Hargreaves consistently for
both historical and future simulations, not those unchanged auxiliary fields.
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
def load_grid(scenario="ssp245", period="2031_2050"):
    if scenario not in {"ssp245", "ssp585"} or period not in {"2031_2050", "2041_2060"}:
        raise ValueError("Unsupported scenario or period")
    path = NEX_DIR / f"delta_{scenario}_{period}.json"
    if not path.exists():
        raise FileNotFoundError(f"{path.name} not found. Run data_scripts/extract_nex_region.py --scenario {scenario}")
    doc = json.loads(path.read_text(encoding="utf-8"))
    first, last = map(int, period.split("_"))
    if (doc["dataset"] != "NEX-GDDP-CMIP6" or doc["version"] != "2.0"
            or doc["scenario"] != scenario
            or doc["source_type"] != "Projected"
            or doc["future_period"] != {"start": first, "end": last}
            or doc["units"]["tmax_c_delta"] != "degC change"
            or doc["units"]["tmin_c_delta"] != "degC change"
            or not doc["units"]["pr_ratio"].startswith("future/baseline")
            or not doc["models"]):
        raise ValueError("Invalid climate dataset metadata")
    doc["_lat"], doc["_lon"] = np.array(doc["lat"]), np.array(doc["lon"])
    for axis, limit in ((doc["_lat"],90), (doc["_lon"],180)):
        if (axis.ndim != 1 or len(axis) < 1 or not np.isfinite(axis).all()
                or np.any(np.abs(axis) > limit) or len(np.unique(axis)) != len(axis)):
            raise ValueError("Invalid climate grid coordinates")
    for block in [*doc["models"].values(), doc["ensemble_median"]]:
        variables = list(VARIABLES)
        if "dtr_ratio" in block:
            variables.append("dtr_ratio")
        for var in variables:
            if np.asarray(block[var], dtype=float).shape != (len(doc["_lat"]),len(doc["_lon"]),12):
                raise ValueError("Invalid climate grid dimensions")
    return doc


def nearest_cell(doc, lat, lon):
    if not np.isfinite(lat) or not np.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise OutsideGridError("Invalid coordinates")
    la, lo = doc["_lat"], doc["_lon"]
    if lat < la.min() - MAX_EDGE_DEG or lat > la.max() + MAX_EDGE_DEG \
            or lon < lo.min() - MAX_EDGE_DEG or lon > lo.max() + MAX_EDGE_DEG:
        raise OutsideGridError("Point is outside the Southern Ontario climate grid")
    i, j = int(np.abs(la - lat).argmin()), int(np.abs(lo - lon).argmin())
    return i, j, float(la[i]), float(lo[j])


def _cell(block, i, j):
    """{var: [12 monthly values]} for one grid cell; null -> NaN."""
    variables = (*VARIABLES, "dtr_ratio") if "dtr_ratio" in block else VARIABLES
    return {v: np.array([np.nan if x is None else x for x in block[v][i][j]]) for v in variables}


def deltas_at(lat, lon, scenario="ssp245", period="2031_2050"):
    """Monthly deltas at a point: per model, the ensemble median, and the spread across models.

    Returns a dict with: cell (grid centre used), scenario, periods, models {name: {var: [12]}},
    median {var: [12]}, spread {var: {"min": [12], "max": [12]}}. Missing values are None.
    """
    doc = load_grid(scenario, period)
    i, j, clat, clon = nearest_cell(doc, lat, lon)
    models = {m: _cell(block, i, j) for m, block in doc["models"].items()}
    median = _cell(doc["ensemble_median"], i, j)
    spread = {v: {"min": np.nanmin([models[m][v] for m in models], axis=0),
                  "max": np.nanmax([models[m][v] for m in models], axis=0)} for v in median}

    def clean(x):
        return None if x is None else [None if np.isnan(v) else round(float(v), 3) for v in x]
    return {
        "dataset": doc["dataset"], "version": doc["version"], "member": doc["member"],
        "source_url": doc.get("source_url", "https://ds.nccs.nasa.gov/thredds/catalog/AMES/NEX/GDDP-CMIP6/catalog.html"),
        "cell": {"lat": clat, "lon": clon, "distance_deg": round(float(np.hypot(lat - clat, lon - clon)), 3)},
        "scenario": doc["scenario"], "baseline_period": doc["baseline_period"], "future_period": doc["future_period"],
        "source_type": doc["source_type"], "method": doc["method"],
        "models": {m: {v: clean(a) for v, a in d.items()} for m, d in models.items()},
        "median": {v: clean(a) for v, a in median.items()},
        "spread": {v: {k: clean(a) for k, a in d.items()} for v, d in spread.items()},
    }


def apply_deltas(weather, deltas):
    """Return a copy of a POWER weather frame shifted by one set of monthly deltas.

    deltas: one model's monthly values (e.g. d["models"]["ACCESS-CM2"]), not ensemble inputs.
    Rain is scaled. New caches apply the model mean-temperature change and DTR
    ratio, preserving temperature order. Retained legacy caches without DTR use
    additive Tmin/Tmax shifts and reject inversions. Missing deltas are errors.
    """
    month = weather.index.month.values - 1
    out = weather.copy()
    arrays = {v: np.asarray(deltas[v], dtype=float) for v in VARIABLES}
    if any(a.shape != (12,) or not np.isfinite(a).all() for a in arrays.values()):
        raise ValueError("Missing/invalid monthly climate deltas; no no-change substitution allowed")
    if (arrays["pr_ratio"] < 0).any():
        raise ValueError("Precipitation ratios must be nonnegative")
    dmax, dmin, ratio = (arrays[v][month] for v in VARIABLES)
    out["tmax_c"] = weather["tmax_c"] + dmax
    out["tmin_c"] = weather["tmin_c"] + dmin
    if "dtr_ratio" in deltas:
        dtr = np.asarray(deltas["dtr_ratio"], dtype=float)
        if dtr.shape != (12,) or not np.isfinite(dtr).all() or (dtr < 0).any():
            raise ValueError("Missing or invalid modeled diurnal temperature range ratios")
        # Additive Tmax/Tmin deltas can invert small observed ranges. Instead,
        # preserve source model changes in mean temperature and relative DTR.
        centre = (weather["tmax_c"] + weather["tmin_c"] + dmax + dmin)/2
        width = (weather["tmax_c"] - weather["tmin_c"])*dtr[month]
        out["tmax_c"], out["tmin_c"] = centre + width/2, centre - width/2
        out.attrs["temperature_adjustment"] = "Additive model mean-temperature change, multiplicative model DTR change; no clipping"
    if (out["tmin_c"] > out["tmax_c"]).any():
        raise ValueError("Delta-adjusted Tmin exceeds Tmax; no silent temperature clipping")
    out["precip_mm"] = weather["precip_mm"] * ratio
    return out
