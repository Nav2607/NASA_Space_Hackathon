"""Soil-water bucket: daily root-zone water balance, shortfall and stress days.

FAO-56 style (Allen et al. 1998, ch. 8): the root zone holds TAW mm of plant-available
water (soil available water per metre x root depth). Rain refills it, crop demand (ETc)
empties it. Once the store falls below (1 - p) x TAW the crop is "stressed" and can only
transpire Ks x ETc, where Ks falls linearly to 0 at an empty store.

Simplifications (shown in the app as limitations):
- The store starts full at planting/spring greenup (soils are near field capacity after thaw).
- All rain infiltrates up to capacity; any excess is lost. No runoff, tile drainage,
  water table or capillary rise. No irrigation.
- Root depth is fixed at the midpoint of the FAO-56 range for the whole season.
"""
import numpy as np
import pandas as pd

from . import crop_water

SEVERE_SHORTFALL_FRACTION = 0.25   # ASSUMED: season counts as water-failed above this share of ETc unmet
HOT_DAY_C = 30.0                   # ASSUMED: generic "hot day" marker, not a crop-specific threshold


def run_bucket(etc, rain, taw, p, start_full=True):
    """Core daily loop. etc, rain: arrays (mm/day). Returns dict of daily arrays.

    stressed[i] is True when depletion exceeds the readily available water p x TAW
    (after that day's rain, before that day's crop demand).
    """
    etc, rain = np.asarray(etc, float), np.asarray(rain, float)
    raw = p * taw
    store = taw if start_full else 0.0
    n = len(etc)
    store_after = np.empty(n)
    eta = np.empty(n)
    stressed = np.zeros(n, dtype=bool)
    for i in range(n):
        store = min(store + rain[i], taw)
        depletion = taw - store
        if depletion > raw:
            stressed[i] = True
            ks = max(store / (taw - raw), 0.0) if taw > raw else 0.0
        else:
            ks = 1.0
        eta[i] = min(ks * etc[i], store)
        store -= eta[i]
        store_after[i] = store
    return {"store": store_after, "eta": eta, "stressed": stressed}


def season_dates(crop, year):
    """(start, end, plant_date) of the simulated season for a crop in a harvest year.

    Spring-planted crops run from planting to the earlier of the end of the FAO-56 cycle
    and the harvest-window midpoint. Fall-planted crops (winter wheat) are simulated only
    from spring greenup (1 April) to harvest, because soils are frozen and the crop is
    dormant over winter, so winter 'crop water use' would be meaningless.
    """
    days = crop.get("stage_days") or []
    if len(days) != 4 or any(d is None for d in days):
        return None
    plant = crop_water.plant_date_for_year(crop, year)
    if plant.month >= 8:   # fall planting: planted the year before
        plant = crop_water.plant_date_for_year(crop, year - 1)
        harvest = _midpoint(crop["harvest_window"], year)
        return pd.Timestamp(year, 4, 1), pd.Timestamp(harvest), pd.Timestamp(plant)
    end = pd.Timestamp(plant) + pd.Timedelta(days=sum(days) - 1)
    if crop.get("harvest_window"):
        end = min(end, pd.Timestamp(_midpoint(crop["harvest_window"], year)))
    return pd.Timestamp(plant), end, pd.Timestamp(plant)


def _midpoint(window, year):
    import datetime as dt
    a = dt.date(year, int(window[0][:2]), int(window[0][3:]))
    b = dt.date(year, int(window[1][:2]), int(window[1][3:]))
    return a + (b - a) / 2


def _in_window(index, window):
    if not window:
        return np.zeros(len(index), dtype=bool)
    md = index.strftime("%m-%d")
    return (md >= window[0]) & (md <= window[1])


