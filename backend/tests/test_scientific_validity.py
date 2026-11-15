"""Synthetic fixtures below test invariants, never represent NASA observations."""
import copy
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import et0, recommend as r, rotations, climate_future as cf
from engine.water_balance import run_bucket
from engine.weather import load_reference, complete_years, validate_weather
from engine.rotation_simulation import simulate_rotation, crop_dates, CalendarError

CROPS = load_reference('crops')
SOIL = load_reference('soil_texture')['loam']
ROT = (('corn', None), ('soybean', None), ('winter_wheat', None))


def synthetic_weather(first=2004, last=2007):
    index = pd.date_range(f'{first}-01-01', f'{last}-12-31')
    return pd.DataFrame({'tmax_c': 25., 'tmin_c': 12., 'precip_mm': np.where(index.day % 9 == 0, 18., 0.)}, index=index)


def test_daily_mass_balance_and_et_limits():
    rng = np.random.default_rng(5)
    demand, rain = rng.uniform(0, 9, 1000), rng.uniform(0, 30, 1000)
    b = run_bucket(demand, rain, 160, initial_storage=80)
    assert np.allclose(b['initial_store'] + rain, b['eta'] + b['drainage'] + b['store'], atol=1e-10)
    assert np.all(b['eta'] <= demand) and np.all(b['eta'] <= b['initial_store'] + rain)
    assert np.all((b['store'] >= 0) & (b['store'] <= 160))
    assert np.all(b['shortfall'] >= 0)
    assert b['initial_store'][1:] == pytest.approx(b['store'][:-1])


def test_rain_available_before_et_and_drainage():
    b = run_bucket([5], [10], 100, initial_storage=100)
    assert b['eta'][0] == 5 and b['drainage'][0] == 5 and b['store'][0] == 100


@pytest.mark.parametrize('demand,rain,capacity,initial', [([-1],[0],100,50),([1],[-1],100,50),
    ([np.nan],[0],100,50),([1],[np.inf],100,50),([1],[0],0,0),([1],[0],100,-1),([1],[0],100,101)])
def test_invalid_bucket_inputs(demand,rain,capacity,initial):
    with pytest.raises(ValueError):
        run_bucket(demand,rain,capacity,initial_storage=initial)


def test_hargreaves_nonnegative_units_and_missing():
    assert et0.et0_hargreaves(-20,-30,43.55,15) == 0
    # Independent equation: Ra=41.1 MJ/m2/day -> 16.7688 mm/day equivalent.
    ra = et0.extraterrestrial_radiation(50.8,187)
    expected = .0023 * (16.9+17.8) * np.sqrt(21.5-12.3) * .408 * ra
    assert float(et0.et0_hargreaves(21.5,12.3,50.8,187)) == pytest.approx(expected)
    assert np.isnan(et0.et0_hargreaves(np.nan,12,43.55,150))
    with pytest.raises(ValueError):
        et0.et0_hargreaves(10,20,43.55,150)


def test_carryover_and_actual_sequence_and_wheat_transition():
    result = simulate_rotation(synthetic_weather(),43.55,ROT,CROPS,SOIL,2005,2007,return_daily=True)
    phase = result['phases'][0]['daily']
    assert phase.loc['2005-06-01','crop'] == 'corn'
    assert phase.loc['2006-06-01','crop'] == 'soybean'
    assert phase.loc['2006-12-31','crop'] == 'winter_wheat'
    assert phase.loc['2007-01-01','crop'] == 'winter_wheat'
    assert phase.loc['2007-06-01','crop'] == 'winter_wheat'
    assert phase.initial_storage_mm.iloc[1:].to_numpy() == pytest.approx(phase.storage_mm.iloc[:-1])
    assert phase.loc['2007-01-01','initial_storage_mm'] == phase.loc['2006-12-31','storage_mm']
    for p in result['phases']:
        assert p['daily'].initial_storage_mm.iloc[0] == 80
        assert len(p['annual']) == 3


