"""Synthetic NetCDF fixtures exercise the existing extraction boundary, no network."""
import io
import sys
from pathlib import Path

import numpy as np
import pytest
from scipy.io import netcdf_file

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from data_scripts import extract_nex_region as nex


def synthetic_netcdf(units='K', duplicate=False, fill=False, calendar='standard'):
    sink=io.BytesIO()
    with netcdf_file(sink,'w') as nc:
        nc.createDimension('time',365)
        nc.createDimension('lat',2)
        nc.createDimension('lon',2)
        lat=nc.createVariable('lat','f8',('lat',));lat[:]=[43.,44.]
        lon=nc.createVariable('lon','f8',('lon',));lon[:]=[279.,280.]
        t=nc.createVariable('time','f8',('time',));t.units='days since 2001-01-01 00:00:00';t.calendar=calendar
        times=np.arange(365,dtype=float)
        if duplicate:
            times[10]=times[9]
        t[:]=times
        v=nc.createVariable('tasmax','f8',('time','lat','lon'));v.units=units;v._FillValue=-9999.
        data=np.broadcast_to((250+np.arange(365)/100)[:,None,None],(365,2,2)).copy()
        if fill:
            data[2,0,0]=-9999.
        v[:]=data
        nc.flush()
        raw=sink.getvalue()
    return raw


@pytest.mark.parametrize('options,message',[({'units':'C'},'units'),({'duplicate':True},'timestamps'),
    ({'fill':True},'Incomplete'),({'calendar':'360_day'},'calendar')])
def test_invalid_netcdf_not_reduced_into_climate_means(monkeypatch,tmp_path,options,message):
    monkeypatch.setattr(nex,'CACHE',tmp_path)
    monkeypatch.setattr(nex,'dataset_path',lambda *a:'synthetic')
    raw=synthetic_netcdf(**options)
    monkeypatch.setattr(nex,'download',lambda *a,**k:raw)
    with pytest.raises(ValueError,match=message):
        nex.monthly_means('test','historical','tasmax',2001)
    assert not list(tmp_path.rglob('*.npz'))


def test_valid_units_dates_and_longitude_conversion(monkeypatch,tmp_path):
    monkeypatch.setattr(nex,'CACHE',tmp_path)
    monkeypatch.setattr(nex,'dataset_path',lambda *a:'synthetic')
    raw=synthetic_netcdf()
    monkeypatch.setattr(nex,'download',lambda *a,**k:raw)
    lat,lon,monthly=nex.monthly_means('test','historical','tasmax',2001)
    assert np.array_equal(lat,[43.,44.]) and np.array_equal(lon,[-81.,-80.])
    assert monthly.shape==(12,2,2)
    assert monthly[0,0,0]==pytest.approx(np.mean(250+np.arange(31)/100)-273.15)
