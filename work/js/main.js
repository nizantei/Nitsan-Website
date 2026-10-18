// Entry point for /work/. Boot order: decide mode → render content → load 3D (if any) →
// measure layout → start the frame loop. The 3D scene is imported on demand, so the
// no-WebGL path never downloads Three.js.
import { CONFIG } from './config.js';
import { detectEnv, applyModeClass, COMPACT_QUERY } from './env.js';
import { loadContent, normalize, renderContent } from './content.js';
import { createDirector } from './director.js';
import { createScroller } from './scroller.js';
import { createStart } from './start.js';
import { createUI } from './ui.js';

const root = document.documentElement;
const env = detectEnv();
let mode = env.mode;
applyModeClass(mode);
root.classList.toggle('is-touch', env.touch);
if ('scrollRestoration' in history) history.scrollRestoration = 'manual';

const pctEl = document.querySelector('[data-loader-pct]');
const barEl = document.querySelector('[data-loader-bar]');
const setProgress = (p) => {
  pctEl.textContent = `${Math.round(p * 100)}`.padStart(3, '0');
  barEl.style.transform = `scaleX(${p})`;
};

// A reload mid-page returns to the same place (and skips the Start screen).
const SAVED = 'work:scroll';
const savedY = (() => {
  try {
    const saved = JSON.parse(sessionStorage.getItem(SAVED) || 'null');
    return saved && saved.hash === location.hash ? +saved.y || 0 : 0;
  } catch { return 0; }
})();
addEventListener('pagehide', () => {
  try { sessionStorage.setItem(SAVED, JSON.stringify({ y: Math.round(scrollY), hash: location.hash })); } catch { /* storage unavailable */ }
});

boot().catch((err) => {
  console.error('[work] boot failed', err);
  root.classList.add('is-loaded');
});

async function boot() {
  const content = normalize(await loadContent(), CONFIG);
  const dom = renderContent(content, CONFIG);

  let stage = null;
  if (mode !== 'poster') {
    try {
      const { createStage } = await import('./scene/stage.js');
      stage = await createStage({ canvas: document.querySelector('.webgl'), env, content, config: CONFIG, onProgress: setProgress });
    } catch (err) {
      console.error('[work] 3D unavailable, showing the still image instead', err);
      mode = 'poster';
      applyModeClass(mode);
    }
  }
  if (mode === 'poster') {
    const poster = document.querySelector('.poster');
    poster.src = poster.dataset.src;
  }

  const compactQuery = matchMedia(COMPACT_QUERY);
  const director = createDirector({ dom, config: CONFIG });
  const scroller = createScroller({ smooth: mode === 'cinematic' && !env.touch, config: CONFIG });
  const start = createStart({ dom, director, scroller, config: CONFIG, getMode: () => mode });
  const ui = createUI({ dom, director, scroller, start, env, config: CONFIG, getMode: () => mode });
  const measure = () => {
    director.measure({ mode, compact: compactQuery.matches });
    stage?.setStops(director.stops);
  };

  await document.fonts?.ready;
  measure();

  // Re-measure whenever the layout can change.
  let resizeTimer;
  addEventListener('resize', () => {
    stage?.resize();
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(measure, 120);
  });
  new ResizeObserver(() => measure()).observe(document.querySelector('main'));

  // Follow the reduced-motion setting live (unless a mode was forced in the URL).
  if (!env.forcedMode && mode !== 'poster') {
    env.reducedQuery.addEventListener('change', (e) => {
      mode = e.matches ? 'static' : 'cinematic';
      applyModeClass(mode);
      start.release();
      scroller.setSmooth(mode === 'cinematic' && !env.touch);
      stage?.setMotion(mode === 'cinematic');
      ui.reset();
      measure();
    });
  }

  // Deep link (#apps etc.) or a reload mid-page skips the Start screen.
  const target = location.hash ? dom.chapters.findIndex((c) => `#${c.data.id}` === location.hash) : -1;
  if (savedY > 2) scroller.scrollTo(Math.min(savedY, director.maxScroll), { immediate: true });
  else if (target >= 0) scroller.scrollTo(director.chapterY(target), { immediate: true });
  else start.arm();

  if (env.debug) window.__work = { director, scroller, start, settle: () => stage?.settle(), get mode() { return mode; } };

  setProgress(1);
  root.classList.add('is-loaded', 'is-ready');
  stage?.startIntro();

  let last = performance.now();
  const tick = (now) => {
    requestAnimationFrame(tick);
    const dt = Math.min(0.05, (now - last) / 1000);
    last = now;
    scroller.raf(now, dt);
    const state = director.evaluate(scroller.y);

    // When the visitor stops between stations, glide onto the nearest one.
    if (CONFIG.scroll.snap && mode === 'cinematic' && !scroller.busy && !scroller.locked && !start.running
      && scroller.idleFor(now) > 240 && Math.abs(scroller.velocity) < 60) {
      const snap = director.snapTarget(scroller.y);
      if (snap !== null) scroller.scrollTo(snap, { duration: snap < 4 ? 1.4 : 1.1 });
    }
    start.update(scroller.y, now);

    stage?.frame(state, dt, now / 1000, scroller.velocity);
    ui.update(state, { info: env.debug ? stage?.info : null });
  };
  requestAnimationFrame(tick);
}
