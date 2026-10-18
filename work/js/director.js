// The director turns a scroll position into scene state. It measures the real layout, so it
// adapts to any number of sections and items, and holds no timing of its own.
//
//   hero ─ zoom ─ [station 1: one beat per pair of works] ─ travel ─ [station 2] … ─ travel ─ outro
//
// The zoom goes from the full figure to the first station (the face). During a travel the camera
// glides down the body to the next station while the scan, rim and particles play; at a station
// the frame is sticky and each beat of scroll shows the next pair of works (one per beat on phones).
import { clamp, lerp, easeInOutCubic } from './util.js';

export const FORMATIONS = ['cloud', 'helix', 'shell', 'ring'];

export function createDirector({ dom, config }) {
  const N = dom.chapters.length;
  const TAU = Math.PI * 2;
  let stops = [];
  let maxScroll = 0;
  let vh = innerHeight;
  let mode = 'cinematic';
  let compact = false;

  // 100svh probe: the layout uses svh, so measure the same unit.
  const probe = document.createElement('div');
  probe.style.cssText = 'position:absolute;left:0;top:0;width:1px;height:100vh;height:100svh;visibility:hidden;pointer-events:none';
  document.body.appendChild(probe);

  const state = {
    y: 0,
    progress: 0,
    pose: { rot: 0, camY: 1, lookY: 1, dist: 5, fov: 30, shiftX: 0, shiftY: 0, span: 2 },
    formation: new Float32Array(FORMATIONS.length),
    segment: 'stop',
    travel: 0, // 0..1 progress through the current transition (0 when holding)
    scanY: -1, // height of the scan band during a transition (m)
    intro: 0, // 0 on the first screen, 1 once the camera has reached the first station
    stop: 0,
    chapter: -1, // -1 hero, 0..N-1 stations, N outro
    next: -2, // during a transition: the station it is heading to (-2 when holding)
    beats: new Int16Array(N).fill(-1), // active beat per station (-1 = cards hidden)
    presence: new Float32Array(N), // 1 while a station's 3D objects should be on screen
  };

  const docTop = (el) => el.getBoundingClientRect().top + scrollY;
  const formationIndex = (name) => Math.max(0, FORMATIONS.indexOf(name));
  const visibleSpan = (dist, fov) => 2 * dist * Math.tan((fov * Math.PI) / 360);

  // Full-figure framings (hero, outro).
  function wholePose(base) {
    const ch = config.layout.compactHero;
    const dist = base.dist + (compact ? ch.distAdd : 0);
    return {
      rot: 0, camY: base.camY, lookY: base.lookY, dist, fov: base.fov, shiftX: 0, shiftY: compact ? ch.shiftY : 0,
      span: visibleSpan(dist, base.fov), formation: formationIndex(base.formation),
    };
  }

  // Close framing on a station: the body part centered, inside the clear column between the cards.
  function stationPose(st, k) {
    const L = config.layout;
    const H = config.model.height;
    const aspect = innerWidth / Math.max(1, innerHeight);
    const clear = compact ? L.compactClear : L.clear;
    const span = Math.max(st.span * (compact ? L.compactSpan : 1), st.width / (clear * aspect));
    const fov = config.stationFov;
    const lookY = st.y * H;
    return {
      rot: k * config.travel.turns * TAU,
      camY: lookY + st.up,
      lookY,
      dist: span / 2 / Math.tan((fov * Math.PI) / 360),
      fov,
      shiftX: 0,
      shiftY: compact ? L.compactShiftY : 0,
      span,
      formation: formationIndex(st.formation),
    };
  }

  function measure(opts = {}) {
    if (opts.mode) mode = opts.mode;
    if (opts.compact !== undefined) compact = opts.compact;
    vh = probe.offsetHeight || innerHeight;
    maxScroll = Math.max(0, document.documentElement.scrollHeight - innerHeight);
    const cinematic = mode === 'cinematic';

    stops = [{ kind: 'hero', chapter: -1, start: 0, end: 0, pose: wholePose(config.poses.hero) }];

    dom.chapters.forEach((ch, i) => {
      const n = ch.data.items.length;
      const beats = Math.max(1, compact ? n : Math.ceil(n / 2));
      let start, end;
      if (cinematic) {
        start = docTop(ch.track);
        end = start + Math.max(1, ch.track.offsetHeight - vh);
      } else {
        start = docTop(ch.el) - vh * 0.4;
        end = start;
      }
      stops.push({ kind: 'chapter', chapter: i, start, end, beats, beatPx: (end - start) / beats, pose: stationPose(ch.data.station, i + 1) });
    });

    const outroTop = cinematic ? Math.min(docTop(dom.outro), maxScroll) : docTop(dom.outro) - vh * 0.6;
    const outro = wholePose(config.poses.outro);
    outro.rot = (N + 1) * config.travel.turns * TAU;
    stops.push({ kind: 'outro', chapter: N, start: outroTop, end: Infinity, pose: outro });

    // Keep segments ordered even if the layout is momentarily odd (e.g. fonts still loading).
    for (let k = 1; k < stops.length; k++) {
      stops[k].start = Math.max(stops[k].start, stops[k - 1].end);
      if (stops[k].end < stops[k].start) stops[k].end = stops[k].start;
    }
    return api;
  }

  function evaluate(rawY) {
    const y = clamp(rawY, 0, maxScroll);
    state.y = y;
    state.progress = maxScroll ? y / maxScroll : 0;

    let k = 0;
    while (k < stops.length - 1 && stops[k + 1].start <= y) k++;
    const s = stops[k];
    const next = stops[k + 1];
    const P = state.pose;
    const F = state.formation;
    F.fill(0);
    const first = stops[1];
    state.intro = first ? clamp(y / Math.max(1, first.start)) : 1;

    if (mode !== 'cinematic' || !next || y <= s.end) {
      // Holding at a stop (static mode always cuts straight to the stop's pose).
      Object.assign(P, s.pose);
      F[s.pose.formation] = 1;
      state.segment = 'stop';
      state.travel = 0;
      state.scanY = -1;
      state.chapter = s.chapter;
      state.next = -2;
    } else {
      const t = clamp((y - s.end) / Math.max(1, next.start - s.end));
      const a = s.pose, b = next.pose;
      const zoom = s.kind === 'hero';
      // The zoom frames the face early and then dollies in; travels move evenly.
      const eLook = easeInOutCubic(zoom ? clamp(t * 1.25) : t);
      const e = easeInOutCubic(t);
      const bump = Math.sin(Math.PI * t);
      const swayDir = k % 2 ? -1 : 1;
      P.rot = lerp(a.rot, b.rot, e) + bump * config.travel.sway * swayDir * (zoom ? 0.4 : 1);
      P.camY = lerp(a.camY, b.camY, eLook);
      P.lookY = lerp(a.lookY, b.lookY, eLook);
      P.dist = lerp(a.dist, b.dist, e) + bump * config.travel.pullback * (zoom ? 0 : 1);
      P.fov = lerp(a.fov, b.fov, e);
      P.shiftX = lerp(a.shiftX, b.shiftX, e);
      P.shiftY = lerp(a.shiftY, b.shiftY, e);
      P.span = lerp(a.span, b.span, e);
      F[a.formation] += 1 - e;
      F[b.formation] += e;
      // The scan band crosses the view in the direction of travel.
      const dir = b.lookY < a.lookY ? -1 : 1;
      state.scanY = lerp(a.lookY - dir * a.span * 0.6, b.lookY + dir * b.span * 0.6, t);
      state.segment = 'travel';
      state.travel = t;
      state.chapter = t < 0.5 ? s.chapter : next.chapter;
      state.next = next.chapter;
    }
    state.stop = k;

    for (let i = 0; i < N; i++) {
      const c = stops[i + 1];
      const prev = stops[i];
      const after = stops[i + 2];
      if (mode !== 'cinematic') {
        state.beats[i] = -1;
        state.presence[i] = state.chapter === i ? 1 : 0;
        continue;
      }
      // Cards arrive as the camera lands and leave as it sets off again.
      const arrive = c.start - 0.18 * (c.start - prev.end);
      const depart = c.end + 0.18 * (after.start - c.end);
      state.beats[i] = y < arrive || y > depart ? -1 : clamp(Math.floor((y - c.start) / c.beatPx), 0, c.beats - 1);
      const enter = c.start - 0.55 * (c.start - prev.end);
      const leave = c.end + 0.5 * (after.start - c.end);
      state.presence[i] = y >= enter && y <= leave ? 1 : 0;
    }
    return state;
  }

  // Scroll targets for navigation (nav links, dots, keyboard focus).
  function chapterY(i) {
    const c = stops[i + 1];
    if (mode !== 'cinematic') return Math.max(0, docTop(dom.chapters[i].el) - 8);
    return c.start + 2;
  }

  function beatY(i, b) {
    const c = stops[i + 1];
    if (mode !== 'cinematic') return chapterY(i);
    return Math.min(c.end - 2, c.start + b * c.beatPx + 2);
  }

  // The beat that shows item j (pairs on desktop, one per beat on phones).
  const beatOf = (j) => (compact ? j : Math.floor(j / 2));

  // Where to glide when the user stops scrolling in the middle of a transition (or null).
  function snapTarget(y) {
    if (mode !== 'cinematic') return null;
    for (let k = 0; k < stops.length - 1; k++) {
      const a = stops[k], b = stops[k + 1];
      if (y > a.end + 1 && y < b.start - 1) {
        const t = (y - a.end) / (b.start - a.end);
        if (t >= config.scroll.snapForwardFrom) return Math.min(b.start + 2, maxScroll);
        if (t <= config.scroll.snapBackUntil) return a.kind === 'hero' ? 0 : a.end - 2;
        return null;
      }
    }
    return null;
  }

  const api = {
    state,
    measure,
    evaluate,
    chapterY,
    beatY,
    beatOf,
    snapTarget,
    get compact() { return compact; },
    get maxScroll() { return maxScroll; },
    get vh() { return vh; },
    get stops() { return stops; },
  };
  return api;
}
