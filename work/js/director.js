// The director turns a scroll position into scene state. It measures the real layout, so it
// adapts to any number of sections and items, and holds no timing of its own.
//
//   hero ─ travel ─ [stop: section 1, one beat per item] ─ travel ─ [stop: section 2] … ─ travel ─ outro
//
// During a travel the figure turns (CONFIG.travel.turns) and the camera moves between framings.
// During a stop the frame is sticky, the figure holds, and each beat of scroll shows the next item.
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
    pose: { rot: 0, camY: 1, lookY: 1, dist: 5, fov: 30, shiftX: 0, shiftY: 0 },
    formation: new Float32Array(FORMATIONS.length),
    segment: 'stop',
    travel: 0, // 0..1 progress through the current transition (0 when stopped)
    stop: 0,
    chapter: -1, // -1 hero, 0..N-1 sections, N outro
    items: new Int16Array(N).fill(-1), // active item per section (-1 = the section's intro card)
    presence: new Float32Array(N), // 1 while a section's 3D objects should be on screen
    side: 'left',
  };

  const docTop = (el) => el.getBoundingClientRect().top + scrollY;

  function pose(base, rot, side, isChapter) {
    const p = config.poses;
    const sideSign = side === 'left' ? 1 : -1;
    return {
      rot,
      camY: base.camY,
      lookY: base.lookY,
      dist: base.dist + (compact ? p.compact.distAdd : 0),
      fov: base.fov,
      shiftX: isChapter && !compact ? sideSign * p.sideShift : 0,
      shiftY: isChapter && compact ? p.compact.shiftY : 0,
      formation: Math.max(0, FORMATIONS.indexOf(base.formation)),
    };
  }

  function measure(opts = {}) {
    if (opts.mode) mode = opts.mode;
    if (opts.compact !== undefined) compact = opts.compact;
    vh = probe.offsetHeight || innerHeight;
    maxScroll = Math.max(0, document.documentElement.scrollHeight - innerHeight);

    const p = config.poses;
    const turn = config.travel.turns * TAU;
    const facing = (side) => (compact ? 0 : side === 'left' ? -p.turnToPanel : p.turnToPanel);
    const cinematic = mode === 'cinematic';

    stops = [{ kind: 'hero', chapter: -1, start: 0, end: cinematic ? vh * 0.1 : 0, pose: pose(p.hero, 0, 'left', false) }];

    dom.chapters.forEach((ch, i) => {
      const k = i + 1;
      const side = ch.data.side;
      const base = p.stops[i % p.stops.length];
      const beats = ch.items.length; // intro card + one per item
      let start, end;
      if (cinematic) {
        start = docTop(ch.track);
        end = start + Math.max(1, ch.track.offsetHeight - vh);
      } else {
        start = docTop(ch.el) - vh * 0.4;
        end = start;
      }
      stops.push({ kind: 'chapter', chapter: i, start, end, beats, beatPx: (end - start) / beats, side, pose: pose(base, k * turn + facing(side), side, true) });
    });

    const outroTop = cinematic ? Math.min(docTop(dom.outro), maxScroll) : docTop(dom.outro) - vh * 0.6;
    stops.push({ kind: 'outro', chapter: N, start: outroTop, end: Infinity, pose: pose(p.outro, (N + 1) * turn, 'left', false) });

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

    if (mode !== 'cinematic' || !next || y <= s.end) {
      // Holding at a stop (static mode always cuts straight to the stop's pose).
      Object.assign(P, s.pose);
      F[s.pose.formation] = 1;
      state.segment = 'stop';
      state.travel = 0;
      state.chapter = s.chapter;
      state.side = s.side ?? 'left';
    } else {
      const t = clamp((y - s.end) / Math.max(1, next.start - s.end));
      const e = easeInOutCubic(t);
      const a = s.pose, b = next.pose;
      const bump = Math.sin(Math.PI * t);
      P.rot = lerp(a.rot, b.rot, e);
      P.camY = lerp(a.camY, b.camY, e) + bump * config.travel.lift;
      P.lookY = lerp(a.lookY, b.lookY, e);
      P.dist = lerp(a.dist, b.dist, e) + bump * config.travel.pullback;
      P.fov = lerp(a.fov, b.fov, e);
      P.shiftX = lerp(a.shiftX, b.shiftX, e);
      P.shiftY = lerp(a.shiftY, b.shiftY, e);
      F[a.formation] += 1 - e;
      F[b.formation] += e;
      state.segment = 'travel';
      state.travel = t;
      state.chapter = t < 0.5 ? s.chapter : next.chapter;
      state.side = (t < 0.5 ? s.side : next.side) ?? 'left';
    }
    state.stop = k;

    for (let i = 0; i < N; i++) {
      const c = stops[i + 1];
      const prev = stops[i];
      const after = stops[i + 2];
      if (mode !== 'cinematic') {
        state.items[i] = -1;
        state.presence[i] = state.chapter === i ? 1 : 0;
        continue;
      }
      state.items[i] = y < c.start ? -1 : y >= c.end ? c.beats - 2 : clamp(Math.floor((y - c.start) / c.beatPx), 0, c.beats - 1) - 1;
      const enter = c.start - 0.55 * (c.start - prev.end);
      const leave = c.end + 0.45 * (after.start - c.end);
      state.presence[i] = y >= enter && y <= leave ? 1 : 0;
    }
    return state;
  }

  // Scroll targets for navigation (nav links, item dots, keyboard focus).
  function chapterY(i) {
    const c = stops[i + 1];
    if (mode !== 'cinematic') return Math.max(0, docTop(dom.chapters[i].el) - 8);
    return c.start + 2;
  }

  function beatY(i, j) {
    const c = stops[i + 1];
    if (mode !== 'cinematic') {
      const el = dom.chapters[i].items[j + 1];
      return Math.max(0, docTop(el) - vh * 0.2);
    }
    return Math.min(c.end - 2, c.start + (j + 1) * c.beatPx + 2);
  }

  // Where to glide when the user stops scrolling in the middle of a transition (or null).
  function snapTarget(y) {
    if (mode !== 'cinematic') return null;
    for (let k = 0; k < stops.length - 1; k++) {
      const a = stops[k], b = stops[k + 1];
      if (y > a.end && y < b.start) {
        const t = (y - a.end) / (b.start - a.end);
        if (t >= config.scroll.snapForwardFrom) return Math.min(b.start + 2, maxScroll);
        if (t <= config.scroll.snapBackUntil && a.kind !== 'hero') return a.end - 2;
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
    snapTarget,
    get maxScroll() { return maxScroll; },
    get vh() { return vh; },
    get stops() { return stops; },
  };
  return api;
}
