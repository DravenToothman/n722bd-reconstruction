"""Build site/data/flight.json for the 3D viewer from the ADS-B track and the dive-loads table.
Usage: python3 analysis/build_site_data.py   (run from the repository root or from analysis/)"""
import csv, json, math, os
from atmosphere import at, GEOID_FT
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.join(HERE, '..')
sec = lambda u: int(u[:2]) * 3600 + int(u[3:5]) * 60 + float(u[6:])
FT = 0.3048
CRATER = (26.63282, -80.11312)      # impact site on Military Trail
GROUND_MSL_FT = 16.0                # terrain elevation at the site
T_ATMOS = sec('17:20:00')           # Miami soundings are only used within about 150 nm of Miami
T_DIVE_TABLE = sec('17:47:30')

rows = [r for r in csv.DictReader(open(os.path.join(ROOT, 'data', 'n722bd-adsb-2026-11-01.csv')))
        if r['alt_baro_ft'] not in ('ground', '') and r['alt_geom_ft'] != '']
P = [dict(t=sec(r['utc']), lat=float(r['lat']), lon=float(r['lon']), ab=float(r['alt_baro_ft']), ag=float(r['alt_geom_ft']),
          gs=float(r['gs_kt']), trk=float(r['track_deg'])) for r in rows]
dive = {round(sec(r['utc']), 2): r for r in csv.DictReader(open(os.path.join(ROOT, 'data', 'n722bd-dive-loads-2026-11-01.csv')))}

def slope(a, key, t0):
    tm = sum(q['t'] for q in a) / len(a); m = sum(key(q) for q in a) / len(a); den = sum((q['t'] - tm) ** 2 for q in a)
    return sum((q['t'] - tm) * (key(q) - m) for q in a) / den if den > 0 else 0.0

for i, p in enumerate(P):
    d = dive.get(round(p['t'], 2))
    if d and p['t'] >= T_DIVE_TABLE:
        p.update(vs=float(d['vs_geom_fpm']), mach=float(d['mach']), kcas=float(d['kcas']), fpa=float(d['fpa_deg']), bank=float(d['bank_deg']),
                 n=float(d['load_factor_g']), dist=float(d['dist_to_crater_sm']))
        continue
    # outside the dive table: a wider window, because cruise points are 10-20 s apart
    w = 25.0 if p['t'] < sec('17:30:00') else 8.0
    a = [q for q in P[max(0, i - 6):i + 7] if abs(q['t'] - p['t']) <= w]
    vs = slope(a, lambda q: q['ag'], p['t']) if len(a) > 1 else 0.0                                   # ft/s
    tr = slope(a, lambda q: (q['trk'] - p['trk'] + 540) % 360 - 180, p['t']) if len(a) > 1 else 0.0   # deg/s
    vsk = vs * 0.592484; fpa = math.degrees(math.atan2(vsk, p['gs']))
    bank = math.degrees(math.atan(p['gs'] * 1.68781 * math.radians(tr) / 32.174))
    p.update(vs=round(vs * 60, -2), fpa=fpa, bank=max(-45, min(45, bank)), n=None, dist=None, mach=None, kcas=None)
    if p['t'] >= T_ATMOS:
        T, pr, rho, wu, wv = at(p['ag']); tk = math.radians(p['trk'])
        hor = math.hypot(p['gs'] * math.sin(tk) - wu, p['gs'] * math.cos(tk) - wv); tas = math.hypot(hor, vsk)
        M = tas / (38.967 * math.sqrt(T)); qc = pr * ((1 + 0.2 * M * M) ** 3.5 - 1)
        p.update(mach=round(M, 2), kcas=round(661.4786 * math.sqrt(5 * ((qc / 1013.25 + 1) ** (2 / 7) - 1))))

