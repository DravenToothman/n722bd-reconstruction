"""Weather radar along the N722BD flight path, from Miami (KAMX) NEXRAD Level II volume scans.

Inputs are the .ar2v files NOAA NCEI delivers for a Level II order (KAMX, 1 Nov 2026, 17:40:32, 17:45:48 and
17:51:04 UTC volumes). They are not kept in this repository (about 14 MB each).

Usage: python3 analysis/radar.py <folder with the .ar2v files>

Writes:
  data/n722bd-radar-along-track.csv   reflectivity at the aircraft, strongest echo in the column, echo top
  site/data/radar_curtain.png         reflectivity along the ground track, surface to 16 km
  site/data/radar_level.png           reflectivity at cruise level (11.25 km above sea level)
  site/data/radar.json                where the two images sit, and the colour scale
"""
import csv, datetime, glob, json, math, os, struct, sys, tempfile, warnings
warnings.filterwarnings('ignore')
import numpy as np
import pyart
from PIL import Image
from scipy.interpolate import RegularGridInterpolator
from atmosphere import GEOID_FT

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.join(HERE, '..')
sec = lambda u: int(u[:2]) * 3600 + int(u[3:5]) * 60 + float(u[6:])
hhmmss = lambda t: '%02d:%02d:%02d' % (t // 3600, t % 3600 // 60, t % 60)
T0, T1 = sec('17:41:00'), sec('17:49:33.2')            # level at FL350 until impact
T_CURTAIN = sec('17:44:00')
Z = np.arange(0, 16001, 500.0)                          # metres above the radar
Y = np.arange(70000, 152001, 1000.0)                    # metres north of the radar
X = np.arange(-62000, 50001, 1000.0)                    # metres east of the radar
LEVEL_M = 11250.0                                       # cruise level, metres above sea level (about 36,900 ft)
UPPER_SCAN_DELAY = 210.0                                # the tilts that reach cruise level are scanned about 3.5 min into a volume

def read_volume(path):
    """Read one Level II volume. The archived 17:45:48 volume is missing its 24-byte volume header and its
    metadata record (it starts straight at the radial data), so a standard header is added for such files."""
    name = os.path.basename(path); when = datetime.datetime.strptime(name[4:19], '%Y%m%d_%H%M%S')
    raw = open(path, 'rb').read()
    if not raw.startswith(b'AR2V'):
        days = (when.date() - datetime.date(1970, 1, 1)).days + 1
        raw = b'AR2V0006.001' + struct.pack('>II', days, (when.hour * 3600 + when.minute * 60 + when.second) * 1000) + name[:4].encode() + raw
    with tempfile.NamedTemporaryFile(suffix='_V06', delete=False) as tmp:
        tmp.write(raw)
    try: radar = pyart.io.read_nexrad_archive(tmp.name)
    finally: os.unlink(tmp.name)
    return radar, when.hour * 3600 + when.minute * 60 + when.second

def grid_volume(radar):
    gf = pyart.filters.GateFilter(radar); gf.exclude_invalid('reflectivity'); gf.exclude_below('reflectivity', -5)
    g = pyart.map.grid_from_radars(radar, grid_shape=(len(Z), len(Y), len(X)), grid_limits=((Z[0], Z[-1]), (Y[0], Y[-1]), (X[0], X[-1])),
                                   fields=['reflectivity'], gatefilters=gf, roi_func='dist_beam', weighting_function='Barnes2')
    return np.ma.filled(g.fields['reflectivity']['data'], -20.0).astype('f4')

files = sorted(glob.glob(os.path.join(sys.argv[1], 'KAMX20261101_17[45]*_V06.ar2v')))
files = [f for f in files if os.path.basename(f)[13:19] in ('174032', '174548', '175104')]
vols = []
for f in files:
    radar, t_start = read_volume(f)
    vols.append(dict(t=t_start, grid=grid_volume(radar), lat=float(radar.latitude['data'][0]), lon=float(radar.longitude['data'][0]), alt=float(radar.altitude['data'][0])))
    print('gridded', os.path.basename(f), 'max dBZ %.0f' % vols[-1]['grid'].max())
LAT0, LON0, ALT0 = vols[0]['lat'], vols[0]['lon'], vols[0]['alt']
interp = [RegularGridInterpolator((Z, Y, X), v['grid'], bounds_error=False, fill_value=-20.0) for v in vols]
t_eff = [v['t'] + UPPER_SCAN_DELAY for v in vols]

def xy(lat, lon):
    x, y = pyart.core.geographic_to_cartesian_aeqd(np.atleast_1d(lon), np.atleast_1d(lat), LON0, LAT0)
    return x, y
def sample(t, lat, lon, z_msl):
    """Reflectivity at points (arrays), blended in time between the two volumes nearest the aircraft's time."""
    x, y = xy(lat, lon); pts = np.stack([np.broadcast_to(np.asarray(z_msl) - ALT0, x.shape), y, x], -1)
    k = int(np.clip(np.searchsorted(t_eff, t) - 1, 0, len(vols) - 2)); w = float(np.clip((t - t_eff[k]) / (t_eff[k + 1] - t_eff[k]), 0, 1))
    return interp[k](pts) * (1 - w) + interp[k + 1](pts) * w

# ---- along the track
rows = [r for r in csv.DictReader(open(os.path.join(ROOT, 'data', 'n722bd-adsb-2026-11-01.csv'))) if r['alt_geom_ft'] and T0 <= sec(r['utc']) <= T1]
out = []
for r in rows:
    t, lat, lon = sec(r['utc']), float(r['lat']), float(r['lon']); z = (float(r['alt_geom_ft']) + GEOID_FT) * 0.3048
    col = sample(t, np.full(len(Z), lat), np.full(len(Z), lon), Z + ALT0)
    here = float(sample(t, lat, lon, z)[0]); top = Z[col >= 18].max() + ALT0 if (col >= 18).any() else None
    out.append([r['utc'], lat, lon, int(round(z / 0.3048, -1)), round(here, 1) if here > -10 else '', round(float(col.max()), 1) if col.max() > -10 else '', '' if top is None else int(round(top / 0.3048, -2))])
with open(os.path.join(ROOT, 'data', 'n722bd-radar-along-track.csv'), 'w', newline='') as fh:
    w = csv.writer(fh); w.writerow('utc,lat,lon,alt_msl_ft,dbz_at_aircraft,dbz_column_max,echo_top_18dbz_ft'.split(',')); w.writerows(out)

# ---- colour scale (dBZ -> RGBA)
STOPS = [(5, (120, 190, 235, 45)), (15, (70, 150, 225, 95)), (20, (60, 185, 120, 150)), (30, (240, 220, 70, 190)), (40, (245, 150, 50, 205)), (50, (225, 50, 45, 220)), (60, (200, 60, 200, 230))]
def colour(dbz):
    dbz = np.asarray(dbz, float); rgba = np.zeros(dbz.shape + (4,), float)
    xs = [s[0] for s in STOPS]
    for c in range(4): rgba[..., c] = np.interp(dbz, xs, [s[1][c] for s in STOPS])
    rgba[dbz < 5] = 0
    return rgba.astype('u1')

# ---- curtain along the ground track, uniform in distance
tr = [(sec(r['utc']), float(r['lat']), float(r['lon'])) for r in rows if sec(r['utc']) >= T_CURTAIN] + [(T1, 26.63282, -80.11312)]
tt = np.array([p[0] for p in tr]); la = np.array([p[1] for p in tr]); lo = np.array([p[2] for p in tr])
d = np.r_[0, np.cumsum(np.hypot(np.diff(la) * 111320, np.diff(lo) * 111320 * np.cos(np.radians(la[:-1]))))]
n = int(d[-1] // 200) + 1; du = np.linspace(0, d[-1], n)
lat_u, lon_u, t_u = np.interp(du, d, la), np.interp(du, d, lo), np.interp(du, d, tt)
zc = np.arange(0, 16001, 250.0)
cur = np.stack([sample(t_u[i], np.full(len(zc), lat_u[i]), np.full(len(zc), lon_u[i]), zc) for i in range(n)], 1)   # (height, distance)
img = Image.fromarray(colour(cur[::-1]), 'RGBA').resize((n * 4, len(zc) * 4), Image.BILINEAR)
img.save(os.path.join(ROOT, 'site', 'data', 'radar_curtain.png'), optimize=True)

# ---- level slice at cruise height, on a latitude/longitude grid, from the volume that covers the dive
lats = np.arange(26.33, 26.951, 0.005); lons = np.arange(-80.95, -79.949, 0.005)
LO, LA = np.meshgrid(lons, lats); x, y = xy(LA.ravel(), LO.ravel())
lev = interp[1](np.stack([np.full(x.shape, LEVEL_M - ALT0), y, x], -1)).reshape(LA.shape)
Image.fromarray(colour(lev[::-1]), 'RGBA').resize((len(lons) * 2, len(lats) * 2), Image.BILINEAR).save(os.path.join(ROOT, 'site', 'data', 'radar_level.png'), optimize=True)

json.dump({
    'curtain': {'image': 'data/radar_curtain.png', 'lat': [round(v, 5) for v in lat_u], 'lon': [round(v, 5) for v in lon_u], 'topMslM': 16000, 'from': hhmmss(T_CURTAIN)},
    'level': {'image': 'data/radar_level.png', 'west': round(float(lons[0]), 4), 'east': round(float(lons[-1]), 4), 'south': round(float(lats[0]), 4), 'north': round(float(lats[-1]), 4), 'mslM': LEVEL_M, 'scan': hhmmss(vols[1]['t'])},
    'scans': [hhmmss(v['t']) for v in vols], 'geoidM': round(GEOID_FT * 0.3048, 1),
    'legend': [{'dbz': s[0], 'rgb': list(s[1][:3])} for s in STOPS],
}, open(os.path.join(ROOT, 'site', 'data', 'radar.json'), 'w'), separators=(',', ':'))
print('track rows', len(out), 'curtain', cur.shape, 'level', lev.shape, 'level max %.0f dBZ' % lev.max())
for s in ('17:41:30', '17:43:00', '17:44:00', '17:45:00', '17:46:00', '17:47:00', '17:47:30', '17:47:56', '17:48:16', '17:48:30', '17:48:52', '17:49:16', '17:49:30'):
    r = min(out, key=lambda o: abs(sec(o[0]) - sec(s))); print(r[0][:8], 'alt', r[3], 'dBZ at aircraft', r[4], 'column max', r[5], 'echo top', r[6])
