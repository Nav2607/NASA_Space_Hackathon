"""Reference evaporation (ET0) in mm/day.

Main method: FAO-56 Penman-Monteith (Allen et al. 1998, eq. 6), using the daily
fields NASA POWER provides: Tmax, Tmin, mean relative humidity, 2 m wind and
solar radiation. Fallback: Hargreaves, which needs only temperatures and latitude.

Missing solar radiation gives NaN. Nothing is ever filled in or estimated.
"""
import numpy as np
import pandas as pd

GSC = 0.0820          # solar constant, MJ m-2 min-1
SIGMA = 4.903e-9      # Stefan-Boltzmann, MJ K-4 m-2 day-1
ALBEDO = 0.23         # grass reference surface
DEFAULT_ELEVATION_M = 250.0   # Southern Ontario farmland is roughly 75-450 m; effect on ET0 is small


def sat_vapour_pressure(t_c):
    """Saturation vapour pressure, kPa (FAO-56 eq. 11)."""
    return 0.6108 * np.exp(17.27 * t_c / (t_c + 237.3))


def validate_temperatures(tmax, tmin):
    tmax, tmin = np.broadcast_arrays(np.asarray(tmax, float), np.asarray(tmin, float))
    if np.any(np.isinf(tmax)) or np.any(np.isinf(tmin)) or np.any(tmax < tmin):
        raise ValueError("Invalid temperatures: require Tmax >= Tmin and no infinity")
    return tmax, tmin


def extraterrestrial_radiation(lat_deg, doy):
    """Ra in MJ m-2 day-1 (FAO-56 eq. 21-25)."""
    if not np.isfinite(lat_deg) or not -90 <= lat_deg <= 90:
        raise ValueError("Latitude must be finite and within [-90, 90]")
    phi = np.radians(lat_deg)
    doy = np.asarray(doy, dtype=float)
    if np.any(~np.isfinite(doy)) or np.any((doy < 1) | (doy > 366)):
        raise ValueError("Invalid day of year")
    dr = 1 + 0.033 * np.cos(2 * np.pi * doy / 365)
    delta = 0.409 * np.sin(2 * np.pi * doy / 365 - 1.39)
    ws = np.arccos(np.clip(-np.tan(phi) * np.tan(delta), -1, 1))
    return (24 * 60 / np.pi) * GSC * dr * (
        ws * np.sin(phi) * np.sin(delta) + np.cos(phi) * np.cos(delta) * np.sin(ws)
    )


def et0_penman_monteith(tmax, tmin, rh_mean, wind_2m, solar, lat_deg, doy,
                        elevation_m=DEFAULT_ELEVATION_M, ea=None):
    """Daily FAO-56 Penman-Monteith ET0 (mm/day).

    rh_mean: mean relative humidity, %. wind_2m: m/s at 2 m. solar: MJ m-2 day-1.
    ea: actual vapour pressure in kPa; if None it is taken from rh_mean (eq. 19).
    Soil heat flux G is taken as 0 for daily steps.
    """
    tmax, tmin = validate_temperatures(tmax, tmin)
    wind_2m, solar = np.asarray(wind_2m, float), np.asarray(solar, float)
    if np.any(wind_2m < 0) or np.any(solar < 0) or np.any(np.isinf(wind_2m)) or np.any(np.isinf(solar)):
        raise ValueError("Wind and solar radiation must be nonnegative and not infinite")
    if not np.isfinite(elevation_m) or elevation_m > 9000 or elevation_m < -500:
        raise ValueError("Invalid elevation in metres")
    if rh_mean is not None and (np.any(np.asarray(rh_mean) < 0) or np.any(np.asarray(rh_mean) > 100)):
        raise ValueError("Relative humidity must be a percentage within [0,100]")
    tmean = (tmax + tmin) / 2

    es = (sat_vapour_pressure(tmax) + sat_vapour_pressure(tmin)) / 2
    if ea is None:
        ea = np.asarray(rh_mean, float) / 100 * es
    if np.any(np.asarray(ea) < 0) or np.any(np.isinf(ea)):
        raise ValueError("Vapour pressure must be nonnegative and not infinite")

    pressure = 101.3 * ((293 - 0.0065 * elevation_m) / 293) ** 5.26
    gamma = 0.000665 * pressure
    delta = 4098 * sat_vapour_pressure(tmean) / (tmean + 237.3) ** 2

    ra = extraterrestrial_radiation(lat_deg, doy)
    rso = (0.75 + 2e-5 * elevation_m) * ra
    rns = (1 - ALBEDO) * solar
    rs_rso = np.clip(solar / rso, 0.3, 1.0)
    rnl = SIGMA * (((tmax + 273.16) ** 4 + (tmin + 273.16) ** 4) / 2) \
        * (0.34 - 0.14 * np.sqrt(ea)) * (1.35 * rs_rso - 0.35)
    rn = rns - rnl

    return np.maximum(0, (0.408 * delta * rn + gamma * 900 / (tmean + 273) * wind_2m * (es - ea)) / (
        delta + gamma * (1 + 0.34 * wind_2m)
    ))


def et0_hargreaves(tmax, tmin, lat_deg, doy):
    """Hargreaves ET0 (mm/day): 0.0023 (Tmean + 17.8) sqrt(Tmax - Tmin) Ra, Ra in mm/day.

    Needs no solar, humidity or wind, so it also works on NEX projections
    and for years where POWER solar radiation is missing. Less accurate in humid climates.
    """
    tmax, tmin = validate_temperatures(tmax, tmin)
    ra_mm = 0.408 * extraterrestrial_radiation(lat_deg, doy)
    return np.maximum(0, 0.0023 * ((tmax + tmin) / 2 + 17.8) * np.sqrt(tmax - tmin) * ra_mm)


def et0_frame(weather, lat_deg, elevation_m=DEFAULT_ELEVATION_M):
    """Add ET0 columns to a POWER weather frame (columns as written by fetch_power.py).

    Returns a DataFrame with et0_pm (NaN where solar is missing) and et0_hargreaves.
    """
    doy = weather.index.day_of_year.values
    out = pd.DataFrame(index=weather.index)
    out["et0_pm"] = et0_penman_monteith(
        weather["tmax_c"], weather["tmin_c"], weather["rh_pct"], weather["wind_m_s"],
        weather["solar_mj_m2"], lat_deg, doy, elevation_m,
    )
    out["et0_hargreaves"] = et0_hargreaves(weather["tmax_c"], weather["tmin_c"], lat_deg, doy)
    return out
