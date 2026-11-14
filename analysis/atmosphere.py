"""Measured atmosphere for the N722BD dive, from the two Miami (KMFL) weather-balloon
soundings that bracket the accident (12Z 1 Nov and 00Z 2 Nov 2026), blended in time
to 17:48Z. Source: Iowa Environmental Mesonet RAOB archive."""
import json, math, bisect, os
HERE = os.path.dirname(os.path.abspath(__file__))
FT = 3.28084
GEOID_FT = 89.0   # ADS-B geometric altitude is above the ellipsoid; MSL is ~27 m higher in S. Florida
W_LATE = (17.8 - 12.0) / 12.0   # weight of the 00Z sounding at 17:48Z

def _load(name):
    prof = json.load(open(os.path.join(HERE, '..', 'data', name)))['profiles'][0]['profile']
    th = [(l['hght'] * FT, l['tmpc'] + 273.15, math.log(l['pres'])) for l in prof if l['tmpc'] is not None and l['hght'] is not None]
    wd = [(l['hght'] * FT, -l['sknt'] * math.sin(math.radians(l['drct'])), -l['sknt'] * math.cos(math.radians(l['drct'])))
          for l in prof if l['sknt'] is not None and l['drct'] is not None and l['hght'] is not None]
    return sorted(th), sorted(wd)

def _interp(tab, h, k):
    hs = [r[0] for r in tab]
    i = min(max(bisect.bisect_left(hs, h), 1), len(tab) - 1)
    a, b = tab[i - 1], tab[i]
    f = min(max((h - a[0]) / ((b[0] - a[0]) or 1), 0), 1)
    return a[k] + (b[k] - a[k]) * f

_A = _load('raob_KMFL_2026110112.json'); _B = _load('raob_KMFL_2026110200.json')

def at(h_geom_ft):
    """Return (T_K, p_hPa, rho_slug_ft3, wind_east_kt, wind_north_kt) at an ADS-B geometric altitude.
    Wind components are the direction the air is moving toward."""
    h = h_geom_ft + GEOID_FT
    mix = lambda k, w: _interp(_A[w], h, k) * (1 - W_LATE) + _interp(_B[w], h, k) * W_LATE
    T = mix(1, 0); p = math.exp(mix(2, 0))
    rho = p * 100 / (287.05 * T) * 0.00194032
    return T, p, rho, mix(1, 1), mix(2, 1)

if __name__ == '__main__':
    for h in (1000, 5000, 10000, 15000, 20000, 25000, 30000, 36900):
        T, p, rho, u, v = at(h)
        spd = math.hypot(u, v); d = (math.degrees(math.atan2(-u, -v)) + 360) % 360
        print(f"{h:6d} ft  {T-273.15:6.1f} C  {p:6.1f} hPa  wind {d:03.0f}/{spd:2.0f} kt")
