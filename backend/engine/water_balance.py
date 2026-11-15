"""Daily mass-conserving bucket and compatibility helpers.

The authoritative rotation path is rotation_simulation.simulate_rotation.
Uptake is min(demand, storage + rain); excess after uptake drains. A depletion
threshold is reported separately. The compatibility key ks is the actual/demand
ratio, not a FAO stress-reduction function. No inferred survival metrics.
"""
import numpy as np
import pandas as pd

def run_bucket(etc, rain, taw, p=0.5, start_full=True, initial_storage=None):
    """Core daily loop. etc, rain: arrays (mm/day). Returns dict of daily arrays.

    stressed[i] is True when depletion exceeds the readily available water p x TAW
    (after that day's rain, before that day's crop demand).
    """
    etc, rain = np.asarray(etc, float), np.asarray(rain, float)
    if etc.ndim != 1 or rain.shape != etc.shape or not len(etc):
        raise ValueError("Demand and precipitation must be equal nonempty 1D arrays")
    if not np.isfinite(etc).all() or not np.isfinite(rain).all() or (etc < 0).any() or (rain < 0).any():
        raise ValueError("Demand and precipitation must be finite and nonnegative")
    if not np.isfinite(taw) or taw <= 0 or not np.isfinite(p) or not 0 <= p <= 1:
        raise ValueError("Capacity must be positive and depletion fraction within [0,1]")
    raw = p * taw
    store = (taw if start_full else 0.0) if initial_storage is None else float(initial_storage)
    if not np.isfinite(store) or not 0 <= store <= taw:
        raise ValueError("Initial storage must be within [0, capacity]")
    n = len(etc)
    store_after = np.empty(n)
    eta = np.empty(n)
    ks_out = np.ones(n)
    stressed = np.zeros(n, dtype=bool)
    initial = np.empty(n)
    drainage = np.empty(n)
    for i in range(n):
        initial[i] = store
        available = store + rain[i]
        # Depletion threshold is a separate indicator; it does not change uptake.
        stressed[i] = taw - min(available, taw) > raw and etc[i] > 0
        eta[i] = min(etc[i], available)
        ks_out[i] = eta[i] / etc[i] if etc[i] else 1.0
        drainage[i] = max(0.0, available - eta[i] - taw)
        store = available - eta[i] - drainage[i]
        store_after[i] = store
    residual = initial + rain - eta - drainage - store_after
    if not np.allclose(residual, 0, atol=1e-9, rtol=0):
        raise ArithmeticError("Daily water mass balance failed")
    return {"store": store_after, "initial_store": initial, "eta": eta,
            "shortfall": etc - eta, "drainage": drainage,
            "mass_balance_error": residual, "stressed": stressed, "ks": ks_out}



def _single_run(frame, crop, soil, first, last, daily=False):
    from .rotation_simulation import simulate_rotation
    from .crop_water import kc_curve
    curve, _ = kc_curve(crop, pd.Timestamp(first, 1, 1).date())
    if curve is None:
        return None
    return simulate_rotation(frame, frame.attrs["latitude"], (("crop", None),),
                             {"crop": crop}, soil, first, last, return_daily=daily)


def simulate_season(frame, crop, soil, year, return_daily=False):
    """Single-crop diagnostic with previous-year warm-up; not rotation scoring.

    Callers must supply latitude in frame.attrs to avoid assuming another anchor.
    """
    from .rotation_simulation import crop_dates
    if "latitude" not in frame.attrs:
        raise ValueError("Single-crop diagnostic requires frame.attrs['latitude']")
    run = _single_run(frame, crop, soil, year, year, daily=True)
    if run is None:
        return None
    plant, harvest = crop_dates("crop", "crop", year, {"crop": crop})
    daily = run["phases"][0]["daily"].loc[plant:harvest]
    result = {"year": year, "season_start": plant.date().isoformat(),
              "season_end": harvest.date().isoformat(), "etc_mm": float(daily.demand_mm.sum()),
              "eta_mm": float(daily.actual_et_mm.sum()), "shortfall_mm": float(daily.shortfall_mm.sum()),
              "notes": run["assumptions"], "et0_method": run["et0_method"]}
    if return_daily:
        result["daily"] = daily
    return result


def simulate_years(frame, crop, soil, years):
    """Single-crop *continuous annual* diagnostic; never average crops into rotations."""
    if "latitude" not in frame.attrs:
        raise ValueError("Single-crop diagnostic requires frame.attrs['latitude']")
    years = list(years)
    if not years:
        return pd.DataFrame()
    if years != list(range(years[0], years[-1]+1)):
        raise ValueError("Continuous diagnostics require contiguous years")
    run = _single_run(frame, crop, soil, years[0], years[-1])
    if run is None:
        return pd.DataFrame()
    return pd.DataFrame(run["phases"][0]["annual"]).set_index("year").rename(
        columns={"demand_mm": "etc_mm", "actual_et_mm": "eta_mm"})


def summarize(metrics):
    if metrics.empty:
        return None
    return {"n_years": len(metrics), "etc_mm_typical": float(metrics.etc_mm.median()),
            "actual_et_mm_typical": float(metrics.eta_mm.median()),
            "shortfall_mm_typical": float(metrics.shortfall_mm.median()),
            "shortfall_mm_dry": float(metrics.shortfall_mm.quantile(.9)),
            "unmet_demand_days_typical": float(metrics.unmet_demand_days.median())}
