/* N722BD flight-path viewer. Loads data/flight.json and draws the flight on a CesiumJS globe. */
(async function () {
  'use strict';

  // Cesium ion access token. It is restricted to https://draventoothman.github.io, so it only works on the published site.
  const ION_TOKEN = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJub25jZSI6IlRkMTJWWU5JdWFtUjJEVDgiLCJqdGkiOiIxM2NhNjUwNi0yN2M5LTQyYzYtODkxMy1hYjgzMDU2YTdhMzYiLCJpZCI6NTQ5MDY4LCJzdWIiOiJEcmF2ZW5Ub290aG1hbiIsImlzcyI6Imh0dHBzOi8vYXBpLmNlc2l1bS5jb20iLCJhdWQiOiJuNzIyYmQtc2l0ZSIsImlhdCI6MTc5NDYzNjE3NX0.ye5o7aUXJTA6HRnU0Bq-3PEfMLnNjxV2P8PkTF-bk9w';
  const C = window.Cesium;
  C.Ion.defaultAccessToken = ION_TOKEN;

  const $ = (id) => document.getElementById(id);
  const rad = C.Math.toRadians;
  const hms = (s) => { const p = s.split(':').map(Number); return p[0] * 3600 + p[1] * 60 + (p[2] || 0); };
  const clamp = (x, a, b) => Math.max(a, Math.min(b, x));
  const nf = (x) => Math.round(x).toLocaleString('en-US');
  const two = (n) => String(Math.floor(n)).padStart(2, '0');
  const clock8 = (t) => two(t / 3600) + ':' + two((t % 3600) / 60) + ':' + two(t % 60);

  // ---------------------------------------------------------------- data
  const F = await (await fetch('data/flight.json')).json();
  const N = F.t.length;
  const RADAR = await fetch('data/radar.json').then((r) => (r.ok ? r.json() : null)).catch(() => null);
  const T_START = F.t[0], T_IMPACT = F.tImpact, T_END = T_IMPACT + 20, T_DIVE = F.tDive;
  const T_ELEV0 = hms('17:48:52'), T_ELEV1 = hms('17:49:16');   // stretch of track 3.8 to 1.3 miles from the site
  const H_GROUND = F.h[N - 1];                                   // ground height at the site, metres above the ellipsoid
  const RADAR_T0 = hms('17:41:00');                               // radar sampling starts when the jet levels at FL350
  const AOA = 2;                                                 // nominal angle of attack added to the path angle, degrees
  const DAY0 = C.JulianDate.fromIso8601(F.date + 'T00:00:00Z');
  const jd = (t) => C.JulianDate.addSeconds(DAY0, t, new C.JulianDate());
  const secOf = (j) => C.JulianDate.secondsDifference(j, DAY0);
  let commsApi = {};                                              // radio and weather module, set up after the data loads
  let bias = 0;                                                  // metres added to every height so the path meets the drawn ground

  function indexAt(t) {
    let lo = 0, hi = N - 1;
    while (hi - lo > 1) { const m = (lo + hi) >> 1; if (F.t[m] <= t) lo = m; else hi = m; }
    return lo;
  }
  function stateAt(t) {
    t = clamp(t, T_START, T_IMPACT);
    const i = indexAt(t), j = Math.min(i + 1, N - 1), f = clamp((t - F.t[i]) / ((F.t[j] - F.t[i]) || 1), 0, 1);
    const L = (k) => { const a = F[k][i], b = F[k][j]; return a == null ? b : b == null ? a : a + (b - a) * f; };
    const dTrk = ((F.trk[j] - F.trk[i] + 540) % 360) - 180;
    return { t, i, lat: L('lat'), lon: L('lon'), h: L('h'), trk: (F.trk[i] + dTrk * f + 360) % 360, fpa: L('fpa'), bank: L('bank'),
      gs: L('gs'), vs: L('vs'), mach: L('mach'), kcas: L('kcas'), n: L('n'), dist: L('dist'), dbz: L('dbz'), top: L('top'),
      altBaro: F.altBaro[i] == null || F.altBaro[j] == null ? null : L('altBaro'), altGps: L('altGps') };
  }
  const posOf = (s, result) => C.Cartesian3.fromDegrees(s.lon, s.lat, s.h + bias, C.Ellipsoid.WGS84, result);

  // Limits from the Learjet 60 Airplane Flight Manual, Section I (primary instruments)
  function limitAt(altFt) {
    if (altFt >= 26750) return { kind: 'mach', value: altFt <= 37000 ? 0.81 : altFt >= 43000 ? 0.78 : 0.81 - 0.03 * (altFt - 37000) / 6000 };
    if (altFt >= 23000) return { kind: 'cas', value: 330 };
    if (altFt >= 20000) return { kind: 'cas', value: 340 - 10 * (altFt - 20000) / 3000 };
    if (altFt >= 8000) return { kind: 'cas', value: 340 };
    return { kind: 'cas', value: 300 };
  }
  function exceedance(s) {   // 1.0 = at the limit
    if (s.mach == null || s.kcas == null) return 0;
    const lim = limitAt(s.altBaro != null ? s.altBaro : s.altGps);
    return lim.kind === 'mach' ? s.mach / lim.value : s.kcas / lim.value;
  }

  // ---------------------------------------------------------------- viewer
  const viewer = new C.Viewer('scene', {
    animation: false, timeline: false, baseLayerPicker: false, geocoder: false, homeButton: false, sceneModePicker: false,
    navigationHelpButton: false, fullscreenButton: false, infoBox: false, selectionIndicator: false,
    baseLayer: false, shouldAnimate: false, scene3DOnly: true,
  });
  const scene = viewer.scene, camera = viewer.camera, clock = viewer.clock;
  window.__viewer = viewer;
  scene.globe.baseColor = C.Color.fromCssColorString('#1b2733');
  scene.globe.depthTestAgainstTerrain = true;
  scene.screenSpaceCameraController.minimumZoomDistance = 8;

  clock.startTime = jd(T_START); clock.stopTime = jd(T_END); clock.currentTime = jd(hms('17:47:40'));
  clock.clockRange = C.ClockRange.CLAMPED; clock.clockStep = C.ClockStep.SYSTEM_CLOCK_MULTIPLIER; clock.multiplier = 1;
  const now = () => secOf(clock.currentTime);

  // ---------------------------------------------------------------- aircraft
  const NWU = C.Transforms.localFrameToFixedFrameGenerator('north', 'west');
  const scratchPos = new C.Cartesian3(), scratchQ = new C.Quaternion(), scratchHpr = new C.HeadingPitchRoll(), ONE = new C.Cartesian3(1, 1, 1);
  const tracker = viewer.entities.add({
    position: new C.CallbackPositionProperty((time, result) => posOf(stateAt(secOf(time)), result), false),
    // a near-invisible point: the camera only follows an entity that has something drawable
    point: { pixelSize: 1, color: C.Color.WHITE.withAlpha(0.01) },
  });
  let model = null, elevNode = null;
  try {
    model = await C.Model.fromGltfAsync({ url: 'model/learjet60/scene.gltf', minimumPixelSize: 54, maximumScale: 600 });
    scene.primitives.add(model);
    model.readyEvent.addEventListener(() => { try { elevNode = model.getNode('elevator_left'); } catch (e) { elevNode = null; } });
  } catch (e) { console.warn('Aircraft model failed to load', e); }

  function updateAircraft(t) {
    const s = stateAt(t);
    if (model) {
      const p = posOf(s, scratchPos);
      scratchHpr.heading = rad(s.trk); scratchHpr.pitch = rad(s.fpa + AOA); scratchHpr.roll = rad(s.bank);
      const q = C.Transforms.headingPitchRollQuaternion(p, scratchHpr, C.Ellipsoid.WGS84, NWU, scratchQ);
      model.modelMatrix = C.Matrix4.fromTranslationQuaternionRotationScale(p, q, ONE, model.modelMatrix);
      model.show = t < T_IMPACT;
      if (elevNode) elevNode.show = t < T_ELEV0 ? true : t < T_ELEV1 ? Math.floor(t * 4) % 2 === 0 : false;
    }
    return s;
  }

  let camMode = 'chase';

  // ---------------------------------------------------------------- track, curtain, labels
  const cBase = C.Color.fromCssColorString('#d6ecff'), cLimit = C.Color.fromCssColorString('#ffd23f'), cOver = C.Color.fromCssColorString('#ff2d2d');
  function trackColor(i) {
    const x = exceedance({ mach: F.mach[i], kcas: F.kcas[i], altBaro: F.altBaro[i], altGps: F.altGps[i] });
    if (x <= 1) return cBase;
    return C.Color.lerp(cLimit, cOver, clamp((x - 1) / 0.8, 0, 1), new C.Color());
  }
  const EVENTS = [
    ['17:36:56', 'Descent to FL350'],
    ['17:45:00', 'Turbulence and ice reported'],
    ['17:47:02', 'Right turn toward Freeport'],
    ['17:47:56', 'Climb toward FL370 begins'],
    ['17:48:16', 'Dive begins · Mach 0.76'],
    ['17:48:29', 'Mach limit 0.81 passed'],
    ['17:48:45', '340 kt passed'],
    ['17:48:52', 'Bank 63° · spiral · 3.8 mi out'],
    ['17:49:16', 'Bank past 90° · 1.3 mi out'],
    ['17:49:23', 'Pressure altitude stops at 8,750 ft'],
  ];
  const notes = new C.CustomDataSource('notes'); viewer.dataSources.add(notes);
  const debris = new C.CustomDataSource('debris'); viewer.dataSources.add(debris);
  const radarDs = new C.CustomDataSource('radar'); viewer.dataSources.add(radarDs);
  let trackPrim = null, curtain = null, diveSphere = null;
  const labelStyle = (text) => ({
    text, font: '13px system-ui, sans-serif', fillColor: C.Color.WHITE, showBackground: true,
    backgroundColor: C.Color.fromCssColorString('#090d13').withAlpha(0.78), backgroundPadding: new C.Cartesian2(7, 4),
    horizontalOrigin: C.HorizontalOrigin.LEFT, verticalOrigin: C.VerticalOrigin.CENTER, pixelOffset: new C.Cartesian2(12, 0),
    disableDepthTestDistance: Number.POSITIVE_INFINITY, distanceDisplayCondition: new C.DistanceDisplayCondition(0, 160000),
  });
  function ring(miles) {
    const out = [], R = miles * 1609.344, lat0 = rad(F.crater[0]);
    for (let a = 0; a <= 360; a += 3) out.push(F.crater[1] + C.Math.toDegrees((R * Math.sin(rad(a))) / (6371000 * Math.cos(lat0))), F.crater[0] + C.Math.toDegrees((R * Math.cos(rad(a))) / 6371000));
    return C.Cartesian3.fromDegreesArray(out);
  }
  function buildStatic() {
    if (trackPrim) scene.primitives.remove(trackPrim);
    const positions = [], colors = [], wall = [], wallMin = [];
    for (let i = 0; i < N; i++) {
      const p = C.Cartesian3.fromDegrees(F.lon[i], F.lat[i], F.h[i] + bias);
      positions.push(p); colors.push(trackColor(i));
      if (F.t[i] >= hms('17:47:30')) { wall.push(p); wallMin.push(H_GROUND + bias); }
    }
    trackPrim = scene.primitives.add(new C.Primitive({
      geometryInstances: new C.GeometryInstance({ geometry: new C.PolylineGeometry({ positions, colors, colorsPerVertex: true, width: 4, arcType: C.ArcType.NONE, vertexFormat: C.PolylineColorAppearance.VERTEX_FORMAT }) }),
      appearance: new C.PolylineColorAppearance({ translucent: false }), asynchronous: false,
    }));
    diveSphere = C.BoundingSphere.fromPoints(wall);
    notes.entities.removeAll();
    curtain = notes.entities.add({ wall: { positions: wall, minimumHeights: wallMin, material: C.Color.fromCssColorString('#8fd8ff').withAlpha(0.2), outline: false }, show: curtainOn() });
    const showLabels = $('lyLabels').checked;
    EVENTS.forEach(([time, text]) => {
      notes.entities.add({ position: posOf(stateAt(hms(time))), show: showLabels, point: { pixelSize: 7, color: C.Color.WHITE, outlineColor: C.Color.BLACK, outlineWidth: 1, disableDepthTestDistance: Number.POSITIVE_INFINITY, distanceDisplayCondition: new C.DistanceDisplayCondition(0, 160000) }, label: labelStyle(text), properties: { kind: 'label' } });
    });
    notes.entities.add({ position: C.Cartesian3.fromDegrees(F.crater[1], F.crater[0], H_GROUND + bias + 1), point: { pixelSize: 11, color: cOver, outlineColor: C.Color.WHITE, outlineWidth: 2, disableDepthTestDistance: Number.POSITIVE_INFINITY, distanceDisplayCondition: new C.DistanceDisplayCondition(0, 400000) }, label: labelStyle('Impact 17:49:33 UTC · Military Trail') });
  }
  function buildDebris() {
    debris.entities.removeAll();
    [1.3, 3.8].forEach((mi) => debris.entities.add({ polyline: { positions: ring(mi), clampToGround: true, width: 2.5, material: new C.PolylineDashMaterialProperty({ color: C.Color.fromCssColorString('#ffb020'), dashLength: 14 }) } }));
    const top = ring(3.8)[0], c = C.Cartographic.fromCartesian(top);
    debris.entities.add({ position: C.Cartesian3.fromRadians(c.longitude, c.latitude, H_GROUND + bias + 30), label: Object.assign(labelStyle('Left elevator pieces found 1.3 to 3.8 mi from the site (NTSB); directions not released'), { horizontalOrigin: C.HorizontalOrigin.CENTER, pixelOffset: new C.Cartesian2(0, -14), distanceDisplayCondition: new C.DistanceDisplayCondition(3000, 60000) }) });
    debris.show = $('lyDebris').checked;
  }
  // Weather radar: a curtain along the ground track and a level slice at cruise height
  let radarPath = null, radarLevel = null;
  const radarFull = new C.Color(1, 1, 1, 1);
  const radarFaint = new C.Color(1, 1, 1, 0.4);   // close-up cameras look along the curtain, so it is drawn fainter there
  const curtainOn = () => $('lyCurtain').checked && !(RADAR && $('lyRadarPath').checked);   // the two curtains share a plane
  function buildRadar() {
    radarDs.entities.removeAll(); radarPath = radarLevel = null;
    if (!RADAR) return;
    const c = RADAR.curtain, n = c.lat.length, pos = [], lo = [], hi = [];
    for (let i = 0; i < n; i++) { pos.push(C.Cartesian3.fromDegrees(c.lon[i], c.lat[i])); lo.push(H_GROUND + bias); hi.push(c.topMslM - RADAR.geoidM + bias); }
    radarPath = radarDs.entities.add({ show: $('lyRadarPath').checked, wall: { positions: pos, minimumHeights: lo, maximumHeights: hi, material: new C.ImageMaterialProperty({ image: c.image, transparent: true, color: new C.CallbackProperty((time, result) => C.Color.clone(camMode === 'chase' || camMode === 'street' ? radarFaint : radarFull, result || new C.Color()), false) }) } });
    const v = RADAR.level;
    radarLevel = radarDs.entities.add({ show: $('lyRadarLevel').checked, rectangle: { coordinates: C.Rectangle.fromDegrees(v.west, v.south, v.east, v.north), height: v.mslM - RADAR.geoidM + bias, material: new C.ImageMaterialProperty({ image: v.image, transparent: true }) } });
  }
  function radarUi() {
    if (radarPath) radarPath.show = $('lyRadarPath').checked;
    if (radarLevel) radarLevel.show = $('lyRadarLevel').checked;
    if (curtain) curtain.show = curtainOn();
    $('lyCurtain').disabled = !!(RADAR && $('lyRadarPath').checked);
    $('radarLegend').hidden = !(RADAR && ($('lyRadarPath').checked || $('lyRadarLevel').checked));
  }
  if (!RADAR) { document.querySelectorAll('label.radar').forEach((l) => { l.hidden = true; }); $('rowRadar').hidden = true; }
  $('lyRadarPath').addEventListener('change', radarUi); $('lyRadarLevel').addEventListener('change', radarUi);
  buildStatic(); buildDebris(); buildRadar(); radarUi();
  $('lyCurtain').addEventListener('change', radarUi);
  $('lyLabels').addEventListener('change', (e) => notes.entities.values.forEach((en) => { if (en.properties && en.properties.kind) en.show = e.target.checked; }));
  $('lyDebris').addEventListener('change', (e) => { debris.show = e.target.checked; });

  // ---------------------------------------------------------------- ground layers
  let tiles = null, buildings = null, groundMode = null, groundSeq = 0;
  const USGS_URL = 'https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/tile/{z}/{y}/{x}';
  const GROUND_NAMES = { photoreal: 'Photoreal 3D', satellite: 'Satellite', usgs: 'USGS aerial' };
  function clearGround() {
    if (tiles) { scene.primitives.remove(tiles); tiles = null; }
    if (buildings) { scene.primitives.remove(buildings); buildings = null; }
    viewer.imageryLayers.removeAll();
  }
  async function loadGround(mode) {
    if (mode === 'photoreal') {
      const t = await C.createGooglePhotorealistic3DTileset({ onlyUsingWithGoogleGeocoder: true });
      clearGround(); tiles = scene.primitives.add(t); scene.globe.show = false;
    } else if (mode === 'satellite') {
      const [imagery, terrain] = await Promise.all([C.IonImageryProvider.fromAssetId(2), C.createWorldTerrainAsync()]);
      clearGround(); scene.globe.show = true; viewer.terrainProvider = terrain; viewer.imageryLayers.addImageryProvider(imagery);
      C.createOsmBuildingsAsync().then((b) => { if (groundMode === 'satellite') buildings = scene.primitives.add(b); }).catch(() => {});
    } else {
      clearGround(); scene.globe.show = true; viewer.terrainProvider = new C.EllipsoidTerrainProvider();
      viewer.imageryLayers.addImageryProvider(new C.UrlTemplateImageryProvider({ url: USGS_URL, maximumLevel: 16, credit: 'USDA, USGS The National Map: Orthoimagery' }));
    }
  }
  async function calibrate(mode, seq) {   // make the path meet the ground that is actually drawn at the impact site
    const carto = C.Cartographic.fromDegrees(F.crater[1], F.crater[0]); let h;
    try {
      if (mode === 'photoreal') { const r = await scene.sampleHeightMostDetailed([carto], [model, trackPrim].filter(Boolean)); h = r[0] && r[0].height; }
      else if (mode === 'satellite') { const r = await C.sampleTerrainMostDetailed(viewer.terrainProvider, [carto]); h = r[0] && r[0].height; }
      else h = 0;
    } catch (e) { h = undefined; }
    if (seq !== groundSeq || typeof h !== 'number' || !isFinite(h) || Math.abs(h - H_GROUND) > 80) return;
    bias = h - H_GROUND; buildStatic(); buildDebris(); buildRadar();
  }
  async function setGround(mode, isFallback) {
    const seq = ++groundSeq, order = ['photoreal', 'satellite', 'usgs'];
    for (let k = order.indexOf(mode); k < order.length; k++) {
      try {
        await loadGround(order[k]); if (seq !== groundSeq) return;
        groundMode = order[k]; bias = order[k] === 'usgs' ? -H_GROUND : 0; buildStatic(); buildDebris(); buildRadar();
        document.querySelectorAll('[data-ground]').forEach((b) => b.classList.toggle('on', b.dataset.ground === groundMode));
        $('groundNote').textContent = order[k] === mode ? '' : GROUND_NAMES[mode] + ' could not be loaded here, so ' + GROUND_NAMES[order[k]] + ' is shown instead.';
        calibrate(groundMode, seq);
        return;
      } catch (e) { console.warn('Ground layer failed: ' + order[k], e); }
    }
    $('groundNote').textContent = 'No ground imagery could be loaded.';
  }
  document.querySelectorAll('[data-ground]').forEach((b) => b.addEventListener('click', () => setGround(b.dataset.ground)));

  // ---------------------------------------------------------------- camera
  const STREET = { lat: 26.6222, lon: -80.11295 };   // on Military Trail, about 0.7 mi south of the site (approximate)
  const scratchDir = new C.Cartesian3(), scratchUp = new C.Cartesian3(), scratchCam = new C.Cartesian3();
  function setCam(mode) {
    camMode = mode;
    document.querySelectorAll('[data-cam]').forEach((b) => b.classList.toggle('on', b.dataset.cam === mode));
    viewer.trackedEntity = undefined; camera.lookAtTransform(C.Matrix4.IDENTITY);
    scene.screenSpaceCameraController.enableInputs = mode !== 'street';
    if (mode === 'chase') {
      const s = stateAt(now()), h = rad(s.trk), back = 75;
      tracker.viewFrom = new C.Cartesian3(-Math.sin(h) * back, -Math.cos(h) * back, 24 - Math.sin(rad(s.fpa)) * 40);
      viewer.trackedEntity = tracker;
    } else if (mode === 'overview') {
      camera.flyToBoundingSphere(diveSphere, { offset: new C.HeadingPitchRange(rad(205), rad(-20), diveSphere.radius * 3.0), duration: 1.2 });
    } else if (mode === 'top') {
      camera.flyToBoundingSphere(diveSphere, { offset: new C.HeadingPitchRange(0, rad(-90), diveSphere.radius * 4.0), duration: 1.2 });
    }
  }
  scene.preRender.addEventListener(() => {
    if (camMode !== 'street') return;
    const eye = C.Cartesian3.fromDegrees(STREET.lon, STREET.lat, H_GROUND + bias + 5, C.Ellipsoid.WGS84, scratchCam);
    const t = now(), target = t < T_IMPACT ? posOf(stateAt(t), scratchPos) : C.Cartesian3.fromDegrees(F.crater[1], F.crater[0], H_GROUND + bias + 20, C.Ellipsoid.WGS84, scratchPos);
    C.Cartesian3.normalize(C.Cartesian3.subtract(target, eye, scratchDir), scratchDir);
    C.Ellipsoid.WGS84.geodeticSurfaceNormal(eye, scratchUp);
    camera.setView({ destination: eye, orientation: { direction: scratchDir, up: scratchUp } });
  });
  document.querySelectorAll('[data-cam]').forEach((b) => b.addEventListener('click', () => setCam(b.dataset.cam)));

  // ---------------------------------------------------------------- sequence panel
  const CHAPTERS = [
    { t: '15:37:12', title: 'Takeoff from Austin', body: 'N722BD leaves Austin, Texas, for North Eleuthera in the Bahamas with two crew and seven passengers.', src: 'NTSB; ADS-B' },
    { t: '16:00:29', title: 'Cruise at 41,000 ft', body: 'The jet levels at flight level 410 and cruises for about 95 minutes over the Gulf of Mexico.', src: 'ADS-B' },
    { t: '17:36:56', title: 'Descent to 35,000 ft', body: 'With heavy storms ahead over south Florida, the jet descends to flight level 350 and turns left to go around weather.', src: 'ADS-B; air traffic audio as reported' },
    { t: '17:45:00', title: 'Turbulence and ice', body: 'A pilot report stamped 17:45 from a Learjet 60 at flight level 350 gives −46 °C and light clear ice. The Miami weather balloon measured −48 °C at this height. On the radio, the crew reports moderate turbulence, −47 °C and managing the ice; that call is heard in the clip at about 17:47:40.', src: 'Pilot report; Miami sounding; radio audio' },
    { t: '17:47:02', title: 'Turn toward Freeport', body: 'A right turn from about 050° to 099°, heading for Freeport.', src: 'ADS-B' },
    { t: '17:48:08', title: 'Asks for FL370, approved', body: 'In the radio clip the crew says they are picking up precipitation and asks to climb to flight level 370. The controller approves and asks them to stay no further right than their present heading, for traffic. Timing comes from the audio alignment (about ±4 s). By that alignment the small climb that began at 17:47:56 started before the request.', src: 'Radio audio; ADS-B' },
    { t: '17:47:56', title: 'Climb begins, into a storm top', body: 'The jet climbs about 450 ft in 20 seconds. Groundspeed rises during the climb, which argues against a low-speed stall. Here the path enters the upper part of a growing storm cell: radar shows echo of about 30 dBZ at the jet’s altitude above a heavy core, with the cell top near 45,000 ft. Five minutes earlier the same spot showed only weak echo at this height.', src: 'ADS-B; Miami radar, scanned 17:49 UTC' },
    { t: '17:48:16', title: 'Dive begins', body: 'The nose drops with the wings level. For 16 seconds the heading stays at 099° while the jet flies at roughly 0.2 to 0.6 g. Speed at this moment is about Mach 0.76, inside the limits. In the radio clip the crew declares Mayday about 8 seconds into the dive, at about 17:48:24, and reports descending at 10,000 ft/min.', src: 'ADS-B; computed; radio audio' },
    { t: '17:48:29', title: 'Past the Mach limit', body: 'The jet passes its Mach 0.81 limit about 13 seconds into the dive. The crew reports an overspeed condition at about 17:48:34, descending at 20,000 ft/min.', src: 'Computed; radio audio; NTSB' },
    { t: '17:48:37', title: 'Steady 22° dive', body: 'The dive holds near 22° nose-down and 20,000 ft/min at Mach 0.88 to 0.89 while a right bank builds to about 60°. Airspeed passes 340 kt, the highest limit at any altitude. About 20 seconds later the crew says they are banking sixty degrees.', src: 'Computed; radio audio' },
    { t: '17:48:52', title: 'Spiral', body: 'The bank passes 65° and keeps growing; the nose falls through. This point is 3.8 miles from the impact site, the distance of the farthest piece of the left elevator. Speed here is Mach 0.89 and about 360 kt.', src: 'Computed; NTSB' },
    { t: '17:49:16', title: 'Near-vertical', body: 'Bank is past 90° and the path is 52° nose-down at about 48,000 ft/min, Mach 0.93 and 480 kt. This point is 1.3 miles out, the distance of the nearest elevator piece.', src: 'Computed; NTSB' },
    { t: '17:49:23', title: 'Pressure altitude stops', body: 'The broadcast pressure altitude freezes at 8,750 ft. GPS altitude keeps reporting. Descent peaks near 58,000 ft/min at Mach 0.94 to 0.96 and about 575 kt, roughly three times the air load at the airspeed limit.', src: 'ADS-B; computed' },
    { t: '17:49:33', title: 'Impact', body: 'The jet strikes Military Trail between Cresthaven Boulevard and 10th Avenue North, about 77 seconds after the dive began. All nine people on board were killed.', src: 'ADS-B; NTSB' },
  ].map((c) => Object.assign(c, { sec: hms(c.t) })).sort((a, b) => a.sec - b.sec);
  const chapterEls = CHAPTERS.map((c) => {
    const li = document.createElement('li'), b = document.createElement('button');
    b.innerHTML = '<time>' + c.t + '</time><span></span>'; b.lastChild.textContent = c.title;
    b.addEventListener('click', () => seek(c.sec, true)); li.appendChild(b); $('chapters').appendChild(li); return li;
  });
  let chapterNow = -1;
  function updateChapter(t) {
    let k = 0; for (let i = 0; i < CHAPTERS.length; i++) if (CHAPTERS[i].sec <= t + 0.01) k = i;
    if (k === chapterNow) return; chapterNow = k;
    chapterEls.forEach((li, i) => li.classList.toggle('now', i === k));
    const box = $('chapterText'); box.textContent = '';
    const p = document.createElement('p'); p.textContent = CHAPTERS[k].body;
    const s = document.createElement('p'); s.className = 'src'; s.textContent = 'Source: ' + CHAPTERS[k].src;
    box.appendChild(p); box.appendChild(s);
    chapterEls[k].scrollIntoView({ block: 'nearest' });
  }

  // ---------------------------------------------------------------- readouts
  const unit = (v, u) => v + '<small>' + u + '</small>';
  function updateHud(s, t) {
    $('hUtc').textContent = clock8(Math.min(t, T_END));
    $('hLocal').textContent = clock8(Math.min(t, T_END) - 5 * 3600) + ' EST';
    const baro = s.altBaro;
    $('hAlt').innerHTML = baro == null ? 'stopped' : unit(nf(Math.round(baro / 25) * 25), 'ft'); $('hAlt').classList.toggle('warn', baro == null);
    $('hGps').innerHTML = unit(nf(Math.round(s.altGps / 10) * 10), 'ft');
    $('hVs').innerHTML = unit((s.vs < 0 ? '−' : s.vs > 0 ? '+' : '') + nf(Math.abs(Math.round(s.vs / 100) * 100)), 'ft/min');
    $('hGs').innerHTML = unit(nf(s.gs), 'kt');
    $('hMach').textContent = s.mach == null ? '—' : s.mach.toFixed(2);
    $('hCas').innerHTML = s.kcas == null ? '—' : unit(nf(s.kcas), 'kt');
    const lim = limitAt(baro != null ? baro : s.altGps); let over = false, text = '—';
    if (s.mach != null) {
      if (lim.kind === 'mach') { over = s.mach > lim.value + 0.004; text = 'Mach ' + lim.value.toFixed(2) + (over ? ' · over by ' + (s.mach - lim.value).toFixed(2) : ' · within'); }
      else { over = s.kcas > lim.value + 0.5; text = nf(lim.value) + ' kt' + (over ? ' · over by ' + nf(s.kcas - lim.value) + ' kt' : ' · within'); }
    }
    $('hLimit').textContent = text; $('hLimit').classList.toggle('over', over);
    $('rowMach').classList.toggle('over', over && lim.kind === 'mach'); $('rowCas').classList.toggle('over', over && lim.kind === 'cas');
    $('hFpa').innerHTML = unit((s.fpa < -0.05 ? '−' : '') + Math.abs(s.fpa).toFixed(0), '°');
    $('hBank').innerHTML = unit(Math.abs(s.bank).toFixed(0), '°' + (Math.abs(s.bank) < 1.5 ? '' : s.bank > 0 ? ' right' : ' left'));
    $('hG').innerHTML = s.n == null ? '—' : unit(s.n.toFixed(1), 'g');
    $('hDist').innerHTML = s.dist == null ? '—' : unit(s.dist.toFixed(1), 'mi');
    const e = $('hElev');
    e.textContent = t < T_ELEV0 ? 'Attached' : t < T_ELEV1 ? 'Separating (timing estimated)' : 'Separated';
    $('hStatus').hidden = t < T_IMPACT;
    if (RADAR) {
      const z = s.dbz, word = z == null || z < 5 ? '' : z < 20 ? 'light' : z < 35 ? 'moderate' : z < 50 ? 'heavy' : 'intense';
      $('hRadar').textContent = s.t < RADAR_T0 ? '—' : z == null || z < 5 ? 'None or weak' : Math.round(z) + ' dBZ (' + word + ')' + (s.top ? ' · echo top ' + nf(Math.round(s.top / 1000) * 1000) + ' ft' : '');
    }
    e.classList.toggle('warn', t >= T_ELEV0 && t < T_ELEV1); e.classList.toggle('over', t >= T_ELEV1);
  }

  // ---------------------------------------------------------------- playback
  const WINDOWS = { dive: [hms('17:47:25'), T_END], last: [hms('17:34:00'), T_END], all: [T_START, T_END] };
  let win = 'dive';
  const scrubber = $('scrubber');
  function setPlaying(on) { clock.shouldAnimate = on; $('btnPlay').textContent = on ? '❚❚' : '▶'; $('btnPlay').setAttribute('aria-label', on ? 'Pause' : 'Play'); }
  function seek(t, keepWindow) {
    t = clamp(t, T_START, T_END);
    if (keepWindow && (t < WINDOWS[win][0] || t > WINDOWS[win][1])) setWindow(t < WINDOWS.last[0] ? 'all' : t < WINDOWS.dive[0] ? 'last' : 'dive', true);
    clock.currentTime = jd(t);
    if (camMode === 'chase' && viewer.trackedEntity !== tracker) setCam('chase');
  }
  function setWindow(name, keepTime) {
    win = name; document.querySelectorAll('[data-win]').forEach((b) => b.classList.toggle('on', b.dataset.win === name));
    const [a, b] = WINDOWS[name], ticks = $('ticks'); ticks.textContent = '';
    CHAPTERS.forEach((c) => { if (c.sec < a || c.sec > b) return; const i = document.createElement('i'); i.style.left = ((c.sec - a) / (b - a)) * 100 + '%'; if (c.sec === T_DIVE || c.title === 'Impact') i.className = 'key'; i.title = c.t + ' ' + c.title; ticks.appendChild(i); });
    if (!keepTime && (now() < a || now() > b)) clock.currentTime = jd(a);
  }
  $('btnPlay').addEventListener('click', () => {
    if (!clock.shouldAnimate && now() >= T_END - 0.05) clock.currentTime = jd(WINDOWS[win][0]);
    setPlaying(!clock.shouldAnimate);
  });
  document.querySelectorAll('[data-speed]').forEach((b) => b.addEventListener('click', () => {
    clock.multiplier = Number(b.dataset.speed); document.querySelectorAll('[data-speed]').forEach((x) => x.classList.toggle('on', x === b));
  }));
  document.querySelectorAll('[data-win]').forEach((b) => b.addEventListener('click', () => setWindow(b.dataset.win)));
  let scrubbing = false;
  scrubber.addEventListener('input', () => { scrubbing = true; const [a, b] = WINDOWS[win]; clock.currentTime = jd(a + (scrubber.value / 1000) * (b - a)); });
  scrubber.addEventListener('change', () => { scrubbing = false; });
  document.addEventListener('keydown', (e) => {
    if (e.target.closest('input, dialog')) return;
    if (e.code === 'Space' && !e.target.closest('button')) { e.preventDefault(); $('btnPlay').click(); }
    else if (e.code === 'ArrowRight') seek(now() + (e.shiftKey ? 5 : 1));
    else if (e.code === 'ArrowLeft') seek(now() - (e.shiftKey ? 5 : 1));
  });
  $('btnAbout').addEventListener('click', () => $('about').showModal());

  clock.onTick.addEventListener(() => {
    const t = now();
    if (clock.shouldAnimate && t >= T_END - 0.01) setPlaying(false);
    const s = updateAircraft(t);
    updateHud(s, t); updateChapter(t); if (commsApi.update) commsApi.update(t);
    if (!scrubbing) { const [a, b] = WINDOWS[win]; scrubber.value = String(Math.round(clamp((t - a) / (b - a), 0, 1) * 1000)); }
  });


  // ---------------------------------------------------------------- radio captions, audio and weather notes
  const COMMS = await fetch('data/comms.json').then((r) => (r.ok ? r.json() : null)).catch(() => null);
  if (COMMS) {
    const AUDIO_T0 = hms(COMMS.audioT0);
    let syncOff = 0;                                              // listener nudge, seconds (positive = audio later)
    const clipT = (a) => AUDIO_T0 + syncOff + a;                  // UTC seconds at clip second a
    const clipAt = (t) => t - AUDIO_T0 - syncOff;                 // clip second at UTC seconds t
    const WHO = { atc: 'Miami Center', crew: 'N722BD crew', wx: 'Weather' };
    COMMS.weather.forEach((w) => { w.sec = hms(w.t); });
    const mk = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };

    // panel lists
    const radioItems = COMMS.radio.map((l) => {
      const li = mk('li', l.unc ? 'unc' : ''), b = mk('button'), tm = mk('time');
      b.appendChild(tm); b.appendChild(mk('span', 'who ' + l.who, WHO[l.who])); b.appendChild(mk('span', 'txt', l.text));
      if (l.note) b.appendChild(mk('span', 'nt', l.note));
      b.addEventListener('click', () => seek(clipT(l.s), true));
      li.appendChild(b); $('radioList').appendChild(li); return { li, tm, l };
    });
    const showTimes = () => radioItems.forEach((r) => { r.tm.textContent = clock8(Math.round(clipT(r.l.s))); });
    showTimes();
    const wxItems = COMMS.weather.map((w) => {
      const li = mk('li'), b = mk('button'), tm = mk('time', null, w.t.slice(0, 5));
      b.appendChild(tm); b.appendChild(mk('span', 'kind', { sigmet: 'SIGMET', pirep: 'Pilot report', metar: 'Airport', sounding: 'Balloon', radar: 'Radar', after: 'After' }[w.kind] || w.kind)); b.appendChild(mk('span', 'ttl', w.title));
      b.appendChild(mk('span', 'bd', w.body)); b.appendChild(mk('span', 'src', 'Source: ' + w.src));
      b.addEventListener('click', () => seek(w.sec, true));
      li.appendChild(b); $('wxList').appendChild(li); return { li, w };
    });

    // captions over the scene
    const capBox = $('captions'); let capKey = '';
    function updateComms(t) {
      const a = clipAt(t), lines = [];
      radioItems.forEach((r) => { const on = a >= r.l.s - 0.15 && a <= r.l.e + 2.2; r.li.classList.toggle('now', a >= r.l.s - 0.15 && a <= r.l.e + 0.5); if (on) lines.push({ who: r.l.who, text: r.l.text, unc: r.l.unc, k: 'r' + r.l.s }); });
      let lastWx = -1; wxItems.forEach((x, i) => { if (x.w.sec <= t) lastWx = i; x.li.classList.toggle('future', x.w.sec > t); });
      wxItems.forEach((x, i) => x.li.classList.toggle('now', i === lastWx));
      const wxNow = lastWx >= 0 && t - wxItems[lastWx].w.sec < 12 && t >= wxItems[lastWx].w.sec ? wxItems[lastWx].w : null;
      const show = lines.slice(-2); const key = show.map((x) => x.k).join('|') + (wxNow ? '|' + wxNow.t : '');
      if (key !== capKey) {
        capKey = key; capBox.textContent = '';
        show.forEach((x) => { const d = mk('div', 'cap' + (x.unc ? ' unc' : '')); d.appendChild(mk('span', 'who ' + x.who, WHO[x.who])); d.appendChild(mk('span', 'txt', x.text)); capBox.appendChild(d); });
        if (wxNow) { const d = mk('div', 'cap'); d.appendChild(mk('span', 'who wx', 'Weather')); d.appendChild(mk('span', 'txt', wxNow.title + ' — see Radio & weather')); capBox.appendChild(d); }
        capBox.hidden = !capBox.childNodes.length;
      }
      if (!$('comms').hidden) {
        const cur = $('radioList').querySelector('li.now'); if (cur && cur.dataset.seen !== '1') { cur.dataset.seen = '1'; cur.scrollIntoView({ block: 'nearest' }); }
        $('radioList').querySelectorAll('li:not(.now)').forEach((x) => { x.dataset.seen = ''; });
        const wcur = $('wxList').querySelector('li.now'); if (wcur && wcur.dataset.seen !== '1') { wcur.dataset.seen = '1'; if (!$('tabWx').hidden) wcur.scrollIntoView({ block: 'nearest' }); }
      }
    }

    // panel open / tabs
    const panel = $('comms');
    const setPanel = (open) => { panel.hidden = !open; document.body.classList.toggle('commsOpen', open); $('btnComms').setAttribute('aria-expanded', String(open)); };
    $('btnComms').addEventListener('click', () => setPanel(panel.hidden));
    $('btnCommsClose').addEventListener('click', () => setPanel(false));
    document.querySelectorAll('[data-tab]').forEach((b) => b.addEventListener('click', () => {
      document.querySelectorAll('[data-tab]').forEach((x) => { x.classList.toggle('on', x === b); x.setAttribute('aria-selected', String(x === b)); });
      $('tabRadio').hidden = b.dataset.tab !== 'radio'; $('tabWx').hidden = b.dataset.tab !== 'wx';
    }));

    // audio: the person's own copy of the clip, played locally and kept in step with the flight clock
    const audio = new Audio(); audio.preload = 'auto';
    let audioReady = false;
    $('btnAudio').addEventListener('click', () => $('audioFile').click());
    $('audioFile').addEventListener('change', () => {
      const f = $('audioFile').files[0]; if (!f) return;
      if (audio.src) URL.revokeObjectURL(audio.src);
      audio.src = URL.createObjectURL(f); audioReady = true; audio.volume = Number($('audioVol').value);
      $('audioName').textContent = 'Loaded: ' + f.name; $('audioCtl').hidden = false; $('btnClip').disabled = false;
      $('audioNote').textContent = 'Audio plays at 1× and ¼× speed while the flight is playing. It stays in your browser; nothing is uploaded.';
    });
    $('audioVol').addEventListener('input', () => { audio.volume = Number($('audioVol').value); });
    const setSync = (v) => { syncOff = Math.round(v * 10) / 10; $('syncVal').textContent = (syncOff > 0 ? '+' : syncOff < 0 ? '−' : '') + Math.abs(syncOff).toFixed(1) + ' s'; showTimes(); };
    $('syncMinus').addEventListener('click', () => setSync(syncOff - 1));
    $('syncPlus').addEventListener('click', () => setSync(syncOff + 1));
    $('btnClip').addEventListener('click', () => {
      document.querySelectorAll('[data-speed]').forEach((b) => { if (b.dataset.speed === '1') b.click(); });
      seek(clipT(0), true); setPlaying(true);
    });
    function syncAudio(t) {
      if (!audioReady) return;
      const a = clipAt(t), m = clock.multiplier, ok = clock.shouldAnimate && t < T_END - 0.05 && (m === 1 || m === 0.25) && a >= 0 && a < (audio.duration || COMMS.audioDur);
      if (!ok) { if (!audio.paused) audio.pause(); return; }
      if (audio.playbackRate !== m) { audio.preservesPitch = true; audio.playbackRate = m; }
      if (audio.paused || Math.abs(audio.currentTime - a) > 0.45) { audio.currentTime = a; if (audio.paused) audio.play().catch(() => { $('audioNote').textContent = 'The browser blocked audio playback. Click Play on the flight, or the clip button, once more.'; }); }
    }
    commsApi = { update: (t) => { updateComms(t); syncAudio(t); }, state: () => ({ audioT: audio.currentTime, audioPaused: audio.paused, rate: audio.playbackRate, syncOff, audioReady, captions: capBox.textContent, panel: !panel.hidden }), setSync };
  }

  // ---------------------------------------------------------------- start
  setWindow('dive', true);
  window.__app = { comms: () => commsApi, model, seek, setCam, setGround, setWindow, setPlaying, hms, stateAt, state: () => ({ groundMode, bias, camMode, t: now(), elev: !!elevNode }) };
  await setGround('photoreal');
  setCam('chase');
  $('loading').classList.add('gone');
})().catch((err) => {
  console.error(err);
  const el = document.getElementById('loading');
  if (el) { el.classList.remove('gone'); el.textContent = 'The viewer could not start: ' + (err && err.message ? err.message : err); }
});
