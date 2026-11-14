# N722BD Reconstruction

Independent, unofficial flight-path reconstruction of the Learjet 60 N722BD accident near Greenacres, Florida, on 1 November 2026.

This is not an NTSB product. The NTSB investigation is ongoing and its findings take precedence over anything here. Estimated values are marked as estimates.

**3D viewer:** https://draventoothman.github.io/n722bd-reconstruction/

## Layout

- `site/` – the 3D viewer published with GitHub Pages (CesiumJS)
  - `site/data/flight.json` – the flight track and computed values the viewer plays back
  - `site/model/learjet60/` – aircraft model (see `CREDITS.md` for its license)
- `data/` – source and derived data (ADS-B track, Miami soundings, dive-loads table, radar along the track)
- `analysis/` – scripts that produce the derived data
- `CREDITS.md` – data sources and licenses

## What the viewer shows

- The whole flight from Austin, with the final dive in detail.
- Ground: Google Photorealistic 3D Tiles (through Cesium ion), with satellite imagery on terrain and USGS aerial imagery as alternatives.
- Readouts at every moment: altitude, vertical speed, groundspeed, Mach, calibrated airspeed, the flight-manual limit at that altitude, path angle, bank and load.
- The stretch of track over which the left elevator is estimated to have separated.
- Weather radar from the Miami (KAMX) NEXRAD radar: a curtain along the flight path and a slice at cruise level.

Mach, airspeed, bank and load are computed, not broadcast. The method and its error bars are described in the viewer under "Sources and method".

## Rebuild the data

```
cd analysis
python3 dive_loads.py ../data/n722bd-adsb-2026-11-01.csv ../data/n722bd-dive-loads-2026-11-01.csv
python3 radar.py <folder with the KAMX .ar2v files>    # optional; needs arm-pyart, scipy, pillow
python3 build_site_data.py
```

The radar volume files are not in this repository (about 14 MB each). They are NOAA NEXRAD Level II data for KAMX, 1 November 2026, volumes starting 17:40:32, 17:45:48 and 17:51:04 UTC, available from NOAA NCEI.

## Run the viewer locally

```
cd site
python3 -m http.server 8000
```

Then open http://localhost:8000. The Cesium ion key in `site/js/app.js` only works on the published site, so a local copy falls back to USGS aerial imagery.

## Publishing

Every push that changes `site/` runs `.github/workflows/pages.yml`, which publishes the `site/` folder. GitHub Pages must be switched on once: repository **Settings → Pages → Source → GitHub Actions**.

## Radio captions, audio and weather notes

`analysis/build_comms.py` writes `site/data/comms.json`: a hand-checked machine transcript of the 116 s air-traffic-control clip, and weather notes
(Convective SIGMET 45E, airport reports, pilot reports, soundings) from the public archives saved under `data/weather/`.
The audio file is not in this repository. Visitors can load their own copy in the viewer; it plays locally in the browser only.
The clip has no clock; it is placed at 17:47:29 UTC by matching the pilot's descent callouts to the ADS-B descent (about +/-4 s).
