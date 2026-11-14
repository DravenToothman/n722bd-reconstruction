"""Speeds and loads through the N722BD dive, from the ADS-B track and the measured atmosphere.
Usage: python3 analysis/dive_loads.py data/n722bd-adsb-2026-11-01.csv data/n722bd-dive-loads-2026-11-01.csv"""
import csv, math, sys
from atmosphere import at
rows = list(csv.DictReader(open(sys.argv[1])))
sec = lambda u: int(u[:2]) * 3600 + int(u[3:5]) * 60 + float(u[6:])
P = [dict(t=sec(r['utc']), u=r['utc'], lat=float(r['lat']), lon=float(r['lon']), ab=float(r['alt_baro_ft']), gs=float(r['gs_kt']),
          trk=float(r['track_deg']), ag=float(r['alt_geom_ft'])) for r in rows if r['utc'] >= '17:47:30' and r['alt_geom_ft'] != '']
IMP = (26.6328, -80.1131); CL = math.cos(math.radians(26.66)); W = 3.0
def fit(a, p, key):   # least-squares slope of key over a +-3 s window
    tm = sum(q['t'] for q in a) / len(a); m = sum(key(q) for q in a) / len(a); den = sum((q['t'] - tm) ** 2 for q in a)
    return sum((q['t'] - tm) * (key(q) - m) for q in a) / den if den > 0 else 0
for p in P:
    a = [q for q in P if abs(q['t'] - p['t']) <= W]
    p['vs'] = fit(a, p, lambda q: q['ag'])
    p['tr'] = fit(a, p, lambda q: (q['trk'] - p['trk'] + 540) % 360 - 180)
    T, pr, rho, wu, wv = at(p['ag'])
    tk = math.radians(p['trk'])
    ax, ay = p['gs'] * math.sin(tk) - wu, p['gs'] * math.cos(tk) - wv      # air-relative horizontal velocity
    vsk = p['vs'] * 0.592484; hor = math.hypot(ax, ay)
    p['tas'] = math.hypot(hor, vsk); p['M'] = p['tas'] / (38.967 * math.sqrt(T))
    p['eas'] = p['tas'] * math.sqrt(rho / 0.0023769); p['q'] = 0.5 * rho * (p['tas'] * 1.68781) ** 2
    qc = pr * ((1 + 0.2 * p['M'] ** 2) ** 3.5 - 1)                         # impact pressure, hPa (subsonic)
    p['cas'] = 661.4786 * math.sqrt(5 * ((qc / 1013.25 + 1) ** (2 / 7) - 1))   # calibrated airspeed, what the airspeed limits are written in
    p['gam'] = math.degrees(math.atan2(vsk, hor)); p['oat'] = T - 273.15
    p['wd'] = (math.degrees(math.atan2(-wu, -wv)) + 360) % 360; p['ws'] = math.hypot(wu, wv)
    p['d'] = math.hypot((p['lon'] - IMP[1]) * 60 * CL, (p['lat'] - IMP[0]) * 60) * 1.15078
for p in P:
    a = [q for q in P if abs(q['t'] - p['t']) <= W]
    gd = math.radians(fit(a, p, lambda q: q['gam'])); V = p['tas'] * 1.68781; g = 32.174
    nv = math.cos(math.radians(p['gam'])) + V * gd / g
    nh = V * math.cos(math.radians(p['gam'])) * math.radians(p['tr']) / g
    p['n'] = math.hypot(nv, nh); p['bank'] = math.degrees(math.atan2(nh, nv))
w = csv.writer(open(sys.argv[2], 'w', newline=''))
w.writerow("utc,lat,lon,alt_baro_ft,alt_geom_ft,gs_kt,track_deg,vs_geom_fpm,tas_kt,mach,kcas,keas,q_psf,fpa_deg,turn_dps,load_factor_g,bank_deg,dist_to_crater_sm,oat_c,wind_dir_deg,wind_kt".split(','))
for p in P:
    w.writerow([p['u'], p['lat'], p['lon'], int(p['ab']), int(p['ag']), p['gs'], p['trk'], round(p['vs'] * 60, -2), round(p['tas']), round(p['M'], 2), round(p['cas']),
                round(p['eas']), round(p['q']), round(p['gam'], 1), round(p['tr'], 1), round(p['n'], 1), round(p['bank']), round(p['d'], 2),
                round(p['oat'], 1), round(p['wd']), round(p['ws'])])
pk = lambda k: max(P, key=lambda q: abs(q[k]))
print("first M>=0.81:", next(p['u'] for p in P if p['M'] >= 0.81), "| M at 17:48:17:", min(P, key=lambda q: abs(q['t'] - sec('17:48:17')))['M'])
for k in ('vs', 'tas', 'M', 'cas', 'eas', 'q'):
    p = pk(k); print(f"peak {k}: {p[k]*(60 if k=='vs' else 1):.2f} at {p['u']} alt {p['ag']:.0f}")
for th in (330, 340, 400, 460, 560): print('KCAS', th, next(((p['u'], round(p['ag']), round(p['d'], 2), round(p['M'], 2)) for p in P if p['cas'] >= th), None))
for s in ('17:48:17', '17:48:27', '17:48:37', '17:48:44', '17:48:52', '17:49:00', '17:49:08', '17:49:16', '17:49:27', '17:49:32'):
    p = min(P, key=lambda q: abs(q['t'] - sec(s)))
    print(f"{p['u'][:8]} geo {p['ag']:6.0f} vs {p['vs']*60:7.0f} M {p['M']:.2f} KCAS {p['cas']:3.0f} KEAS {p['eas']:3.0f} q {p['q']:4.0f} fpa {p['gam']:5.1f} bank {p['bank']:4.0f} n {p['n']:.1f} d {p['d']:.2f}")
