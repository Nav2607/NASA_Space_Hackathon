"""Screening/event tests; synthetic weather is explicitly a test fixture."""
import sys
import copy
import datetime as dt
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


def test_intensity_uses_exact_pre_et_threshold_and_heat_equality():
    index = pd.date_range("2004-01-01", "2005-12-31")
    weather = pd.DataFrame({"tmax_c": 40., "tmin_c": 20., "precip_mm": 0.}, index=index)
    crops = load_reference("crops")
    soil = load_reference("soil_texture")["loam"]
    capacity = soil["available_water_mm_per_m"]
    threshold = crops["corn"]["depletion_fraction_p"] * capacity
    weather.loc["2005-07-10", "precip_mm"] = capacity - threshold
    weather.loc["2005-07-11", "tmax_c"] = 43.
    weather.loc["2005-07-12", "precip_mm"] = 1000.
    run = simulate_rotation(weather, 43.55, (("corn", None),), crops, soil,
                            2005, 2005, return_daily=True)
    daily = run["phases"][0]["daily"]
    equal, dry, wet = (daily.loc[d] for d in ("2005-07-10", "2005-07-11", "2005-07-12"))
    assert equal.initial_storage_mm == 0
    assert equal.depletion_mm == threshold
    assert not equal.threshold_stress and equal.water_depletion_intensity == 0
    assert equal.storage_mm < capacity-threshold  # post-ET store would incorrectly flag stress
    assert equal.heat_stress and equal.heat_exceedance_c == 0  # >= threshold, not >
    assert dry.water_depletion_intensity == pytest.approx(
        (dry.depletion_mm-threshold)/(capacity-threshold))
    assert dry.heat_exceedance_c == 3 and dry.heat_stress
    assert wet.water_depletion_intensity == 0 and not wet.threshold_stress
    assert daily.water_depletion_intensity.between(0, 1).all()
    assert daily.loc["2005-07-09", "water_depletion_intensity"] == 1
    assert daily.loc[daily.crop == "", "heat_exceedance_c"].eq(0).all()
    assert daily.loc[daily.kc > 0, "threshold_stress"].to_list() == (
        daily.loc[daily.kc > 0, "water_depletion_intensity"] > 0).to_list()
    crops = copy.deepcopy(crops)
    crops["corn"]["depletion_fraction_p"] = 1.
    edge = simulate_rotation(weather, 43.55, (("corn", None),), crops, soil,
                             2005, 2005, return_daily=True)["phases"][0]["daily"]
    assert edge.water_depletion_intensity.eq(0).all() and not edge.threshold_stress.any()


def test_event_intensity_and_cumulative_quantities():
    days = [{"date": "2005-07-10", "crop": "corn", "stress_type": "combined_heat_water",
             "water_depletion_intensity": .2, "unmet_demand_mm": 1., "heat_exceedance_c": 2., "tmax_c": 42.},
            {"date": "2005-07-11", "crop": "corn", "stress_type": "combined_heat_water",
             "water_depletion_intensity": .6, "unmet_demand_mm": 2., "heat_exceedance_c": 3., "tmax_c": 43.}]
    event = bs.detect_events(days)[0]
    assert event["duration_days"] == 2
    assert event["max_water_depletion_intensity"] == .6
    assert event["mean_water_depletion_intensity"] == pytest.approx(.4)
    assert event["cumulative_unmet_demand_mm"] == 3
    assert event["cumulative_heat_exceedance_degree_days"] == 5
    assert event["max_temperature_c"] == 43
    assert "_days" not in event


def test_event_duration_statistics():
    frame = pd.DataFrame({"crop": "corn", "sensitive_window": True,
                          "critical_stress": [True, True, False, True], "heat_stress": False,
                          "precip_mm": 0., "tmax_c": 30., "storage_mm": 10.,
                          "shortfall_mm": 0., "water_depletion_intensity": .5,
                          "heat_exceedance_c": 0.}, index=pd.date_range("2005-07-10", periods=4))
    phase = {"phase": 0, "first_crop": "corn", "daily": frame}
    view = bs.present_phase(phase, 2005, 2005)
    assert view["event_statistics"] == {"event_count": 2, "longest_event_duration_days": 2,
                                        "mean_event_duration_days": 1.5}
    frame["critical_stress"] = False
    assert bs.present_phase(phase, 2005, 2005)["event_statistics"] == {
        "event_count": 0, "longest_event_duration_days": 0, "mean_event_duration_days": None}


def weekly_day(year, crop="corn", water=False, heat=False, intensity=0., unmet=0., weekday=2):
    return {"date": dt.date.fromisocalendar(year, 28, weekday).isoformat(), "crop": crop,
            "sensitive_window": True, "water_stress": water, "heat_exposure": heat,
            "water_depletion_intensity": intensity, "unmet_demand_mm": unmet}


def test_weekly_denominators_exclude_absent_crops_and_do_not_pool_phases():
    phases = [{"daily": [weekly_day(2005, water=True, intensity=.8, unmet=4.), weekly_day(2007)]},
              {"daily": [weekly_day(2005), weekly_day(2006, crop="soybean")]}]
    rows = bs.weekly_vulnerabilities(phases)
    corn = next(row for row in rows if row["crop"] == "corn")
    assert corn["eligible_seasons"] == 2 and corn["eligible_season_years"] == [2005, 2007]
    assert corn["seasons_with_exposure"]["water"] == 1
    assert corn["exposed_season_equivalents"]["water"] == .5
    assert corn["frequency_pct"]["water"] == 25  # (mean(1,0) + 0) / 2
    assert corn["mean_water_depletion_intensity"] == pytest.approx(.2)
    assert corn["mean_daily_unmet_demand_mm"] == 1.
    assert rows == bs.weekly_vulnerabilities(phases * 2)  # duplicates aren't extra climate years


