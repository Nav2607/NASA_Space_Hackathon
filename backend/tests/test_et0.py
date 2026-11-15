"""ET0 and crop water tests. Run from the repo root: python -m pytest backend/tests"""
import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine import crop_water, et0
from engine.weather import complete_years, load_reference, load_weather


def test_fao56_example_18_brussels():
    """FAO-56 Example 18 (Brussels, 6 July, 100 m, 50.80 N): published ET0 about 3.9 mm/day.

    Published intermediates, recalled from the guideline: es 1.997 kPa, ea 1.409 kPa,
    Ra about 41.1 MJ/m2/day. Inputs: Tmax 21.5, Tmin 12.3, u2 2.078 m/s, Rs 22.07 MJ/m2/day.
    """
    ra = et0.extraterrestrial_radiation(50.80, 187)
    assert ra == pytest.approx(41.1, abs=0.3)
    value = et0.et0_penman_monteith(21.5, 12.3, None, 2.078, 22.07, 50.80, 187,
                                    elevation_m=100, ea=1.409)
    assert float(value) == pytest.approx(3.9, abs=0.1)


def test_hargreaves_close_to_pm_in_typical_summer():
    pm = et0.et0_penman_monteith(26, 14, 70, 2.0, 22, 43.5, 190)
    hg = et0.et0_hargreaves(26, 14, 43.5, 190)
    assert 3 < float(pm) < 6 and 3 < float(hg) < 7


def test_missing_solar_gives_nan_not_a_guess():
    value = et0.et0_penman_monteith(20, 10, 70, 2.0, np.nan, 43.5, 150)
    assert np.isnan(value)


def test_kc_curve_shape_and_length():
    corn = load_reference("crops")["corn"]
    kc, notes = crop_water.kc_curve(corn, dt.date(2020, 5, 10))
    assert len(kc) == sum(corn["stage_days"])
    assert kc.iloc[0] == pytest.approx(corn["kc"]["ini"])
    assert kc.max() == pytest.approx(1.20)
    assert kc.iloc[-1] < kc.max()
    assert corn["kc"]["ini"] == 0.30  # FAO Table 12 inherited cereal value, no fallback


def test_crop_without_data_returns_none():
    rye = load_reference("crops")["cereal_rye"]
    kc, notes = crop_water.kc_curve(rye, dt.date(2020, 9, 1))
    assert kc is None and notes


def test_constant_et0_gives_expected_total():
    soy = load_reference("crops")["soybean"]
    idx = pd.date_range("2020-01-01", "2021-12-31")
    et0_flat = pd.Series(4.0, index=idx)
    kc, _ = crop_water.kc_curve(soy, dt.date(2020, 5, 20))
    out = crop_water.season_etc(et0_flat, soy, dt.date(2020, 5, 20))
    assert out["etc_mm"] == pytest.approx(4.0 * kc.sum())


def test_season_with_gap_is_not_usable():
    corn = load_reference("crops")["corn"]
    idx = pd.date_range("2020-01-01", "2021-12-31")
    et0_gap = pd.Series(4.0, index=idx)
    et0_gap.loc["2020-07-01"] = np.nan
    assert crop_water.season_etc(et0_gap, corn, dt.date(2020, 5, 10))["etc_mm"] is None


def test_real_anchor_end_to_end():
    weather = load_weather("guelph")
    years = complete_years(weather)
    assert years and min(years) >= 1983 and 2024 in years
    frame = et0.et0_frame(weather, 43.55)
    usable = frame.loc[frame.index.year.isin(years)]
    assert usable["et0_pm"].notna().all()
    assert 400 < usable["et0_pm"].groupby(usable.index.year).sum().mean() < 900
