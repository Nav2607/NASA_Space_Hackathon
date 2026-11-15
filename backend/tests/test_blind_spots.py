"""Screening/event tests; synthetic weather is explicitly a test fixture."""
import sys
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from api.main import app
from engine import blind_spots as bs
from engine.rotation_simulation import simulate_rotation
from engine.weather import load_reference

REQUEST = {"lat": 43.55, "lon": -80.25, "soil": "loam",
           "current_rotation": ["corn", "soybean"], "historical_period": "2005_2014"}


def test_events_split_at_type_crop_clear_day_and_date_gap():
    def day(date, crop="corn", kind="water_stress"):
        return {"date": date, "crop": crop, "stress_type": kind}
    events = bs.detect_events([
        day("2005-07-10"), day("2005-07-11"),
        day("2005-07-12", kind="combined_heat_water"),
        day("2005-07-13", kind="no_blind_spot"), day("2005-07-14"),
        day("2005-07-15", crop="soybean"), day("2005-07-17", crop="soybean"),
    ])
    assert [e["duration_days"] for e in events] == [2, 1, 1, 1, 1]
    assert events[0]["end_date"] == "2005-07-11"
    assert events[1]["stress_type"] == "combined_heat_water"
    assert bs.detect_events([]) == []


def test_daily_flags_reuse_engine_diagnostics_and_exclude_warmup():
    index = pd.date_range("2004-01-01", "2005-12-31")
    weather = pd.DataFrame({"tmax_c": 45., "tmin_c": 25., "precip_mm": 0.}, index=index)
    run = simulate_rotation(weather, 43.55, (("corn", None),), load_reference("crops"),
                            load_reference("soil_texture")["loam"], 2005, 2005, return_daily=True)
    phase = run["phases"][0]
    view = bs.present_phase(phase, 2005, 2005)
    assert len(view["daily"]) == 365 and view["daily"][0]["date"] == "2005-01-01"
    totals = view["summary"]["total_days"]
    assert totals["combined"] > 0
    assert totals["combined"] == totals["heat"] == totals["water"]
    assert view["summary"]["annualized_days"] == totals
    for day in view["daily"]:
        source = phase["daily"].loc[day["date"]]
        assert day["storage_mm"] == source.storage_mm
        assert day["unmet_demand_mm"] == source.shortfall_mm
        assert day["water_stress"] == bool(source.critical_stress)
        assert day["heat_exposure"] == bool(source.heat_stress)
        if not day["sensitive_window"]:
            assert day["stress_type"] == "no_blind_spot"
    assert sum(e["duration_days"] for e in view["events"]) == totals["combined"]


def test_exclusive_categories_and_inclusive_counts():
    index = pd.date_range("2005-07-10", periods=4)
    frame = pd.DataFrame({"crop": "corn", "sensitive_window": True,
                          "critical_stress": [True, False, True, False],
                          "heat_stress": [False, True, True, False],
                          "precip_mm": 0., "tmax_c": 41., "storage_mm": 10.,
                          "shortfall_mm": 0.}, index=index)
    view = bs.present_phase({"phase": 0, "first_crop": "corn", "daily": frame}, 2005, 2006)
    assert [d["stress_type"] for d in view["daily"]] == [
        "water_stress", "heat_exposure", "combined_heat_water", "no_blind_spot"]
    assert view["summary"]["total_days"] == {"water": 2, "heat": 2, "combined": 1}
    assert view["summary"]["annualized_days"] == {"water": 1., "heat": 1., "combined": .5}


@pytest.mark.parametrize("climate", ["historical", "future"])
def test_api_real_cached_weather_and_all_phases(climate):
    response = TestClient(app).post("/blind-spots", json={**REQUEST, "climate_period": climate})
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "available", result.get("reason")
    assert len(result["runs"]) == (3 if climate == "future" else 1)
    for run in result["runs"]:
        assert [p["first_crop"] for p in run["phases"]] == ["corn", "soybean"]
        assert len(run["phases"]) == 2
        first, last = (1995, 2014) if climate == "future" else (2005, 2014)
        for phase in run["phases"]:
            assert phase["daily"][0]["date"] == f"{first}-01-01"
            assert phase["daily"][-1]["date"] == f"{last}-12-31"
            for key, total in phase["summary"]["total_days"].items():
                assert phase["summary"]["annualized_days"][key] == total / (last-first+1)
        for key in bs.EXPOSURES:
            assert run["summary"]["total_days"][key] == pytest.approx(
                sum(p["summary"]["total_days"][key] for p in run["phases"]) / 2)
    if climate == "future":
        assert {r["model"] for r in result["runs"]} == {"ACCESS-CM2", "MPI-ESM1-2-HR", "MRI-ESM2-0"}
        assert result["period"] == {"start": 2031, "end": 2050}
        assert "not deterministic future forecasts" in result["weather_label"]
        for key in bs.EXPOSURES:
            values = sorted(r["summary"]["annualized_days"][key] for r in result["runs"])
            assert result["summary"]["annualized_days"][key] == values[1]
            assert result["model_range"]["annualized_days"][key] == {"min": values[0], "max": values[-1]}


def test_api_validation_and_missing_future_are_explicit(monkeypatch):
    client = TestClient(app)
    for changes in ({"soil": "unknown"}, {"current_rotation": ["rice"]},
                    {"historical_period": "2000_2001"}, {"lat": 90}):
        assert client.post("/blind-spots", json={**REQUEST, **changes}).status_code == 422
    def missing(*args):
        raise FileNotFoundError("Synthetic missing-cache test")
    monkeypatch.setattr(bs.climate_future, "deltas_at", missing)
    result = client.post("/blind-spots", json={**REQUEST, "climate_period": "future"}).json()
    assert result["status"] == "insufficient_data"
    assert result["runs"] == [] and result["summary"] is None
    assert "missing-cache" in result["reason"]
