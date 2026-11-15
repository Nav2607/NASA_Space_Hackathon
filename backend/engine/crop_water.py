"""Crop coefficient curve and crop water use (ETc = Kc x ET0), FAO-56 single-Kc method."""
import datetime as dt

import numpy as np
import pandas as pd

# FAO-56 Table 12 gives no Kc ini for maize and soybean in the text we could read.
# FAO-56 quotes Kc ini between about 0.1 and 1.15 depending on wetting, 0.3-0.4 is
# typical for grain crops. Used only when crops.json has null, and always reported.
DEFAULT_KC_INI = 0.4


def _scalar(value):
    """kc.end may be a [low, high] range: use the midpoint."""
    if isinstance(value, (list, tuple)):
        return float(np.mean(value))
    return None if value is None else float(value)


def kc_curve(crop, plant_date):
    """Daily Kc for one crop planted on plant_date.

    Returns (Series indexed by date, list of assumptions used) or (None, reasons) when
    the crop library lacks what is needed (e.g. cereal rye, red clover).
    """
    days = crop.get("stage_days") or []
    kc = crop.get("kc") or {}
    if len(days) != 4 or any(d is None for d in days):
        return None, ["no stage lengths in the crop library"]
    if kc.get("mid") is None or kc.get("end") is None:
        return None, ["no mid/end crop coefficient in the crop library"]

    notes = []
    kc_ini = _scalar(kc.get("ini"))
    if kc_ini is None:
        kc_ini = DEFAULT_KC_INI
        notes.append(f"Kc initial not in the library, assumed {DEFAULT_KC_INI}")
    kc_mid, kc_end = _scalar(kc["mid"]), _scalar(kc["end"])
    if isinstance(kc["end"], (list, tuple)):
        notes.append("Kc end given as a range, midpoint used")

    l_ini, l_dev, l_mid, l_late = days
    total = sum(days)
    d = np.arange(total)
    values = np.empty(total)
    values[d < l_ini] = kc_ini
    m = (d >= l_ini) & (d < l_ini + l_dev)
    values[m] = kc_ini + (kc_mid - kc_ini) * (d[m] - l_ini + 0.5) / l_dev
    m = (d >= l_ini + l_dev) & (d < l_ini + l_dev + l_mid)
    values[m] = kc_mid
    m = d >= l_ini + l_dev + l_mid
    values[m] = kc_mid + (kc_end - kc_mid) * (d[m] - (l_ini + l_dev + l_mid) + 0.5) / l_late

    index = pd.date_range(pd.Timestamp(plant_date), periods=total, freq="D")
    return pd.Series(values, index=index, name="kc"), notes


def plant_date_for_year(crop, year):
    """Midpoint of the crop's planting window, in the given year."""
    start, end = crop["plant_window"]
    a = dt.date(year, int(start[:2]), int(start[3:]))
    b = dt.date(year, int(end[:2]), int(end[3:]))
    return a + (b - a) / 2


def season_etc(et0, crop, plant_date):
    """Crop water use over one season.

    et0: daily ET0 Series (mm/day). Returns dict with total mm and daily series, or
    None for the total if any season day lacks ET0 (that year is then not usable).
    """
    kc, notes = kc_curve(crop, plant_date)
    if kc is None:
        return {"etc_mm": None, "daily": None, "notes": notes}
    window = et0.reindex(kc.index)
    if window.isna().any():
        return {"etc_mm": None, "daily": None, "notes": notes + ["season not fully covered by ET0 data"]}
    daily = kc * window
    return {"etc_mm": float(daily.sum()), "daily": daily, "notes": notes}


def seasonal_etc_by_year(et0, crop, years):
    """Seasonal ETc (mm) for each planting year; NaN where the season is not fully covered."""
    rows = {}
    for year in years:
        rows[year] = season_etc(et0, crop, plant_date_for_year(crop, year))["etc_mm"]
    return pd.Series(rows, name="etc_mm", dtype=float)