def test_phase_fairness_cyclic_shift_and_same_weather():
    weather = synthetic_weather()
    a = simulate_rotation(weather,43.55,ROT,CROPS,SOIL,2005,2007)
    b = simulate_rotation(weather,43.55,ROT[1:]+ROT[:1],CROPS,SOIL,2005,2007)
    assert a['metrics'] == pytest.approx(b['metrics'])
    assert len(a['phases']) == len(ROT)
    assert {p['first_crop'] for p in a['phases']} == {'corn','soybean','winter_wheat'}


def test_crop_order_is_preserved_beyond_cyclic_shifts():
    # Two distinct chronological sequences have distinct occupancy even with same crop counts.
    rot = (('corn',None),('soybean',None),('corn',None),('winter_wheat',None))
    other = (('corn',None),('corn',None),('soybean',None),('winter_wheat',None))
    with pytest.raises(CalendarError):
        # Corn immediately precedes wheat in this cycle and harvest misses sowing.
        simulate_rotation(synthetic_weather(),43.55,rot,CROPS,SOIL,2005,2007)
    result = simulate_rotation(synthetic_weather(),43.55,other,CROPS,SOIL,2005,2007,return_daily=True)
    assert result['phases'][0]['daily'].loc['2006-06-01','crop'] == 'corn'


def test_wheat_waits_for_previous_harvest_within_planting_window():
    plant, harvest = crop_dates('winter_wheat','soybean',2007,CROPS)
    assert plant.year == 2006 and harvest.year == 2007
    assert plant > pd.Timestamp('2006-10-01') and plant <= pd.Timestamp('2006-10-10')
    with pytest.raises(CalendarError):
        crop_dates('winter_wheat','corn',2007,CROPS)


def test_cover_exclusion_is_explicit():
    rules = load_reference('rotation_rules')
    assert all(cover is None for rot in rotations.all_candidates(rules) for _,cover in rot)
    with pytest.raises(ValueError,match='Cover'):
        simulate_rotation(synthetic_weather(),43.55,(('corn','cereal_rye'),),CROPS,SOIL,2005,2007)


def test_exact_daily_coverage_and_missing_observations():
    w = synthetic_weather()
    assert complete_years(w, ['tmax_c','tmin_c','precip_mm']) == [2004,2005,2006,2007]
    missing = w.drop(pd.Timestamp('2005-05-05'))
    assert 2005 not in complete_years(missing,['tmax_c','tmin_c','precip_mm'])
    for bad in [missing, pd.concat([w,w.iloc[:1]]), w.iloc[::-1]]:
        with pytest.raises(ValueError):
            simulate_rotation(bad,43.55,ROT,CROPS,SOIL,2005,2007)
    w.loc['2005-05-05','precip_mm'] = np.nan
    with pytest.raises(ValueError):
        validate_weather(w)


@pytest.mark.parametrize('var',cf.VARIABLES)
def test_missing_climate_deltas_not_zero_filled(var):
    d = {'tmax_c_delta':[1.]*12,'tmin_c_delta':[1.]*12,'pr_ratio':[1.1]*12}
    d[var][0] = None
    with pytest.raises(ValueError,match='Missing'):
        cf.apply_deltas(synthetic_weather(),d)


def test_mandatory_constraints_and_original_baseline():
    req = {'lat':43.55,'lon':-80.25,'current_rotation':['corn','soybean']}
    out = r.recommend({**req,'must_include':['rice']})
    assert out['status'] == 'insufficient_feasible_alternatives' and not out['options']
    assert out['inputs_used']['must_include'] == ['rice']
    assert [x['crop'] for x in out['baseline']['rotation']] == req['current_rotation']
    out = r.recommend({**req,'must_include':['winter_wheat'],'equipment':['planter','combine']})
    assert not out['options'] and out['baseline']['metrics'] is not None
    out = r.recommend({**req,'avoid':['corn']})
    assert out['baseline']['rotation'][0]['crop'] == 'corn'
    assert all('corn' not in [x['crop'] for x in o['rotation']] for o in out['options'])


def test_min_gaps_and_no_cash_crop_overlap_in_candidates():
    rules = load_reference('rotation_rules')
    for rotation in rotations.all_candidates(rules):
        for i,(crop,_) in enumerate(rotation):
            gap = next(k for k in range(1,len(rotation)+1) if rotation[(i-k)%len(rotation)][0] == crop)
            assert gap > rules['min_gap_years'][crop]['value']


