# N722BD Reconstruction

Independent, unofficial flight-path reconstruction of the Learjet 60 N722BD accident near Greenacres, Florida, on 1 November 2026.

This is not an NTSB product. The NTSB investigation is ongoing and its findings take precedence over anything here. Estimated values are marked as estimates.

## Layout

- `site/` – the 3D viewer published with GitHub Pages
- `data/` – derived data used by the viewer (track, winds, radar, terrain)
- `analysis/` – scripts that produce the derived data
- `CREDITS.md` – data sources and licenses

## Status

- Done: dive speeds and loads from the ADS-B track with the measured atmosphere (`analysis/dive_loads.py`).
- Next: radar along the track, flight-dynamics model, 3D viewer.

## Reproduce the dive loads

```
cd analysis
python3 dive_loads.py ../data/n722bd-adsb-2026-11-01.csv ../data/n722bd-dive-loads-2026-11-01.csv
```
