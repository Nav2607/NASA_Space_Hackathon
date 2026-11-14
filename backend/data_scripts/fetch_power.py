import json
import sys
import time
from pathlib import Path

import pandas as pd
import requests

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
ANCHORS_PATH = DATA_DIR / "anchors.json"
OUT_DIR = DATA_DIR / "anchors"

API = "https://power.larc.nasa.gov/api/temporal/daily/point"
START, END = "19810101", "20241231"

PARAMS = {
    "T2M_MAX": "tmax_c",
    "T2M_MIN": "tmin_c",
    "PRECTOTCORR": "precip_mm",
    "ALLSKY_SFC_SW_DWN": "solar_mj_m2",
    "RH2M": "rh_pct",
    "WS2M": "wind_m_s",
}


def load_anchors() -> dict[str, dict[str, float]]:
    with ANCHORS_PATH.open("r", encoding="utf-8") as fh:
        anchors = json.load(fh)
    return anchors


def fetch_point(lat: float, lon: float, retries: int = 3):
    params = {
        "parameters": ",".join(PARAMS),
        "community": "AG",
        "longitude": lon,
        "latitude": lat,
        "start": START,
        "end": END,
        "format": "JSON",
    }
    last_err = None
    for attempt in range(retries):
        try:
            response = requests.get(API, params=params, timeout=180)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as err:
            last_err = err
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"POWER request failed after {retries} tries: {last_err}")


def to_frame(payload):
    fill = payload.get("header", {}).get("fill_value", -999.0)
    series = payload["properties"]["parameter"]
    frame = pd.DataFrame(
        {PARAMS[name]: pd.Series(values) for name, values in series.items()}
    )
    frame = frame.where(frame != fill)
    frame.index = pd.to_datetime(frame.index, format="%Y%m%d")
    frame.index.name = "date"
    return frame.sort_index()


def save_anchor(anchor_id: str, lat: float, lon: float):
    print(f"Fetching {anchor_id} ({lat}, {lon}) ...")
    payload = fetch_point(lat, lon)
    frame = to_frame(payload)

    folder = OUT_DIR / anchor_id
    folder.mkdir(parents=True, exist_ok=True)
    frame.to_csv(folder / "weather.csv", index=True)

    units = payload.get("parameters", {})
    print(f"  rows: {len(frame)}  ({frame.index.min().date()} to {frame.index.max().date()})")
    print(f"  missing values per column:\n{frame.isna().sum().to_string()}")
    for key in PARAMS:
        print(f"  units {key}: {units.get(key, {}).get('units')}")
    time.sleep(1)


def main():
    anchors = load_anchors()
    requested = sys.argv[1:]
    ids = requested if requested else list(anchors)

    for anchor_id in ids:
        if anchor_id not in anchors:
            print(f"Unknown anchor '{anchor_id}'. Available anchors: {', '.join(sorted(anchors))}")
            continue
        entry = anchors[anchor_id]
        save_anchor(anchor_id, entry["lat"], entry["lon"])


if __name__ == "__main__":
    main()