def test_model_outcomes_summarized_after_independent_runs(monkeypatch):
    # Synthetic model runs prove aggregation occurs after simulation, with matched reference years.
    monkeypatch.setattr(cf,'deltas_at',lambda *args: {'models':{'cool':{},'warm':{},'hot':{}},
        'baseline_period':{'start':1995,'end':2014},'cell':{'lat':43.625,'lon':-80.375},'method':'synthetic test'})
    calls=[]
    def run(anchor,soil,rotation,first,last,model=None,scenario='ssp245'):
        calls.append((first,last,model))
        return {'metrics':{'water_use_mm':{'cool':1.,'warm':4.,'hot':100.}[model]},'et0_method':r.ET0_METHOD}
    monkeypatch.setattr(r,'_run',run)
    out = r._future('guelph','loam',ROT)
    assert calls == [(1995,2014,'cool'),(1995,2014,'warm'),(1995,2014,'hot')]
    assert out['metrics']['water_use_mm'] == 4.
    assert out['model_range']['water_use_mm'] == {'min':1.,'max':100.}
    assert out['period'] == {'start':2031,'end':2050}
    assert out['et0_method'] == r.ET0_METHOD


def test_historical_and_future_use_same_et0(monkeypatch):
    weather = synthetic_weather(1994,2014)
    monkeypatch.setattr(r,'load_weather',lambda *a: weather)
    monkeypatch.setattr(cf,'deltas_at',lambda *a: {'models':{'test':{'tmax_c_delta':[1.]*12,'tmin_c_delta':[1.]*12,'pr_ratio':[1.]*12}}})
    r._run.cache_clear()
    historic=r._run('guelph','loam',(('corn',None),),1995,2014)
    future=r._run('guelph','loam',(('corn',None),),1995,2014,'test')
    assert historic['et0_method'] == future['et0_method'] == r.ET0_METHOD
    assert future['metrics']['water_use_mm'] > historic['metrics']['water_use_mm']
    r._run.cache_clear()


def test_api_rejects_nonfinite_coordinates_and_unknown_fields():
    from api.main import app
    from fastapi.testclient import TestClient
    c = TestClient(app,raise_server_exceptions=False)
    assert c.get('/snap',params={'lat':'nan','lon':-80.25}).status_code == 422
    assert c.post('/recommend',json={'lat':43.55,'lon':-80.25,'mystery':True}).status_code == 422


def test_mean_temperature_and_dtr_change_factors_preserve_order():
    w = synthetic_weather()
    w['tmax_c'], w['tmin_c'] = 10.1,10.0
    d = {'tmax_c_delta':[1.]*12,'tmin_c_delta':[3.]*12,'pr_ratio':[1.]*12,'dtr_ratio':[.8]*12}
    out = cf.apply_deltas(w,d)
    assert (out.tmax_c >= out.tmin_c).all()
    assert ((out.tmax_c + out.tmin_c)/2).to_numpy() == pytest.approx(np.full(len(w),12.05))
    assert (out.tmax_c-out.tmin_c).to_numpy() == pytest.approx(np.full(len(w),.08))
    assert w.tmax_c.iloc[0] == 10.1
    assert 'no clipping' in out.attrs['temperature_adjustment']


def test_soil_capacity_and_initial_fraction_validation():
    for soil,fraction in [({'available_water_mm_per_m':None},.5),({'available_water_mm_per_m':-1},.5),(SOIL,-.1),(SOIL,1.1)]:
        with pytest.raises(ValueError):
            simulate_rotation(synthetic_weather(),43.55,ROT,CROPS,soil,2005,2007,initial_fraction=fraction)


def test_future_missing_cannot_be_scored_as_historical(monkeypatch):
    monkeypatch.setattr(r,'_future',lambda *a: {'status':'insufficient_data','reason':'synthetic missing-file test','metrics':None,'models':{}})
    out = r.recommend({'lat':43.55,'lon':-80.25,'climate_period':'future'})
    assert out['status'] == 'insufficient_feasible_alternatives'
    assert not out['scores_available'] and not out['options']
    assert out['baseline']['metrics_period'] == 'historical_2005_2024'


