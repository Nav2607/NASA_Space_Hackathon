"""Load cached weather and reference tables."""
import json
from pathlib import Path

import pandas as pd
import numpy as np

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def load_anchors():
    return json.loads((DATA_DIR / "anchors.json").read_text(encoding="utf-8"))


def load_weather(anchor_id):
    if anchor_id not in load_anchors():
        raise ValueError("Unknown anchor ID")
    path = DATA_DIR / "anchors" / anchor_id / "weather.csv"
    frame = pd.read_csv(path, parse_dates=["date"], index_col="date")
    if not frame.index.is_unique or not frame.index.is_monotonic_increasing:
        raise ValueError("Weather dates must be unique and chronological")
    return frame


def validate_weather(frame, start=None, end=None):
    """Require exact daily coverage and complete essential inputs; never impute."""
    if not isinstance(frame.index, pd.DatetimeIndex) or frame.empty:
        raise ValueError("Weather requires a nonempty daily date index")
    expected = pd.date_range(start or frame.index[0], end or frame.index[-1], freq="D")
    if not frame.index.equals(expected):
        raise ValueError("Weather dates must be complete, unique and chronological")
    required = ["tmax_c", "tmin_c", "precip_mm"]
    if not set(required) <= set(frame.columns):
        raise ValueError("Missing required weather columns")
    values = frame[required].to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("Missing or nonfinite essential weather inputs")
    if (frame.tmax_c < frame.tmin_c).any() or (frame.precip_mm < 0).any():
        raise ValueError("Require Tmax >= Tmin and precipitation >= 0")
    if (frame.tmin_c < -100).any() or (frame.tmax_c > 70).any():
        raise ValueError("Temperatures must be Celsius, within terrestrial bounds")
    return frame


def load_reference(name):
    """name: 'crops', 'soil_texture', 'rotation_rules' or 'sources'."""
    return json.loads((DATA_DIR / "reference" / f"{name}.json").read_text(encoding="utf-8"))


def complete_years(weather, columns=None):
    """Years in which every required column has a value on every day.

    The water model only runs on these years (decision: missing solar is never filled).
    """
    columns = columns or ["tmax_c", "tmin_c", "precip_mm", "solar_mj_m2", "rh_pct", "wind_m_s"]
    valid = []
    for year, group in weather.groupby(weather.index.year):
        expected = pd.date_range(f"{year}-01-01", f"{year}-12-31")
        if group.index.equals(expected) and np.isfinite(group[columns].to_numpy(float)).all():
            valid.append(int(year))
    return valid
