// Choreography and quality settings. Timings and camera framings live here so that most
// notes ("turn slower", "closer on the face", "less glow") are a one-number change.
// Scroll lengths (lead-in and per-item beat) are CSS variables in css/work.css: --lead, --beat.

export const CONFIG = {
  model: {
    url: 'models/placeholder-figure.glb', // relative to /work/; swap for the real model
    height: 1.8, // the model is scaled to this height (scene units = meters)
  },

  scroll: {
    lerp: 0.085, // Lenis smoothing: lower is smoother and slower
    snap: true, // when you stop scrolling near a section, glide onto it
    snapForwardFrom: 0.6, // ...if you stopped after 60% of a transition, go forward
    snapBackUntil: 0.12, // ...if you stopped before 12%, go back
  },

  travel: {
    turns: 1, // full turns of the figure between two sections
    pullback: 0.9, // extra camera distance in the middle of a transition
    lift: 0.25, // extra camera height in the middle of a transition
  },

  // Camera framings. `stops` apply to the sections in order and cycle if there are more sections.
  //   camY / lookY: camera and target height (m) · dist: distance from the figure · fov: degrees
  //   formation: particle shape around the figure (cloud | helix | shell | ring)
  poses: {
    hero: { camY: 1.0, lookY: 0.98, dist: 4.5, fov: 32, formation: 'cloud' },
    stops: [
      { camY: 1.5, lookY: 1.28, dist: 3.7, fov: 30, formation: 'helix' },
      { camY: 0.75, lookY: 1.02, dist: 4.9, fov: 30, formation: 'ring' },
      { camY: 1.2, lookY: 1.12, dist: 4.6, fov: 30, formation: 'shell' },
      { camY: 1.55, lookY: 1.32, dist: 3.6, fov: 30, formation: 'cloud' },
    ],
    outro: { camY: 1.0, lookY: 0.66, dist: 5.6, fov: 30, formation: 'ring' }, // low target lifts the figure above the contact text
    turnToPanel: 0.38, // radians the figure turns toward the text panel at a stop
    sideShift: 0.2, // how far the figure moves away from the text panel (fraction of screen width)
    compact: { distAdd: 1.0, shiftY: 0.15 }, // phones: pull back and lift the figure above the panel
  },

  quality: {
    high: { maxDpr: 2, particles: 4200 },
    low: { maxDpr: 1.5, particles: 1700 },
  },

  colors: { a: '#00d4ff', b: '#ff006e', scan: '#a8f4ff', light: '#fff4e8' },
};