def test_no_feasible_crop_constraints_preserve_baseline():
    out = r.recommend({'lat':43.55,'lon':-80.25,'current_rotation':['corn','soybean'],
                       'avoid':['corn','soybean','winter_wheat']})
    assert out['status'] == 'insufficient_feasible_alternatives' and not out['options']
    assert [x['crop'] for x in out['baseline']['rotation']] == ['corn','soybean']


def test_missing_crop_parameters_return_insufficient_data():
    crops = copy.deepcopy(CROPS)
    crops['corn']['kc']['ini'] = None
    with pytest.raises(ValueError,match='Insufficient crop data'):
        simulate_rotation(synthetic_weather(),43.55,ROT,crops,SOIL,2005,2007)


def test_zero_demand_baseline_has_no_fabricated_percentage(monkeypatch):
    w = synthetic_weather(2004,2024)
    w['tmax_c'],w['tmin_c'] = -20.,-30.
    monkeypatch.setattr(r,'load_weather',lambda *a: w)
    monkeypatch.setattr(r,'_future',lambda *a: {'status':'insufficient_data','reason':'synthetic test','metrics':None,'models':{}})
    r._run.cache_clear()
    out = r.recommend({'lat':43.55,'lon':-80.25})
    assert out['baseline']['metrics']['potential_demand_mm'] == 0
    assert all(o['vs_baseline']['water_use_pct'] is None for o in out['options'])
    r._run.cache_clear()


def test_power_unit_validation_and_solar_conversion():
    from data_scripts.fetch_power import to_frame, PARAMS
    payload = {'header':{'fill_value':-999},'properties':{'parameter':{key:{'20200101':1.0} for key in PARAMS}},
               'parameters':{key:{'units':unit} for key,unit in {'T2M_MAX':'C','T2M_MIN':'C','PRECTOTCORR':'mm/day',
                'ALLSKY_SFC_SW_DWN':'kW-hr/m^2/day','RH2M':'%','WS2M':'m/s'}.items()}}
    out = to_frame(payload)
    assert out.solar_mj_m2.iloc[0] == pytest.approx(3.6)
    payload['parameters']['ALLSKY_SFC_SW_DWN']['units'] = 'unknown'
    with pytest.raises(ValueError,match='radiation units'):
        to_frame(payload)


def test_unsupported_baseline_is_preserved_without_invented_results():
    out = r.recommend({'lat':43.55,'lon':-80.25,'current_rotation':['rice','corn']})
    assert out['status']=='insufficient_data' and out['baseline']['metrics'] is None
    assert [x['crop'] for x in out['baseline']['rotation']]==['rice','corn']
    assert not out['options']


def test_real_mvp_future_cache_and_independent_model_outcomes():
    doc=cf.load_grid('ssp245','2031_2050')
    assert doc['future_period']=={'start':2031,'end':2050}
    assert doc['baseline_period']=={'start':1995,'end':2014}
    assert set(doc['models'])=={'ACCESS-CM2','MPI-ESM1-2-HR','MRI-ESM2-0'}
    result=r._future('guelph','loam',ROT)
    assert result['status']=='available', result.get('reason')
    assert result['model_count']==3
    for key,value in result['metrics'].items():
        values=[run['metrics'][key] for run in result['models'].values()]
        assert value==pytest.approx(np.median(values))
        assert result['model_range'][key]=={'min':min(values),'max':max(values)}
    for run in result['models'].values():
        assert run['et0_method']==r.ET0_METHOD and len(run['phases'])==3
        assert run['period']=={'start':1995,'end':2014}


def test_real_future_api_scoring_is_model_median():
    out=r.recommend({'lat':43.55,'lon':-80.25,'current_rotation':['corn','soybean'],
                     'must_include':['corn'],'climate_period':'future'})
    assert out['status']=='ok' and out['scores_available']
    assert out['baseline']['metrics_period']=='future_2031_2050'
    f=out['time_machine']['future_2031_2050']
    assert out['baseline']['metrics']['water_use_mm']==round(f['metrics']['water_use_mm'],2)
    assert all(o['metrics_period']=='future_2031_2050' for o in out['options'])
    assert 'survived_years' not in out['baseline']['metrics']