# GPS altitude is broadcast in 25 ft steps and is not time-aligned with position, and positions carry timing jitter,
# which makes the drawn path zigzag. For drawing only, replace each dive point by a local straight-line fit
# (+-1.5 s for altitude, +-1.0 s for latitude and longitude). Readouts keep the raw values.
def local_fit(i, key, half):
    p = P[i]; a = [q for q in P[max(0, i - 12):i + 13] if abs(q['t'] - p['t']) <= half]
    if len(a) < 3: return p[key]
    w = [(1 - (abs(q['t'] - p['t']) / (half * 1.07)) ** 3) ** 3 for q in a]; sw = sum(w)
    tm = sum(wi * q['t'] for wi, q in zip(w, a)) / sw; m = sum(wi * q[key] for wi, q in zip(w, a)) / sw
    den = sum(wi * (q['t'] - tm) ** 2 for wi, q in zip(w, a))
    k = sum(wi * (q['t'] - tm) * (q[key] - m) for wi, q in zip(w, a)) / den if den > 0 else 0.0
    return m + k * (p['t'] - tm)
draw = [(local_fit(i, 'ag', 1.5), local_fit(i, 'lat', 1.0), local_fit(i, 'lon', 1.0)) if p['t'] >= T_DIVE_TABLE else (p['ag'], p['lat'], p['lon']) for i, p in enumerate(P)]
for p, (h, la, lo) in zip(P, draw): p['ag_draw'], p['lat_draw'], p['lon_draw'] = h, la, lo

# carry the last measured velocity down to the ground to get the impact point and time
last = P[-1]; ground_hae_ft = GROUND_MSL_FT - GEOID_FT
dt = (last['ag'] - ground_hae_ft) / (-last['vs'] / 60.0)
P.append(dict(last, t=last['t'] + dt, lat=CRATER[0], lon=CRATER[1], lat_draw=CRATER[0], lon_draw=CRATER[1], ag=ground_hae_ft, ag_draw=ground_hae_ft, dist=0.0, impact=True))

r1 = lambda x, n=1: None if x is None else round(x, n)
out = {
    'date': '2026-11-01', 'tImpact': round(P[-1]['t'], 2), 'tDive': sec('17:48:16'), 'crater': CRATER, 'geoidFt': GEOID_FT,
    't': [round(p['t'], 2) for p in P], 'lat': [round(p['lat_draw'], 6) for p in P], 'lon': [round(p['lon_draw'], 6) for p in P],
    'h': [round(p['ag_draw'] * FT, 1) for p in P],                  # metres above the WGS84 ellipsoid (what Cesium uses)
    'altBaro': [None if p['t'] > sec('17:49:22.5') else int(p['ab']) for p in P],   # pressure altitude froze at 8,750 ft
    'altGps': [int(round(p['ag'] + GEOID_FT, -1)) for p in P],      # GPS altitude converted to feet above mean sea level
    'gs': [r1(p['gs'], 0) for p in P], 'trk': [r1(p['trk']) for p in P], 'vs': [r1(p['vs'], 0) for p in P],
    'fpa': [r1(p['fpa']) for p in P], 'bank': [r1(p['bank'], 0) for p in P], 'n': [r1(p['n']) for p in P],
    'mach': [r1(p['mach'], 2) for p in P], 'kcas': [r1(p['kcas'], 0) for p in P], 'dist': [r1(p['dist'], 2) for p in P],
}
os.makedirs(os.path.join(ROOT, 'site', 'data'), exist_ok=True)
json.dump(out, open(os.path.join(ROOT, 'site', 'data', 'flight.json'), 'w'), separators=(',', ':'))
print('max smoothing shift: altitude %.0f ft, position %.0f m' % (max(abs(p['ag_draw'] - p['ag']) for p in P), max(math.hypot((p['lat_draw'] - p['lat']) * 111320, (p['lon_draw'] - p['lon']) * 99500) for p in P)))
print('points', len(P), 'first', P[0]['t'], 'impact', out['tImpact'], 'dt to ground %.2f s' % dt, 'bytes', os.path.getsize(os.path.join(ROOT, 'site', 'data', 'flight.json')))
for s in ('17:36:30', '17:45:00', '17:47:00', '17:48:16', '17:48:52', '17:49:16'):
    p = min(P, key=lambda q: abs(q['t'] - sec(s))); print(s, {k: p[k] for k in ('ab', 'ag', 'gs', 'trk', 'vs', 'fpa', 'bank', 'mach', 'kcas')})
