"""Load cached weather and reference tables."""
import json
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def load_anchors():
    return json.loads((DATA_DIR / "anchors.json").read_text(encoding="utf-8"))


def load_weather(anchor_id):
    path = DATA_DIR / "anchors" / anchor_id / "weather.csv"
    return pd.read_csv(path, parse_dates=["date"], index_col="date")


def load_reference(name):
    """name: 'crops', 'soil_texture', 'rotation_rules' or 'sources'."""
    return json.loads((DATA_DIR / "reference" / f"{name}.json").read_text(encoding="utf-8"))


def complete_years(weather, columns=None):
    """Years in which every required column has a value on every day.

    The water model only runs on these years (decision: missing solar is never filled).
    """
    columns = columns or ["tmax_c", "tmin_c", "precip_mm", "solar_mj_m2", "rh_pct", "wind_m_s"]
    ok = weather[columns].notna().all(axis=1)
    by_year = ok.groupby(weather.index.year).all()
    return [int(y) for y in by_year[by_year].index]
