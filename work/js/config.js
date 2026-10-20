// Choreography and quality settings. Timings and camera framings live here so that most
// notes ("zoom slower", "closer on the face", "less glow") are a one-number change.
// Scroll lengths (zoom, travel between stations, per-pair beat) are CSS variables in
// css/work.css: --intro, --lead, --beat.

export const CONFIG = {
  model: {
    // Built by work/tools/model (see its README). Relative to /work/.
    url: 'models/nitsan.glb', // low-poly character, ~5k triangles: one file for every device
    urlLow: null, // optional lighter model for the low quality tier (phones)
    height: 1.83, // the model is scaled to this height in meters
  },

  figure: {
    rim: 0.07, // fresnel edge light on the figure at rest (brand colors); low, so close-ups keep true colors
    rimTravel: 0.3, // extra rim glow while the camera travels between stations
    // Per-material tuning, by the material names in the model (body: skin, hair, shoes, belt;
    // cloth: tee and chinos; metal: chain and buckle; beads: bracelet). envMapIntensity: how much
    // of the studio environment a surface reflects; low keeps the facets' colors clean.
    materials: {
      body: { envMapIntensity: 0.6 },
      cloth: { envMapIntensity: 0.45 },
      metal: { envMapIntensity: 0.7 },
    },
  },

  // The Start button (and a scroll on the first screen) zooms from the full figure to the face.
  start: {
    duration: 2.4, // seconds
  },

  scroll: {
    lerp: 0.085, // Lenis smoothing: lower is smoother and slower
    snap: true, // when you stop scrolling between stations, glide onto the nearest one
    snapForwardFrom: 0.5, // ...if you stopped after 50% of a transition, go forward
    snapBackUntil: 0.5, // ...otherwise go back (set lower to leave the middle free)
  },

  travel: {
    turns: 0, // full turns of the figure between two stations (0 = stays facing you)
    sway: 0.32, // radians the figure sways while the camera travels, back to front at each station
    pullback: 0.18, // extra camera distance in the middle of a transition (m)
  },

  // Full-body framings (camera and target height in m, distance in m, fov in degrees).
  poses: {
    hero: { camY: 1.0, lookY: 0.98, dist: 4.5, fov: 32, formation: 'cloud' },
    outro: { camY: 0.95, lookY: 0.3, dist: 6.4, fov: 30, formation: 'ring' }, // low target lifts the figure above the contact text
  },

  // Stations down the body. A section picks one with `station` in content.json; sections without
  // one are spread down the body in order.
  //   y: height of the station as a fraction of the figure (0 = floor, 1 = top of the head)
  //   span: how much of the body is in view, top to bottom (m)
  //   width: body width at the station (m); the camera pulls back if needed to keep it inside
  //          the clear center column (layout.clear), so cards never cover the body
  //   up: camera height above the station point (m); positive looks down a little
  //   formation: particle shape around the figure (cloud | helix | shell | ring)
  stations: {
    head: { y: 0.925, span: 0.56, width: 0.27, up: 0.02, formation: 'shell', label: 'Head' },
    chest: { y: 0.76, span: 1.0, width: 0.58, up: 0.05, formation: 'helix', label: 'Chest' },
    hands: { y: 0.72, span: 1.22, width: 0.58, up: 0.06, formation: 'helix', label: 'Hands' }, // waist-up, like the photo
    waist: { y: 0.56, span: 0.9, width: 0.5, up: 0.06, formation: 'cloud', label: 'Waist' },
    legs: { y: 0.21, span: 0.86, width: 0.5, up: 0.2, formation: 'cloud', label: 'Legs' },
    feet: { y: 0.05, span: 0.62, width: 0.56, up: 0.06, formation: 'ring', label: 'Feet' }, // low, at sneaker level
  },
  stationFov: 24,

  layout: {
    clear: 0.36, // width of the clear center column, as a fraction of the screen (desktop)
    compactClear: 0.86, // phones: the body uses most of the width above the bottom sheet
    compactSpan: 1.9, // phones: the station fills about half the screen height (above the sheet)
    compactShiftY: 0.21, // phones: lift the body into the upper part of the screen
    compactHero: { distAdd: 1.7, shiftY: 0.12 }, // phones: the full figure sits above the title and Start
  },

  quality: {
    high: { maxDpr: 2, particles: 5000, msaa: 4, bloom: true, shadows: true },
    low: { maxDpr: 1.5, particles: 2000, msaa: 0, bloom: false, shadows: false },
  },

  bloom: { strength: 0.35, radius: 0.4, threshold: 1.8 }, // linear HDR: only emissive highlights (scan, rim edges) cross it
  exposure: 1.0,

  colors: { a: '#00d4ff', b: '#ff006e', scan: '#a8f4ff', light: '#fff1e2' },
};