def simulate_season(frame, crop, soil, year, return_daily=False):
    """One crop, one soil, one weather year.

    frame: daily DataFrame with tmax_c, precip_mm, et0_pm (see et0.et0_frame).
    Returns a dict of metrics, or None when the crop library lacks data or the season
    is not fully covered by complete weather (such years are skipped, never filled).
    """
    awc = soil.get("available_water_mm_per_m")
    depth = crop.get("root_depth_m") or [None, None]
    p = crop.get("depletion_fraction_p")
    dates = season_dates(crop, year)
    if awc is None or depth[0] is None or p is None or dates is None:
        return None
    start, end, plant = dates
    kc, notes = crop_water.kc_curve(crop, plant)
    if kc is None:
        return None
    window = frame.loc[start:end, ["tmax_c", "precip_mm", "et0_pm"]]
    if len(window) != (end - start).days + 1 or window.isna().any().any():
        return None
    kc_w = kc.reindex(window.index)
    if kc_w.isna().any():
        return None

    taw = awc * float(np.mean(depth))          # mm: (mm/m) x (m)
    etc = (kc_w * window["et0_pm"]).values
    bucket = run_bucket(etc, window["precip_mm"].values, taw, p)

    crit = _in_window(window.index, crop.get("critical_window"))
    if not crit.any():
        crit = np.ones(len(window), dtype=bool)
    thr = crop.get("heat_threshold_c")
    tmax = window["tmax_c"].values
    shortfall = float(etc.sum() - bucket["eta"].sum())

    out = {
        "year": int(year),
        "season_start": start.date().isoformat(),
        "season_end": end.date().isoformat(),
        "taw_mm": round(taw, 1),
        "etc_mm": float(etc.sum()),
        "eta_mm": float(bucket["eta"].sum()),
        "shortfall_mm": shortfall,
        "shortfall_pct": shortfall / float(etc.sum()) if etc.sum() > 0 else 0.0,
        "season_rain_mm": float(window["precip_mm"].sum()),
        "stress_days": int(bucket["stressed"].sum()),
        "stress_days_critical": int((bucket["stressed"] & crit).sum()),
        "heat_days_critical": int(((tmax >= thr) & crit).sum()) if thr is not None else None,
        "hot_days_30c_critical": int(((tmax >= HOT_DAY_C) & crit).sum()),
        "notes": notes,
    }
    if return_daily:
        out["daily"] = pd.DataFrame({
            "etc": etc, "eta": bucket["eta"], "store": bucket["store"],
            "rain": window["precip_mm"].values, "stressed": bucket["stressed"],
        }, index=window.index)
    return out


def simulate_years(frame, crop, soil, years):
    """Metrics for every usable year, as a DataFrame indexed by year (unusable years absent)."""
    rows = [r for y in years if (r := simulate_season(frame, crop, soil, y)) is not None]
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).set_index("year").drop(columns=["notes"])


def summarize(metrics):
    """Typical year (median) and dry year (90th percentile of seasonal shortfall).

    With only ~30 usable years the 90th percentile is roughly the 3rd-driest year; the app
    should call it 'a dry year (about 1 in 10)'. survival_rate = share of years whose
    unmet water demand stayed under SEVERE_SHORTFALL_FRACTION (assumed threshold).
    """
    if metrics.empty:
        return None
    dry_cut = metrics["shortfall_mm"].quantile(0.9)
    dry_years = metrics[metrics["shortfall_mm"] >= dry_cut]
    return {
        "n_years": int(len(metrics)),
        "etc_mm_typical": float(metrics["etc_mm"].median()),
        "shortfall_mm_typical": float(metrics["shortfall_mm"].median()),
        "shortfall_mm_dry": float(dry_cut),
        "stress_days_typical": float(metrics["stress_days"].median()),
        "stress_days_dry": float(dry_years["stress_days"].mean()),
        "stress_days_critical_typical": float(metrics["stress_days_critical"].median()),
        "heat_days_critical_typical": (None if metrics["heat_days_critical"].isna().all()
                                       else float(metrics["heat_days_critical"].median())),
        "hot_days_30c_critical_typical": float(metrics["hot_days_30c_critical"].median()),
        "survival_rate": float((metrics["shortfall_pct"] <= SEVERE_SHORTFALL_FRACTION).mean()),
        "survived_years": int((metrics["shortfall_pct"] <= SEVERE_SHORTFALL_FRACTION).sum()),
    }