def test_weekly_combined_requires_same_day_and_sensitive_eligibility():
    ignored = {**weekly_day(2006, water=True, heat=True), "sensitive_window": False}
    rows = bs.weekly_vulnerabilities([{"daily": [weekly_day(2005, water=True),
                    weekly_day(2005, heat=True, weekday=3), ignored]}])
    assert rows[0]["eligible_seasons"] == 1
    assert rows[0]["frequency_pct"] == {"water": 100., "heat": 100., "combined": 0.}


@pytest.mark.parametrize("old,values,label,agreement", [
    (0, [10, 20, 30], "emerging", {"increased": 3, "decreased": 0, "unchanged": 0}),
    (50, [0, 20, 40], "diminishing", {"increased": 0, "decreased": 3, "unchanged": 0}),
    (50, [50, 60, 70], "persistent", {"increased": 2, "decreased": 0, "unchanged": 1}),
    (50, [60, 40, 50], "uncertain", {"increased": 1, "decreased": 1, "unchanged": 1}),
    (0, [0, 0, 0], "no_exposure", {"increased": 0, "decreased": 0, "unchanged": 3}),
    (0, [0, 0, 10], "uncertain", {"increased": 1, "decreased": 0, "unchanged": 2}),
])
def test_future_comparisons_and_model_agreement(old, values, label, agreement):
    def row(value):
        return {"crop": "corn", "calendar_week": 28, "eligible_seasons": 20,
                "frequency_pct": {"water": value, "heat": 0., "combined": 0.}}
    models = {name: [row(value)] for name, value in zip(("a", "b", "c"), values)}
    out = bs.compare_weekly([row(old)], models)[0]["exposures"]["water"]
    median = sorted(values)[1]
    assert out["classification"] == label and out["model_agreement"] == agreement
    assert out["future_median_frequency_pct"] == median
    assert out["future_range_frequency_pct"] == {"min": min(values), "max": max(values)}
    assert out["change_percentage_points"] == median-old
    assert out["future_frequency_pct_by_model"] == dict(zip(models, values))


def test_missing_eligible_seasons_are_not_assumed_unexposed():
    baseline = [{"crop": "corn", "calendar_week": 28, "eligible_seasons": 2,
                 "frequency_pct": {"water": 50, "heat": 0, "combined": 0}}]
    out = bs.compare_weekly(baseline, {"a": baseline, "b": []})
    assert out[0]["status"] == "insufficient_data" and out[0]["exposures"] is None


def test_weekly_rotation_phase_fairness():
    index = pd.date_range("2004-01-01", "2007-12-31")
    weather = pd.DataFrame({"tmax_c": 42., "tmin_c": 20., "precip_mm": 1.}, index=index)
    rotation = (("corn", None), ("soybean", None), ("winter_wheat", None))
    def weekly(rot):
        run = simulate_rotation(weather, 43.55, rot, load_reference("crops"),
                                load_reference("soil_texture")["loam"], 2005, 2007, return_daily=True)
        return bs.weekly_vulnerabilities([bs.present_phase(p, 2005, 2007) for p in run["phases"]])
    a, b = weekly(rotation), weekly(rotation[1:] + rotation[:1])
    assert [(r["crop"], r["calendar_week"]) for r in a] == [(r["crop"], r["calendar_week"]) for r in b]
    for left, right in zip(a, b):
        assert left["eligible_seasons"] == right["eligible_seasons"]
        assert 1 <= left["eligible_seasons"] <= 3  # window-edge ISO weeks vary by year
        assert left["frequency_pct"] == pytest.approx(right["frequency_pct"])
        assert left["mean_water_depletion_intensity"] == pytest.approx(right["mean_water_depletion_intensity"])


def test_future_endpoint_reuses_three_model_runs_and_one_matched_reference(monkeypatch):
    original = bs.simulate_rotation
    calls = []
    def tracked(*args, **kwargs):
        calls.append((args[5], args[6], kwargs.get("return_daily")))
        return original(*args, **kwargs)
    monkeypatch.setattr(bs, "simulate_rotation", tracked)
    response = TestClient(app).post("/blind-spots", json={**REQUEST, "climate_period": "future"})
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "available"
    assert calls == [(1995, 2014, True)] * 4
    assert result["recurring_vulnerabilities"]["historical_period"] == {"start": 1995, "end": 2014}
    assert result["emerging_vulnerabilities"]
    reference = {(r["crop"], r["calendar_week"]): r for r in result["recurring_vulnerabilities"]["historical"]}
    assert reference[("corn", 30)]["eligible_seasons"] == 20
    for row in result["emerging_vulnerabilities"]:
        assert row["status"] == "available"
        assert row["eligible_seasons"] == reference[(row["crop"], row["calendar_week"])]["eligible_seasons"]
        for exposure in row["exposures"].values():
            assert sum(exposure["model_agreement"].values()) == 3
            assert len(exposure["future_frequency_pct_by_model"]) == 3
    for run in result["runs"]:
        assert run["weekly_vulnerabilities"]
        assert all(1 <= r["eligible_seasons"] <= 20 for r in run["weekly_vulnerabilities"])
        day = run["phases"][0]["daily"][190]
        assert 0 <= day["water_depletion_intensity"] <= 1
        assert day["heat_exceedance_c"] >= 0


def test_unmatched_eligible_reference_seasons_are_rejected():
    old = {"crop": "corn", "calendar_week": 28, "eligible_seasons": 20,
           "frequency_pct": {"water": 50., "heat": 0., "combined": 0.}}
    out = bs.compare_weekly([old], {"a": [{**old, "eligible_seasons": 10}]})
    assert out[0]["status"] == "insufficient_data" and out[0]["exposures"] is None
